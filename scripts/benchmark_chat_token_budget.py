"""Measure AI-190 on synthetic prompts without printing content or credentials.

Run from the backend root with PYTHONPATH=. and a valid Gemini environment key.
This measures prompt fitting and generation, not the full retrieval endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from google import genai
from google.genai import types

from app.config import Settings
from app.services import chat_service, rag_service, token_budget_service


async def benchmark(env_file: str | None, model: str | None) -> dict:
    config = Settings(_env_file=env_file) if env_file else Settings()
    if not config.google_api_key:
        raise ValueError("A valid GEMINI_API_KEY is required")
    model = model or config.llm_model
    async with genai.Client(
        api_key=config.google_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=15000, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    ).aio as client:
        info = await client.models.get(model=model)
        if not info.input_token_limit or not info.output_token_limit:
            raise ValueError("Model does not expose token limits")
        counter = token_budget_service.GeminiTokenCounter(
            client, model, info.input_token_limit, info.output_token_limit
        )
        history = [
            f"Student: Explain loops, example {i}.\nAssistant: A loop repeats instructions. "
            + "Use a stopping condition. " * 80
            for i in range(20)
        ]
        chunks = [
            rag_service.ScoredChunk(
                "A loop repeats instructions while a condition holds. " * 100,
                0.95,
                {"document_id": "synthetic-loop", "title": "Synthetic lesson"},
            )
        ]
        original = chat_service._format_messages(
            "answer-course-prompt",
            context=chat_service._course_context(chunks),
            question="Explain what a loop does in two sentences.",
            history="\n\n".join(history),
        )
        render, sources = chat_service._budget_renderer(original, chunks, [])
        before_messages = render(history, sources)
        # Independent counter: baseline measurement must not consume the fitter's cap.
        before = (
            await client.models.count_tokens(
                model=model,
                contents=token_budget_service.prompt_text(before_messages),
            )
        ).total_tokens
        started = time.monotonic()
        fitted = await token_budget_service.fit_prompt(
            render,
            history,
            sources,
            counter,
            token_budget_service.BudgetLimits(
                input=config.chat_input_max_tokens,
                system=config.chat_system_max_tokens,
                history=config.chat_history_max_tokens,
                documents=config.chat_documents_max_tokens,
                answer=config.chat_answer_max_tokens,
                margin=config.chat_token_safety_margin,
            ),
        )
        fit_ms = (time.monotonic() - started) * 1000
        generations = []
        for messages in (before_messages, fitted.messages):
            started = time.monotonic()
            response = await client.models.generate_content(
                model=model,
                contents=messages[1].content,
                config=types.GenerateContentConfig(
                    system_instruction=messages[0].content,
                    max_output_tokens=config.chat_answer_max_tokens,
                ),
            )
            generations.append(
                {
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "answer_received": bool(response.text),
                    "usage_prompt_tokens": response.usage_metadata.prompt_token_count,
                }
            )
        return {
            "model": model,
            "history_turns_before": 20,
            "history_turns_after": len(fitted.history),
            "counted_prompt_tokens_before": before,
            "counted_prompt_tokens_after": fitted.tokens,
            "count_api_calls": counter.calls,
            "fit_latency_ms": round(fit_ms, 1),
            "generation_before": generations[0],
            "generation_after": generations[1],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", help="Optional environment file; never printed")
    parser.add_argument("--model", help="Optional Gemini model override")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(benchmark(args.env_file, args.model)), indent=2))
    except Exception as exc:  # noqa: BLE001 - scrub provider diagnostics at the CLI boundary
        # SDK errors can contain request details; retain only safe diagnostics.
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "http_status": getattr(exc, "code", None),
                }
            )
        )
        raise SystemExit(1) from None
