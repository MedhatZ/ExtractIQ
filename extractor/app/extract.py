from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.errors import fetch_failed
from app.fetch import FetchedPage, decode_body, fetch_url
from app.html_text import html_to_text
from app.models import ExtractResponse, Meta, Source
from app.openai_client import complete_extraction


def extract_from_page(
    page: FetchedPage,
    requested_url: str,
    *,
    settings: Settings | None = None,
) -> ExtractResponse:
    settings = settings or get_settings()
    raw = decode_body(page)
    text = html_to_text(raw, page.content_type)
    if not text.strip():
        raise fetch_failed("no extractable text was found in the source")

    truncated = False
    if len(text) > settings.max_text_chars:
        text = text[: settings.max_text_chars]
        truncated = True

    extraction, model_name, is_mock = complete_extraction(
        text,
        requested_url,
        settings=settings,
    )
    return ExtractResponse(
        source=Source(
            url=page.url,
            fetchedAt=datetime.now(timezone.utc).isoformat(),
            contentType=page.content_type,
            truncated=truncated,
        ),
        extraction=extraction,
        meta=Meta(model=model_name, mock=is_mock),
    )


def extract_from_url(url: str, *, settings: Settings | None = None) -> ExtractResponse:
    settings = settings or get_settings()
    page = fetch_url(url, settings=settings)
    return extract_from_page(page, url, settings=settings)
