"""Separate web-search answer path used only after explicit consent.

Search and fetch are intentionally isolated from the course-source answer:
the model sees the authorized query scope and fetched public web evidence,
never course documents, the course answer, or conversation history.
"""

from __future__ import annotations

import html
import ipaddress
import json
import logging
import re
import socket
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpcore
from sqlalchemy.orm import Session

from app.core.prompt_manager import get_prompt_manager
from app.services import rag_service, strict_sources_service

logger = logging.getLogger(__name__)

WEB_ANSWER_PROMPT = "web-answer-prompt"
MAX_FETCH_BYTES = 200_000
MAX_REDIRECTS = 3
MAX_WEB_SOURCES = 3


class WebEvidenceError(RuntimeError):
    """The web path could not obtain or validate usable evidence."""


class WebAnswerValidationError(WebEvidenceError):
    """The web answer model response violated the strict citation contract."""


class WebAnswerGenerationError(WebEvidenceError):
    """The web answer model failed before a validated answer existed."""


WEB_DIAG_NO_USABLE_SOURCES = "no usable fetched sources"
WEB_DIAG_ANSWER_VALIDATION = "strict web answer validation failed"
WEB_DIAG_ANSWER_GENERATION = "strict web answer generation failed"


def _web_diagnostic(message: str, **fields: int | str) -> None:
    """Log only non-sensitive branch metadata, never query/page/URL content."""

    details = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.warning(
        "Strict web diagnostic: %s%s",
        message,
        f" ({details})" if details else "",
    )


@dataclass(frozen=True)
class WebEvidence:
    source_id: str
    title: str
    url: str
    content: str


@dataclass(frozen=True)
class WebAnswerResult:
    answer: str
    citations: tuple[rag_service.Source, ...]
    conflicts: str = ""


class _TextExtractor(HTMLParser):
    """Small stdlib HTML-to-text extractor with script/style exclusion."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "template"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "template"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def _resolve_public_target(url: str) -> tuple[str, str, str]:
    """Return ``(url, host, pinned_public_ip)`` for one HTTP(S) target.

    The IP selected here is the only address the transport is allowed to
    connect to. A later DNS answer (including a rebinding answer) is ignored.
    """

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WebEvidenceError("Web evidence URL must be a public HTTP(S) URL.")
    if parsed.username or parsed.password:
        raise WebEvidenceError("Web evidence URL must not contain credentials.")

    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        raise WebEvidenceError("Web evidence URL must not target localhost.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise WebEvidenceError("Web evidence URL host could not be resolved.") from exc
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise WebEvidenceError("Web evidence URL must resolve only to public IP addresses.")
    return url, host, min(addresses)


def validate_public_http_url(url: str) -> str:
    """Reject credentials, non-HTTP(S), localhost, and non-public DNS results."""

    return _resolve_public_target(url)[0]


class _PinnedPublicBackend(httpcore.SyncBackend):
    """httpcore backend that connects only to the IP validated for one host.

    httpcore still receives the original URL host, so ``Host`` and TLS SNI are
    preserved; only the TCP destination is pinned.
    """

    def __init__(self, *, host: str, ip: str) -> None:
        self._expected_host = host.lower().rstrip(".")
        self._pinned_ip = ip

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any | None = None,
    ) -> httpcore.NetworkStream:
        if host.lower().rstrip(".") != self._expected_host:
            raise httpcore.ConnectError("Refusing to connect to an unexpected web host.")
        return super().connect_tcp(
            self._pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


def _read_capped_body(response: Any, *, max_bytes: int = MAX_FETCH_BYTES) -> bytes:
    """Stream a response and fail before storing more than the hard cap."""

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_stream():
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise WebEvidenceError(
                f"Web evidence body exceeded the {max_bytes} byte cap."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _header_value(headers: Sequence[tuple[bytes, bytes]], name: bytes) -> str | None:
    wanted = name.lower()
    for key, value in headers:
        if key.lower() == wanted:
            return value.decode("latin-1")
    return None


def fetch_public_web(url: str, *, timeout_seconds: float = 8.0) -> str:
    """Fetch one public page with pinned DNS, bounded redirects and hard byte cap."""

    current = url
    headers = [
        (b"user-agent", b"CourseQAAgent/1.0 (strict-source web evidence)"),
        (b"accept", b"text/html,text/plain;q=0.9,*/*;q=0.1"),
        (b"accept-encoding", b"identity"),
    ]
    timeout_extensions = {
        "timeout": {
            "connect": timeout_seconds,
            "read": timeout_seconds,
            "write": timeout_seconds,
            "pool": timeout_seconds,
        }
    }
    try:
        for _ in range(MAX_REDIRECTS + 1):
            current, host, pinned_ip = _resolve_public_target(current)
            backend = _PinnedPublicBackend(host=host, ip=pinned_ip)
            ssl_context = ssl.create_default_context()
            with httpcore.ConnectionPool(  # noqa: SIM117 - response must close before redirect retry
                ssl_context=ssl_context,
                network_backend=backend,
                http2=False,
            ) as pool:
                with pool.stream(
                    "GET",
                    current,
                    headers=headers,
                    extensions=timeout_extensions,
                ) as response:
                    location = _header_value(response.headers, b"location")
                    if response.status in {301, 302, 303, 307, 308}:
                        if not location:
                            raise WebEvidenceError("Web evidence redirect had no target.")
                        current = urljoin(current, location)
                        continue
                    if response.status < 200 or response.status >= 300:
                        raise WebEvidenceError("Web evidence page was not accessible.")

                    content_type = (_header_value(response.headers, b"content-type") or "").split(
                        ";"
                    )[0].strip().lower()
                    if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                        raise WebEvidenceError("Web evidence page is not text content.")
                    declared_length = _header_value(response.headers, b"content-length")
                    if declared_length is not None:
                        try:
                            declared = int(declared_length)
                        except ValueError:
                            declared = None
                        if declared is not None and declared > MAX_FETCH_BYTES:
                            raise WebEvidenceError(
                                f"Web evidence body exceeded the {MAX_FETCH_BYTES} byte cap."
                            )

                    body = _read_capped_body(response)
                    charset = "utf-8"
                    raw_content_type = _header_value(response.headers, b"content-type") or ""
                    for part in raw_content_type.split(";")[1:]:
                        key, _, value = part.partition("=")
                        if key.strip().lower() == "charset" and value.strip():
                            charset = value.strip()
                            break
                    text = body.decode(charset, errors="replace")
                    if content_type == "text/plain":
                        return " ".join(text.split())
                    parser = _TextExtractor()
                    parser.feed(text)
                    extracted = html.unescape(parser.text()).strip()
                    if not extracted:
                        raise WebEvidenceError("Web evidence page had no readable text.")
                    return extracted
    except WebEvidenceError:
        raise
    except Exception as exc:
        raise WebEvidenceError("Web evidence page could not be fetched safely.") from exc
    raise WebEvidenceError("Web evidence page exceeded the redirect limit.")


def search_web_evidence(
    query: str,
    *,
    search_fn: Callable[..., Sequence[rag_service.WebResult]] = rag_service.search_internet,
    fetch_fn: Callable[[str], str] = fetch_public_web,
) -> list[WebEvidence]:
    """Search first, then fetch only public HTTP(S) pages with bounded reads."""

    results = list(search_fn(query, verify_urls=False))
    evidence: list[WebEvidence] = []
    failures = 0
    for result in results:
        if len(evidence) >= MAX_WEB_SOURCES:
            break
        try:
            safe_url = validate_public_http_url(result.url)
            content = fetch_fn(safe_url)
        except Exception as exc:  # noqa: BLE001 - one bad page must not abort the others
            failures += 1
            logger.info("Dropping inaccessible web evidence: %s", type(exc).__name__)
            continue
        clean = " ".join((content or "").split())
        if not clean:
            failures += 1
            continue
        evidence.append(
            WebEvidence(
                source_id=f"W{len(evidence) + 1}",
                title=(result.title or result.url).strip(),
                url=safe_url,
                content=clean[:20_000],
            )
        )
    if not evidence:
        _web_diagnostic(
            WEB_DIAG_NO_USABLE_SOURCES,
            results=len(results),
            evidence=0,
            failures=failures,
        )
        raise WebEvidenceError("No usable public web evidence was found.")
    return evidence


def build_web_answer_messages(
    query_scope: str,
    evidence: Sequence[strict_sources_service.StrictSource],
) -> list[Any]:
    """Build the web-only prompt; no course documents or history are accepted."""

    if not query_scope.strip() or not evidence:
        raise WebEvidenceError("Web answer requires an authorized scope and evidence.")
    from langchain_core.messages import HumanMessage, SystemMessage

    evidence_json = json.dumps(
        [
            {
                "source_id": item.source_id,
                "title": item.title,
                "content": item.content,
            }
            for item in evidence
        ],
        ensure_ascii=False,
        indent=2,
    )
    prompt = get_prompt_manager().format(
        WEB_ANSWER_PROMPT,
        query_scope=query_scope.strip(),
        evidence_json=evidence_json,
    )
    return [
        SystemMessage(content=str(prompt["system-prompt"])),
        HumanMessage(content=str(prompt["user-prompt"])),
    ]


def _web_citations(
    source_ids: Sequence[str],
    allowed: dict[str, WebEvidence],
) -> tuple[rag_service.Source, ...]:
    citations: list[rag_service.Source] = []
    for index, source_id in enumerate(source_ids, start=1):
        evidence = allowed.get(source_id)
        if evidence is None:
            raise WebAnswerValidationError(
                "Web answer cited a source outside the fetched evidence."
            )
        citations.append(
            rag_service.Source(
                index=index,
                kind=rag_service.SOURCE_INTERNET,
                title=evidence.title,
                url=evidence.url,
                snippet=evidence.content[: rag_service.CITATION_SNIPPET_LENGTH],
            )
        )
    return tuple(citations)


def _remap_markers(answer: str, source_ids: Sequence[str]) -> str:
    mapping = {source_id: str(index) for index, source_id in enumerate(source_ids, start=1)}

    def replace(match: re.Match[str]) -> str:
        source_id = match.group(1)
        return f"[{mapping[source_id]}]" if source_id in mapping else match.group(0)

    return re.sub(r"\[([A-Za-z0-9_-]+)\]", replace, answer)


async def generate_web_answer(
    *,
    query_scope: str,
    evidence: Sequence[WebEvidence],
    db: Session | None = None,
    model_invoker: Callable[[Sequence[Any]], Any] | None = None,
    timeout_seconds: float | None = None,
) -> WebAnswerResult:
    """Generate and validate one separate web answer; fail closed on uncertainty."""

    if not evidence:
        _web_diagnostic(WEB_DIAG_NO_USABLE_SOURCES, evidence=0)
        raise WebEvidenceError("No usable public web evidence was found.")
    allowed = {item.source_id: item for item in evidence}
    strict_sources = [
        strict_sources_service.StrictSource(
            source_id=item.source_id,
            content=item.content,
            title=item.title,
        )
        for item in evidence
    ]
    try:
        result = await strict_sources_service.generate_strict_sources_answer(
            question=query_scope,
            sources=strict_sources,
            db=db,
            model_invoker=model_invoker,
            timeout_seconds=timeout_seconds,
            messages_builder=build_web_answer_messages,
        )
    except strict_sources_service.StrictSourcesValidationError as exc:
        _web_diagnostic(WEB_DIAG_ANSWER_VALIDATION, evidence=len(evidence))
        raise WebAnswerValidationError(
            "Web answer did not validate against the authorized query and evidence."
        ) from exc
    except strict_sources_service.StrictSourcesError as exc:
        _web_diagnostic(WEB_DIAG_ANSWER_GENERATION, evidence=len(evidence))
        raise WebAnswerGenerationError("Web answer generation failed.") from exc

    if result.status == "full":
        answer = (result.answer or "").strip()
        used = list(result.source_ids_used)
        if not answer or not used:
            _web_diagnostic(WEB_DIAG_ANSWER_VALIDATION, evidence=len(evidence))
            raise WebAnswerValidationError("Web answer was not supported by the web evidence.")
        return WebAnswerResult(
            answer=f"**Web Search Answer**\n\n{_remap_markers(answer, used)}",
            citations=_web_citations(used, allowed),
        )

    conflict_ids = _conflict_ids(result)
    if result.status == "none" and conflict_ids:
        conflict_lines = [
            "**Web Search Answer**",
            "",
            "**Source conflict warning:** the fetched web sources disagree; no winner was selected.",
        ]
        for intent in result.intents:
            if intent.status != "conflicting":
                continue
            note = (intent.conflict_note or "The web sources conflict.").strip()
            markers = " ".join(f"[{source_id}]" for source_id in intent.source_ids)
            conflict_lines.append(f"- {intent.question}: {note} {markers}".strip())
        return WebAnswerResult(
            answer=_remap_markers("\n".join(conflict_lines), conflict_ids),
            citations=_web_citations(conflict_ids, allowed),
            conflicts="The fetched web sources conflict; no winner was selected.",
        )

    _web_diagnostic(WEB_DIAG_ANSWER_VALIDATION, evidence=len(evidence))
    raise WebAnswerValidationError(
        "Web evidence did not cover the full authorized query or was insufficient."
    )


def _conflict_ids(result: strict_sources_service.StrictSourcesResult) -> list[str]:
    source_ids: list[str] = []
    for intent in result.intents:
        if intent.status != "conflicting":
            continue
        for source_id in intent.source_ids:
            if source_id not in source_ids:
                source_ids.append(source_id)
    return source_ids
