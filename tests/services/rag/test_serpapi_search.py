"""Internet source agent backed by SerpApi (Google Search) (AI-67)."""

from __future__ import annotations

from app.config.config import settings
from app.services import rag_service


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_search_internet_returns_nothing_without_a_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "serpapi_api_key", None)

    assert rag_service.search_internet("gửi email bằng python") == []


def test_search_internet_maps_google_organic_results(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def get(self, url, params=None):
            captured.update(url=url, params=params)
            return _FakeResponse(
                {
                    "organic_results": [
                        {
                            "title": "Send Email With Python",
                            "link": "https://realpython.com/python-send-email/",
                            "snippet": "Use smtplib to send email from Python.",
                        },
                        {"title": "Broken result without a link"},
                    ]
                }
            )

    monkeypatch.setattr(settings, "serpapi_api_key", "test-key")
    monkeypatch.setattr(rag_service, "_get_search_client", lambda: FakeClient())

    results = rag_service.search_internet("gửi email bằng python")

    assert captured["url"] == rag_service.SERPAPI_SEARCH_ENDPOINT
    params = captured["params"]
    assert params["engine"] == "google"
    assert params["q"] == "gửi email bằng python"
    assert params["api_key"] == "test-key"
    assert params["num"] == rag_service.SERPAPI_FETCH_RESULTS
    assert params["hl"] == "vi"
    assert "gl" not in params
    assert len(results) == 1
    assert results[0].title == "Send Email With Python"
    assert results[0].url.startswith("https://realpython.com/python-send-email/")
    assert results[0].content == "Use smtplib to send email from Python."


def test_search_internet_uses_english_market_for_english_questions(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def get(self, url, params=None):
            captured.update(params=params)
            return _FakeResponse({"organic_results": []})

    monkeypatch.setattr(settings, "serpapi_api_key", "test-key")
    monkeypatch.setattr(rag_service, "_get_search_client", lambda: FakeClient())

    rag_service.search_internet("python send email example")

    assert captured["params"]["hl"] == "en"
    assert "gl" not in captured["params"]


def test_search_internet_returns_nothing_when_the_provider_fails(monkeypatch) -> None:
    class BrokenClient:
        def get(self, *args, **kwargs):
            raise RuntimeError("quota exhausted")

    monkeypatch.setattr(settings, "serpapi_api_key", "test-key")
    monkeypatch.setattr(rag_service, "_get_search_client", lambda: BrokenClient())

    assert rag_service.search_internet("gửi email bằng python") == []


def test_is_url_accessible_handles_status_codes() -> None:
    class MockProbeResponse:
        def __init__(self, status_code: int, headers: dict | None = None) -> None:
            self.status_code = status_code
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class MockProbeClient:
        def __init__(self, status_code: int, headers: dict | None = None) -> None:
            self._status_code = status_code
            self._headers = headers or {}

        def head(self, url):
            if self._status_code in (405, 403):
                raise RuntimeError("HEAD rejected")
            return MockProbeResponse(self._status_code, self._headers)

        def stream(self, method, url):
            return MockProbeResponse(self._status_code, self._headers)

    # 200 OK -> Accessible
    client_200 = MockProbeClient(200)
    assert rag_service.is_url_accessible("https://learncpp.com/test", client=client_200) is True

    # 404 Not Found -> Pruned
    client_404 = MockProbeClient(404)
    assert rag_service.is_url_accessible("https://learncpp.com/dead", client=client_404) is False

    # 410 Gone -> Pruned
    client_410 = MockProbeClient(410)
    assert rag_service.is_url_accessible("https://learncpp.com/gone", client=client_410) is False

    # 500 Server Error -> Pruned
    client_500 = MockProbeClient(500)
    assert rag_service.is_url_accessible("https://broken-server.com", client=client_500) is False

    # 403 Access Denied on unknown domain -> Pruned
    client_403_unknown = MockProbeClient(403)
    assert rag_service.is_url_accessible("https://private-paywall.xyz", client=client_403_unknown) is False

    # 403 with Cloudflare challenge -> Pruned (users in real browsers often get blocked with Access Denied)
    client_403_cf = MockProbeClient(403, headers={"server": "cloudflare", "cf-ray": "12345"})
    assert rag_service.is_url_accessible("https://stackoverflow.com/questions/123", client=client_403_cf) is False


def test_filter_accessible_web_results_prunes_dead_links() -> None:
    results = [
        rag_service.WebResult(title="Live 1", url="https://live1.com", content="c1"),
        rag_service.WebResult(title="Dead 404", url="https://dead404.com", content="c2"),
        rag_service.WebResult(title="Live 2", url="https://live2.com", content="c3"),
    ]

    def mock_probe(url: str) -> bool:
        return "dead" not in url

    filtered = rag_service.filter_accessible_web_results(results, probe_fn=mock_probe)
    assert len(filtered) == 2
    assert [r.title for r in filtered] == ["Live 1", "Live 2"]


def test_search_internet_prunes_dead_urls_when_verified(monkeypatch) -> None:
    class FakeClient:
        def get(self, url, params=None):
            return _FakeResponse(
                {
                    "organic_results": [
                        {
                            "title": "Good Result Python",
                            "link": "https://realpython.com/good-article/",
                            "snippet": "Python tips smtplib",
                        },
                        {
                            "title": "Dead Result Python",
                            "link": "https://developer.mozilla.org/dead-page/",
                            "snippet": "Python dead link smtplib",
                        },
                    ]
                }
            )

    monkeypatch.setattr(settings, "serpapi_api_key", "test-key")
    monkeypatch.setattr(rag_service, "_get_search_client", lambda: FakeClient())

    def custom_probe(url: str) -> bool:
        return "dead" not in url

    results = rag_service.search_internet("python smtplib", verify_urls=True, probe_fn=custom_probe)
    assert len(results) == 1
    assert results[0].title == "Good Result Python"

