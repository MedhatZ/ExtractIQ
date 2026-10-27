from unittest.mock import patch

from fastapi.testclient import TestClient

from app.errors import AppError
from app.fetch import FetchedPage
from app.models import ExtractResponse, Extraction, Meta, Source

SAMPLE_HTML = b"""
<html><head><title>Example Domain</title></head>
<body><h1>Example Domain</h1><p>This domain is for use in documentation examples.</p></body>
</html>
"""


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_success_in_mock_mode(client: TestClient) -> None:
    page = FetchedPage(
        url="https://example.com/",
        body=SAMPLE_HTML,
        content_type="text/html",
    )
    with patch("app.extract.fetch_url", return_value=page):
        response = client.post("/extract", json={"url": "https://example.com/"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["mock"] is True
    assert body["extraction"]["title"]
    assert body["source"]["url"] == "https://example.com/"


def test_missing_url(client: TestClient) -> None:
    response = client.post("/extract", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_invalid_url_scheme(client: TestClient) -> None:
    response = client.post("/extract", json={"url": "file:///etc/passwd"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SSRF_BLOCKED"


def test_loopback_url_is_rejected(client: TestClient) -> None:
    response = client.post("/extract", json={"url": "http://127.0.0.1/admin"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SSRF_BLOCKED"


def test_extractor_fetch_failure(client: TestClient) -> None:
    with patch(
        "app.extract.fetch_url",
        side_effect=AppError("FETCH_FAILED", "could not fetch the source URL", 502),
    ):
        response = client.post("/extract", json={"url": "https://example.com/"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "FETCH_FAILED"


def test_extractor_timeout(client: TestClient) -> None:
    with patch(
        "app.extract.fetch_url",
        side_effect=AppError("UPSTREAM_TIMEOUT", "timed out", 504),
    ):
        response = client.post("/extract", json={"url": "https://example.com/"})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "UPSTREAM_TIMEOUT"


def test_malformed_ai_response_from_pipeline(client: TestClient) -> None:
    page = FetchedPage(
        url="https://example.com/",
        body=SAMPLE_HTML,
        content_type="text/html",
    )
    with patch("app.extract.fetch_url", return_value=page), patch(
        "app.extract.complete_extraction",
        side_effect=AppError("MALFORMED_AI_RESPONSE", "bad json", 502),
    ):
        response = client.post("/extract", json={"url": "https://example.com/"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MALFORMED_AI_RESPONSE"


def test_response_schema_shape() -> None:
    payload = ExtractResponse(
        source=Source(
            url="https://example.com",
            fetchedAt="2026-01-01T00:00:00+00:00",
            contentType="text/html",
            truncated=False,
        ),
        extraction=Extraction(
            title="T",
            summary="S",
            topics=["a"],
            entities={"people": [], "organizations": [], "locations": []},
            keyFacts=["k"],
        ),
        meta=Meta(model="mock", mock=True),
    )
    dumped = payload.model_dump()
    assert set(dumped.keys()) == {"source", "extraction", "meta"}
    assert set(dumped["extraction"].keys()) == {
        "title",
        "summary",
        "topics",
        "entities",
        "keyFacts",
    }
