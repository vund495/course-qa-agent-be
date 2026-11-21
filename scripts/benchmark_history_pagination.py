"""Compare offset vs keyset pagination for chat history (AI-185 AC-07).

Seeds one throwaway user + class with ``--rows`` sessions whose ``updated_at``
is evenly spread, then times three reads against the same data:

1. ``offset=0``  — first page (the common case)
2. ``offset=N-limit`` — deep offset, the case that degrades linearly
3. last cursor page — keyset seek at the same depth

Run from the backend root; ``DATABASE_URL`` is read from ``.env``:

    python scripts/benchmark_history_pagination.py --rows 5000

Seeded rows are deleted afterwards unless ``--keep`` is passed.
"""

from __future__ import annotations

import argparse
import math
import statistics
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_session_local
from app.models.chat import ChatSession
from app.models.course import Class
from app.models.user import Role, User
from app.services import history_service

BENCH_EMAIL_DOMAIN = "example.invalid"


def _seed(db: Session, rows: int) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an isolated user + class holding ``rows`` evenly spaced sessions."""
    suffix = uuid.uuid4().hex[:8]
    role = db.scalar(select(Role).where(Role.name == "TRAINER"))
    if role is None:
        raise SystemExit("Role TRAINER is missing — seed the database first.")

    user = User(
        full_name="AI-185 Benchmark",
        email=f"ai185-bench-{suffix}@{BENCH_EMAIL_DOMAIN}",
        role_id=role.id,
    )
    db.add(user)
    db.flush()

    clazz = Class(
        trainer_id=user.id,
        code=f"AI185-{suffix}",
        name="AI-185 Benchmark",
        semester="1",
        academic_year="2026-2027",
    )
    db.add(clazz)
    db.flush()

    base = datetime.now(UTC) - timedelta(minutes=rows + 1)
    db.execute(
        insert(ChatSession),
        [
            {
                "id": uuid.uuid4(),
                "user_id": user.id,
                "class_id": clazz.id,
                "title": f"Bench session {i}",
                "created_at": base + timedelta(minutes=i),
                "updated_at": base + timedelta(minutes=i),
                "is_pinned": False,
                "pinned_at": None,
            }
            for i in range(rows)
        ],
    )
    db.commit()
    return user.id, clazz.id


def _cleanup(db: Session, user_id: uuid.UUID, class_id: uuid.UUID) -> None:
    db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    db.execute(delete(Class).where(Class.id == class_id))
    db.execute(delete(User).where(User.id == user_id))
    db.commit()


def _last_page_cursor(
    db: Session, user_id: uuid.UUID, class_id: uuid.UUID, limit: int
) -> str | None:
    """Walk every page once and return the cursor that produces the final page."""
    cursor: str | None = None
    while True:
        _, _, next_cursor = history_service.get_sessions_cursor(
            db=db,
            user_id=user_id,
            section="recent",
            cursor=cursor,
            class_id=class_id,
            limit=limit,
        )
        if next_cursor is None:
            return cursor
        cursor = next_cursor


def _time(call: Callable[[], object], runs: int, warmup: int) -> list[float]:
    for _ in range(warmup):
        call()
    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _report(title: str, rows: int, samples: list[float]) -> None:
    print(
        f"{title:<22} | {rows:>4} | {statistics.median(samples):>9.2f} | {_p95(samples):>7.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=5000, help="Sessions to seed")
    parser.add_argument("--limit", type=int, default=20, help="Page size")
    parser.add_argument("--runs", type=int, default=20, help="Timed repetitions")
    parser.add_argument("--warmup", type=int, default=3, help="Untimed warm-up runs")
    parser.add_argument("--keep", action="store_true", help="Keep the seeded rows")
    args = parser.parse_args()

    if args.rows < args.limit * 2:
        raise SystemExit("--rows must be at least twice --limit.")

    session_factory = get_session_local(settings.database_url)
    db: Session = session_factory()
    user_id: uuid.UUID | None = None
    class_id: uuid.UUID | None = None
    try:
        print(
            f"backend={db.bind.dialect.name} rows={args.rows} "
            f"limit={args.limit} runs={args.runs} warmup={args.warmup}"
        )
        user_id, class_id = _seed(db, args.rows)

        deep_offset = args.rows - args.limit
        last_cursor = _last_page_cursor(db, user_id, class_id, args.limit)

        def first_page() -> int:
            items, _ = history_service.get_sessions_by_class(
                db=db, user_id=user_id, class_id=class_id, limit=args.limit, offset=0
            )
            return len(items)

        def deep_page() -> int:
            items, _ = history_service.get_sessions_by_class(
                db=db,
                user_id=user_id,
                class_id=class_id,
                limit=args.limit,
                offset=deep_offset,
            )
            return len(items)

        def cursor_page() -> int:
            items, _, _ = history_service.get_sessions_cursor(
                db=db,
                user_id=user_id,
                section="recent",
                cursor=last_cursor,
                class_id=class_id,
                limit=args.limit,
            )
            return len(items)

        print()
        print(f"{'mode':<22} | rows | median_ms |  p95_ms")
        print(f"{'-' * 22}-+------+-----------+--------")
        for title, call in (
            ("offset (first page)", first_page),
            (f"offset (deep {deep_offset})", deep_page),
            ("cursor (last page)", cursor_page),
        ):
            rows = call()
            _report(title, rows, _time(call, args.runs, args.warmup))
    finally:
        if user_id is not None and class_id is not None:
            if args.keep:
                print(f"\nkept rows: user={user_id} class={class_id}")
            else:
                _cleanup(db, user_id, class_id)
        db.close()


if __name__ == "__main__":
    main()
