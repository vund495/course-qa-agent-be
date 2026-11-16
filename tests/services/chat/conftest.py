"""Keep chat regression tests offline; token API contracts have dedicated tests."""

from types import SimpleNamespace

import pytest

from app.services import token_budget_service


@pytest.fixture(autouse=True)
def offline_answer_token_counter(monkeypatch, request):
    if request.node.path.name == "test_token_budget.py":
        return

    async def count(text):
        return (len(text.encode("utf-8")) + 3) // 4

    async def close():
        pass

    async def open_counter(db, model=None, **kwargs):
        return SimpleNamespace(
            model=model or "offline-test",
            input_limit=1000000,
            output_limit=64000,
            count=count,
            client=SimpleNamespace(aclose=close),
        )

    monkeypatch.setattr(token_budget_service, "open_counter", open_counter)
