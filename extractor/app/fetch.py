from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from app.config import Settings, get_settings
from app.errors import fetch_failed, upstream_timeout
from app.ssrf import parse_public_url, validate_resolved_url

USER_AGENT = "ai-extraction-sample/1.0"
ALLOWED_CONTENT_PREFIXES = ("text/html", "application/xhtml+xml", "text/plain")


@dataclass(frozen=True)
class FetchedPage:
    url: str
    body: bytes
    content_type: str


def _content_type(header: str | None) -> str:
    if not header:
        return "application/octet-stream"
    return header.split(";", 1)[0].strip().lower() or "application/octet-stream"


def _is_redirect(status: int) -> bool:
    return status in {301, 302, 303, 307, 308}


def fetch_url(
    raw_url: str,
    *,
    client: httpx.Client | None = None,
    settings: Settings | None = None,
) -> FetchedPage:
    settings = settings or get_settings()
    current = validate_resolved_url(raw_url)
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(settings.fetch_timeout_seconds),
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )

    try:
        for _ in range(settings.max_redirects + 1):
            try:
                with client.stream("GET", current) as response:
                    if _is_redirect(response.status_code):
                        location = response.headers.get("location")
                        if not location:
                            raise fetch_failed("redirect was missing a Location header")
                        nxt = urljoin(str(response.url), location)
                        current = validate_resolved_url(nxt)
                        continue
                    if response.status_code < 200 or response.status_code >= 300:
                        raise fetch_failed(f"source returned HTTP {response.status_code}")

                    content_type = _content_type(response.headers.get("content-type"))
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > settings.allowed_content_max_bytes:
                            raise fetch_failed("source exceeded the maximum allowed size")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    if not body:
                        raise fetch_failed("source returned an empty body")
                    return FetchedPage(
                        url=str(response.url),
                        body=body,
                        content_type=content_type,
                    )
            except httpx.TimeoutException as exc:
                raise upstream_timeout("timed out while fetching the source URL") from exc
            except httpx.RequestError as exc:
                raise fetch_failed("could not fetch the source URL") from exc
        raise fetch_failed("too many redirects")
    finally:
        if owns_client:
            client.close()


def decode_body(page: FetchedPage) -> str:
    parse_public_url(page.url)
    if not any(page.content_type.startswith(prefix) for prefix in ALLOWED_CONTENT_PREFIXES):
        raise fetch_failed(f"unsupported content type: {page.content_type}")
    return page.body.decode("utf-8", errors="replace")
