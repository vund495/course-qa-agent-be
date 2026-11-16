"""Bound answer prompts using provider token counts (AI-190)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from google import genai
from google.genai import types

from app.config import settings
from app.services import gemini_key_service

logger = logging.getLogger(__name__)
# Public model metadata contains no credentials. Bound the cache to active models.
_model_limits: dict[str, tuple[int, int]] = {}


class TokenBudgetError(RuntimeError):
    """The answer cannot safely be generated within its token budget."""


@dataclass(frozen=True)
class BudgetLimits:
    input: int = 24000
    system: int = 6000
    history: int = 4000
    documents: int = 12000
    answer: int = 4000
    margin: int = 1000

    @classmethod
    def configured(cls) -> BudgetLimits:
        return cls(
            *(
                getattr(settings, f"chat_{name}_max_tokens")
                for name in ("input", "system", "history", "documents", "answer")
            ),
            margin=settings.chat_token_safety_margin,
        )


@dataclass(frozen=True)
class ContextSource:
    content: str
    priority: float
    identity: Any = None
    prefix: str = ""


@dataclass
class BudgetedPrompt:
    messages: list[Any]
    history: list[str]
    sources: list[ContextSource]
    tokens: int


def prompt_text(messages: Sequence[Any]) -> str:
    """Include every rendered instruction, delimiter and question in the count."""
    return "\n".join(str(message.content) for message in messages)


@dataclass
class CountingAllowance:
    """Shared count calls and active I/O time across keys and fallback models."""

    calls: int = 0
    seconds: float = 15.0


def _token_client(api_key: str) -> Any:
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=int(settings.chat_token_count_timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    ).aio


class GeminiTokenCounter:
    """Request-scoped counting with bounded key rotation and exact-text caching."""

    def __init__(
        self,
        client: Any,
        model: str,
        input_limit: int,
        output_limit: int,
        *,
        allowance: CountingAllowance | None = None,
        db: Any = None,
        resolved: Any = None,
    ):
        self.client = client
        self.model = model
        self.input_limit = input_limit
        self.output_limit = output_limit
        self.allowance = allowance or CountingAllowance()
        self.cache: dict[str, int] = {"": 0}
        self.db = db
        self.resolved = resolved
        self.excluded: set[Any] = set()

    @property
    def calls(self) -> int:
        return self.allowance.calls

    async def _request(self, operation: str, **kwargs: Any) -> Any:
        for _ in range(8):
            if self.allowance.seconds <= 0 or (operation == "count_tokens" and self.calls >= 8):
                raise TokenBudgetError(
                    "Unable to validate the chat context size. Please try again."
                )
            if operation == "count_tokens":
                self.allowance.calls += 1
            started = time.monotonic()
            try:
                return await asyncio.wait_for(
                    getattr(self.client.models, operation)(model=self.model, **kwargs),
                    timeout=min(settings.chat_token_count_timeout_seconds, self.allowance.seconds),
                )
            except Exception as exc:
                retryable = isinstance(exc, (TimeoutError, OSError)) or getattr(
                    exc, "code", None
                ) in (401, 403, 429, 500, 502, 503, 504)
                if getattr(exc, "code", None) == 400:
                    retryable = any(
                        marker in str(exc).lower()
                        for marker in ("api_key_invalid", "api key not valid", "api key is invalid")
                    )
                if self.resolved is None or not retryable:
                    raise
                failed = self.resolved
                if failed.key is not None:
                    gemini_key_service.mark_key_failure(self.db, failed.key, exc)
                if failed.key_id is None or not gemini_key_service.get_auto_switch(self.db):
                    raise
                self.excluded.add(failed.key_id)
                resolved = gemini_key_service.resolve_key(
                    self.db, model=self.model, exclude_ids=self.excluded
                )
                if resolved is None:
                    raise
                await self.client.aclose()
                self.client = _token_client(resolved.api_key)
                self.resolved = resolved
                logger.warning("Token counting switched Gemini key for model=%s", self.model)
            finally:
                self.allowance.seconds -= time.monotonic() - started
        raise TokenBudgetError("Unable to validate the chat context size. Please try again.")

    async def count(self, text: str) -> int:
        if text in self.cache:
            return self.cache[text]
        # Developer API rejects system_instruction in CountTokensConfig. Count
        # its text as contents too, with a separate protocol safety margin.
        response = await self._request("count_tokens", contents=text)
        count = response.total_tokens
        if not isinstance(count, int) or count < 0:
            raise TokenBudgetError("Gemini returned an invalid token count.")
        self.cache[text] = count
        return count


async def open_counter(
    db: Any, model: str | None = None, *, allowance: CountingAllowance | None = None
) -> GeminiTokenCounter:
    """Resolve pool credentials and cache public model limits; never expose keys."""
    model = model or gemini_key_service.get_chat_model(db)
    resolved = gemini_key_service.resolve_key(db, model=model)
    if resolved is None:
        raise TokenBudgetError("Gemini is not configured to validate the chat context size.")
    counter = GeminiTokenCounter(
        _token_client(resolved.api_key), model, 0, 0, allowance=allowance, db=db, resolved=resolved
    )
    try:
        if model not in _model_limits:
            info = await counter._request("get")
            if not info.input_token_limit or not info.output_token_limit:
                raise TokenBudgetError("Unable to determine the model context limits.")
            if len(_model_limits) >= 32:
                _model_limits.clear()
            _model_limits[model] = (info.input_token_limit, info.output_token_limit)
        counter.input_limit, counter.output_limit = _model_limits[model]
        return counter
    except BaseException:
        await counter.client.aclose()
        raise


def _source_text(sources: Sequence[ContextSource]) -> str:
    return "\n\n".join(f"[{i}] {s.prefix}{s.content}" for i, s in enumerate(sources, 1))


def _bytes(text: str) -> int:
    return len(text.encode("utf-8"))


async def fit_prompt(
    render: Callable[[list[str], list[ContextSource]], list[Any]],
    history: Sequence[str],
    sources: Sequence[ContextSource],
    counter: Any,
    limits: BudgetLimits | None = None,
) -> BudgetedPrompt:
    """Trim whole exchanges, then low-priority evidence; verify the final prompt."""
    limits = limits or BudgetLimits.configured()
    kept_history, kept_sources = list(history), list(sources)
    started = time.monotonic()
    try:
        async with asyncio.timeout(15):
            ceiling = min(limits.input, counter.input_limit - limits.answer - limits.margin)
            if ceiling <= 0 or limits.answer > counter.output_limit:
                raise TokenBudgetError(
                    "The configured token budget is incompatible with the selected model."
                )
            original = render(kept_history, kept_sources)
            system = "\n".join(str(m.content) for m in original if m.type == "system")
            if await counter.count(system) > limits.system:
                raise TokenBudgetError("The system instructions exceed their token budget.")
            before_h = await counter.count("\n".join(kept_history))
            before_d = await counter.count(_source_text(kept_sources))
            before_total = await counter.count(prompt_text(original))
            if (
                before_h <= limits.history
                and before_d <= limits.documents
                and before_total <= ceiling
            ):
                return BudgetedPrompt(original, kept_history, kept_sources, before_total)

            mandatory = await counter.count(prompt_text(render([], [])))
            if mandatory > ceiling:
                raise TokenBudgetError(
                    "The question or code is too long. Please shorten it and try again."
                )
            # Selection uses conservative UTF-8 bytes only after an exact count
            # proves trimming necessary. Provider counts always gate generation.
            available = max(0, ceiling - mandatory - 32)
            history_size = before_h
            while kept_history and (
                history_size > limits.history or history_size + before_d > available
            ):
                kept_history.pop(0)
                history_size = _bytes("\n".join(kept_history))
            document_limit = min(limits.documents, max(0, available - history_size))
            document_size = before_d
            while len(kept_sources) > 1 and document_size > document_limit:
                index = min(range(len(kept_sources)), key=lambda i: (kept_sources[i].priority, -i))
                kept_sources.pop(index)
                document_size = _bytes(_source_text(kept_sources))
            if kept_sources and document_size > document_limit:
                source = kept_sources[0]
                suffix = " [truncated]"
                allowed = max(0, document_limit - _bytes(suffix) - _bytes(source.prefix) - 4)
                prefix = source.content.encode("utf-8")[:allowed].decode("utf-8", errors="ignore")
                if not prefix:
                    raise TokenBudgetError(
                        "The token budget cannot retain the highest-priority source. Please shorten the question."
                    )
                kept_sources = [replace(source, content=prefix + suffix)]

            after_h = await counter.count("\n".join(kept_history))
            after_d = await counter.count(_source_text(kept_sources))
            messages = render(kept_history, kept_sources)
            total = await counter.count(prompt_text(messages))
            if after_h > limits.history or after_d > limits.documents or total > ceiling:
                raise TokenBudgetError(
                    "Unable to fit the chat context safely. Please shorten the question."
                )
            for section, before, after, removed in (
                ("history", before_h, after_h, len(history) - len(kept_history)),
                ("documents", before_d, after_d, len(sources) - len(kept_sources)),
            ):
                if before != after:
                    logger.warning(
                        "Token truncation section=%s before=%d after=%d dropped=%d removed=%d "
                        "model=%s budget=%d elapsed_ms=%.1f",
                        section,
                        before,
                        after,
                        max(0, before - after),
                        removed,
                        counter.model,
                        ceiling,
                        (time.monotonic() - started) * 1000,
                    )
            return BudgetedPrompt(messages, kept_history, kept_sources, total)
    except TokenBudgetError:
        raise
    except Exception as exc:
        raise TokenBudgetError(
            "Unable to validate the chat context size. Please try again."
        ) from exc
