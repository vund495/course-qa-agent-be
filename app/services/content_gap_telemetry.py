"""Best-effort in-process coordination for Content Gap Qdrant telemetry.

Only scalar job arguments are held here. A capture or web-update job owns one
state reference and one bounded worker slot until its worker function really
returns, so a cancelled request cannot pretend the Qdrant work finished.
Delete serializes against the same state: it marks the message deleted, waits
for any running worker to release the state lock, and only then removes points.
A queued worker sees the deleted flag and skips. State is removed when the last
worker/delete reference is released. A bounded tombstone cache blocks a delayed
capture from recreating a just-deleted point; it is process-local and evicts old
IDs, so multi-worker deployments still need their own deletion ordering.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

MAX_INFLIGHT_JOBS = 4
MAX_DELETED_TOMBSTONES = 4096
_SLOTS = threading.BoundedSemaphore(MAX_INFLIGHT_JOBS)
_THREADS: set[threading.Thread] = set()
_THREADS_GUARD = threading.Lock()
_DELETED_TOMBSTONES: OrderedDict[str, None] = OrderedDict()


class _MessageState:
    def __init__(self, key: str) -> None:
        self.key = key
        self.lock = threading.Lock()
        self.meta = threading.Lock()
        self.refs = 1
        self.deleted = False
        self.web_consumed = False

    def mark_deleted(self) -> None:
        with self.meta:
            self.deleted = True

    def is_deleted(self) -> bool:
        with self.meta:
            return self.deleted

    def mark_web_consumed(self) -> None:
        with self.meta:
            self.web_consumed = True

    def is_web_consumed(self) -> bool:
        with self.meta:
            return self.web_consumed


_STATES: dict[str, _MessageState] = {}
_STATES_GUARD = threading.Lock()


def _remember_deleted(key: str) -> None:
    with _STATES_GUARD:
        _DELETED_TOMBSTONES[key] = None
        _DELETED_TOMBSTONES.move_to_end(key)
        while len(_DELETED_TOMBSTONES) > MAX_DELETED_TOMBSTONES:
            _DELETED_TOMBSTONES.popitem(last=False)


def _is_tombstoned(key: str) -> bool:
    with _STATES_GUARD:
        return key in _DELETED_TOMBSTONES


def active_state_count() -> int:
    """Number of message states still referenced by a job or delete."""

    with _STATES_GUARD:
        return len(_STATES)


def deleted_tombstone_count() -> int:
    """Bounded process-local tombstones that block delayed captures."""

    with _STATES_GUARD:
        return len(_DELETED_TOMBSTONES)


def _acquire(key: str) -> _MessageState:
    with _STATES_GUARD:
        state = _STATES.get(key)
        if state is None:
            state = _MessageState(key)
            _STATES[key] = state
        else:
            state.refs += 1
        return state


def _release(state: _MessageState) -> None:
    with _STATES_GUARD:
        state.refs -= 1
        if state.refs <= 0:
            _STATES.pop(state.key, None)


def _run_job(
    state: _MessageState,
    func: Callable[..., Any],
    kwargs: dict[str, Any],
) -> None:
    try:
        if state.is_deleted():
            return
        with state.lock:
            if state.is_deleted():
                return
            func(**kwargs)
    except Exception:
        logger.warning(
            "Content-gap telemetry job failed for message %s.",
            state.key,
            exc_info=True,
        )
    finally:
        _SLOTS.release()
        _release(state)
        with _THREADS_GUARD:
            _THREADS.discard(threading.current_thread())


def _submit(
    state: _MessageState,
    func: Callable[..., Any],
    kwargs: dict[str, Any],
) -> bool:
    if not _SLOTS.acquire(blocking=False):
        _release(state)
        return False
    thread = threading.Thread(
        target=_run_job,
        args=(state, func, kwargs),
        name=f"content-gap-{state.key[:8]}",
        daemon=True,
    )
    with _THREADS_GUARD:
        _THREADS.add(thread)
    try:
        thread.start()
    except Exception:
        with _THREADS_GUARD:
            _THREADS.discard(thread)
        _SLOTS.release()
        _release(state)
        raise
    return True


def schedule_capture(
    capture_func: Callable[..., Any],
    *,
    message_id: str,
    **kwargs: Any,
) -> bool:
    """Submit one material capture without blocking the chat stream."""

    key = str(message_id)
    if not key:
        return False
    if _is_tombstoned(key):
        return False
    state = _acquire(key)
    if _is_tombstoned(key) or state.is_deleted():
        _release(state)
        return False
    kwargs["message_id"] = key
    kwargs["web_consumed"] = state.is_web_consumed
    return _submit(state, capture_func, kwargs)


def schedule_web_update(
    update_func: Callable[..., Any],
    *,
    message_id: str,
) -> bool:
    """Mark the turn consumed synchronously, then submit its payload update."""

    key = str(message_id)
    if not key:
        return False
    if _is_tombstoned(key):
        return False
    state = _acquire(key)
    state.mark_web_consumed()
    if _is_tombstoned(key) or state.is_deleted():
        _release(state)
        return False
    return _submit(state, update_func, {"message_id": key, "source": "web"})


def serialize_delete(
    delete_func: Callable[[], Any] | None,
    message_ids: list[str],
) -> None:
    """Wait for a running worker, then delete; queued workers will skip."""

    keys = list(dict.fromkeys(str(message_id) for message_id in message_ids if message_id))
    if not keys:
        return
    for key in keys:
        _remember_deleted(key)
    states = [_acquire(key) for key in keys]
    for state in states:
        state.mark_deleted()
    try:
        for state in states:
            with state.lock:
                # A running upsert finishes before delete; queued jobs skip.
                pass
        if delete_func is not None:
            delete_func()
    finally:
        for state in states:
            _release(state)


async def wait_for_tasks(timeout: float = 2.0) -> None:
    """Await workers that are still running in this process."""

    with _THREADS_GUARD:
        threads = [thread for thread in _THREADS if thread.is_alive()]
    if not threads:
        return

    def join_all() -> None:
        deadline = time.monotonic() + timeout
        for thread in threads:
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(remaining)

    await asyncio.to_thread(join_all)
