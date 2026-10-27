from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APITimeoutError, OpenAIError

from app.config import Settings
from app.errors import AppError
from app.extract import extract_from_page
from app.fetch import FetchedPage, fetch_url
from app.models import Extraction
from app.openai_client import anthropic_base_url, complete_extraction, parse_model_json, uses_anthropic

SAMPLE_HTML = """
<html>
  <head><title>Acme Widget Launch</title></head>
  <body>
    <h1>Acme Widget Launch</h1>
    <p>Jane Doe in Berlin announced that Acme Corp released Widget 2.0.</p>
  </body>
</html>
"""


def test_mock_extraction_from_html() -> None:
    page = FetchedPage(
        url="https://example.com/launch",
        body=SAMPLE_HTML.encode("utf-8"),
        content_type="text/html",
    )
    result = extract_from_page(
        page,
        "https://example.com/launch",
        settings=Settings(mock_ai=True),
    )
    assert result.meta.mock is True
    assert result.meta.model == "mock"
    assert result.extraction.title
    assert result.extraction.summary
    assert "example.com" in result.extraction.keyFacts[0]


def test_parse_model_json_strips_markdown_fences() -> None:
    payload = parse_model_json(
        '```json\n{"title": "Launch", "summary": "S", "topics": [], '
        '"entities": {"people": [], "organizations": [], "locations": []}, '
        '"keyFacts": []}\n```'
    )
    assert payload["title"] == "Launch"


def test_agentrouter_url_uses_anthropic_path() -> None:
    settings = Settings(
        mock_ai=False,
        openai_api_key="sk-test",
        openai_base_url="https://agentrouter.org/v1",
        openai_model="claude-opus-4-6",
    )
    assert uses_anthropic(settings) is True
    assert anthropic_base_url(settings.openai_base_url) == "https://agentrouter.org"


def test_agentrouter_anthropic_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = Extraction(
        title="Launch",
        summary="A product launch.",
        topics=["product"],
        entities={"people": ["Jane Doe"], "organizations": ["Acme"], "locations": ["Berlin"]},
        keyFacts=["Widget 2.0 was released."],
    )
    block = MagicMock(type="text", text=payload.model_dump_json())
    fake_msg = MagicMock(content=[block], model="claude-opus-4-6")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg
    monkeypatch.setattr("app.openai_client.Anthropic", lambda **_kwargs: fake_client)

    extraction, model_name, is_mock = complete_extraction(
        "some page text",
        "https://example.com",
        settings=Settings(
            mock_ai=False,
            openai_api_key="sk-test",
            openai_base_url="https://agentrouter.org/v1",
            openai_model="claude-opus-4-6",
        ),
    )
    assert is_mock is False
    assert model_name == "claude-opus-4-6"
    assert extraction.title == "Launch"
    assert extraction.entities.organizations == ["Acme"]


def test_malformed_ai_json() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = "not-json"
    with pytest.raises(AppError) as exc:
        complete_extraction(
            "some page text",
            "https://example.com",
            settings=Settings(mock_ai=False, openai_api_key="sk-test"),
            client=client,
        )
    assert exc.value.code == "MALFORMED_AI_RESPONSE"


def test_malformed_ai_schema() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = '{"title": 1}'
    with pytest.raises(AppError) as exc:
        complete_extraction(
            "some page text",
            "https://example.com",
            settings=Settings(mock_ai=False, openai_api_key="sk-test"),
            client=client,
        )
    assert exc.value.code == "MALFORMED_AI_RESPONSE"


def test_openai_timeout_is_mapped() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = APITimeoutError("timed out")
    with pytest.raises(AppError) as exc:
        complete_extraction(
            "some page text",
            "https://example.com",
            settings=Settings(mock_ai=False, openai_api_key="sk-test"),
            client=client,
        )
    assert exc.value.code == "UPSTREAM_TIMEOUT"


def test_openai_provider_failure() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = OpenAIError("provider down")
    with pytest.raises(AppError) as exc:
        complete_extraction(
            "some page text",
            "https://example.com",
            settings=Settings(mock_ai=False, openai_api_key="sk-test"),
            client=client,
        )
    assert exc.value.code == "INTERNAL_ERROR"


def test_valid_ai_payload_is_accepted() -> None:
    payload = Extraction(
        title="Launch",
        summary="A product launch.",
        topics=["product"],
        entities={"people": ["Jane Doe"], "organizations": ["Acme"], "locations": ["Berlin"]},
        keyFacts=["Widget 2.0 was released."],
    )
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = payload.model_dump_json()
    client.chat.completions.create.return_value.model = "gpt-4o-mini"
    extraction, model_name, is_mock = complete_extraction(
        "some page text",
        "https://example.com",
        settings=Settings(mock_ai=False, openai_api_key="sk-test"),
        client=client,
    )
    assert is_mock is False
    assert model_name == "gpt-4o-mini"
    assert extraction.title == "Launch"
    assert extraction.entities.people == ["Jane Doe"]


def test_fetch_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.fetch.validate_resolved_url",
        lambda url: url,
    )

    class FakeClient:
        def stream(self, *_args, **_kwargs):
            raise httpx.TimeoutException("slow")

        def close(self) -> None:
            return None

    with pytest.raises(AppError) as exc:
        fetch_url("https://example.com", client=FakeClient())  # type: ignore[arg-type]
    assert exc.value.code == "UPSTREAM_TIMEOUT"


def test_fetch_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.fetch.validate_resolved_url", lambda url: url)

    class FakeClient:
        def stream(self, *_args, **_kwargs):
            raise httpx.ConnectError("refused")

        def close(self) -> None:
            return None

    with pytest.raises(AppError) as exc:
        fetch_url("https://example.com", client=FakeClient())  # type: ignore[arg-type]
    assert exc.value.code == "FETCH_FAILED"


def test_redirect_is_revalidated() -> None:
    calls: list[str] = []

    def fake_validate(url: str) -> str:
        calls.append(url)
        if "private.example" in url:
            raise AppError("SSRF_BLOCKED", "blocked", 400)
        return url

    request = httpx.Request("GET", "https://example.com")
    redirect = httpx.Response(
        302,
        headers={"location": "http://private.example/secret"},
        request=request,
    )

    class FakeStream:
        def __enter__(self):
            return redirect

        def __exit__(self, *_args) -> None:
            return None

    class FakeClient:
        def stream(self, method: str, url: str):
            assert method == "GET"
            return FakeStream()

        def close(self) -> None:
            return None

    with patch("app.fetch.validate_resolved_url", side_effect=fake_validate):
        with pytest.raises(AppError) as exc:
            fetch_url("https://example.com", client=FakeClient())  # type: ignore[arg-type]
    assert exc.value.code == "SSRF_BLOCKED"
    assert any("private.example" in url for url in calls)
