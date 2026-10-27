from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urlparse

from anthropic import Anthropic
from anthropic import APIStatusError as AnthropicStatusError
from anthropic import APITimeoutError as AnthropicTimeoutError
from openai import APITimeoutError, OpenAI, OpenAIError
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.errors import internal_error, malformed_ai, upstream_timeout
from app.models import Extraction

SYSTEM_PROMPT = """You extract structured metadata from webpage text.
Return a JSON object with exactly these keys:
- title: string
- summary: string
- topics: array of strings
- entities: object with people, organizations, and locations arrays of strings
- keyFacts: array of strings
Use only information present in the text. If a field is unknown, use an empty string or empty array.
Do not include markdown."""


def mock_completion(text: str, url: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = lines[0][:120] if lines else url
    snippet = " ".join(text.split())
    summary = snippet[:400] if snippet else "No extractable summary was found."
    return {
        "title": title,
        "summary": summary,
        "topics": ["sample", "extraction"],
        "entities": {
            "people": [],
            "organizations": [],
            "locations": [],
        },
        "keyFacts": [f"Source URL: {url}"],
    }


def complete_extraction(
    text: str,
    url: str,
    *,
    settings: Settings | None = None,
    client: OpenAI | None = None,
) -> tuple[Extraction, str, bool]:
    settings = settings or get_settings()
    if settings.mock_ai:
        payload = mock_completion(text, url)
        return Extraction.model_validate(payload), "mock", True

    if not settings.openai_api_key:
        raise internal_error("OPENAI_API_KEY is not set and MOCK_AI is false")

    try:
        if client is None and uses_anthropic(settings):
            content, model_name = _complete_with_anthropic(settings, text, url)
        else:
            openai_client = client or _build_client(settings)
            response = _create_completion(openai_client, settings, text, url)
            content = response.choices[0].message.content if response.choices else None
            model_name = (response.model or settings.openai_model) if response else settings.openai_model
    except (APITimeoutError, AnthropicTimeoutError) as exc:
        raise upstream_timeout("timed out while calling the AI provider") from exc
    except AnthropicStatusError as exc:
        raise internal_error(_anthropic_error_message(exc)) from exc
    except OpenAIError as exc:
        raise internal_error(f"AI provider request failed: {exc}") from exc

    if not content:
        raise malformed_ai("AI provider returned an empty response")

    try:
        payload = parse_model_json(content)
    except json.JSONDecodeError as exc:
        raise malformed_ai("AI provider returned invalid JSON") from exc

    try:
        extraction = Extraction.model_validate(payload)
    except ValidationError as exc:
        raise malformed_ai("AI provider JSON did not match the extraction schema") from exc

    return extraction, model_name, False


def _build_client(settings: Settings) -> OpenAI:
    kwargs: dict[str, Any] = {
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout_seconds,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url.rstrip("/")
    return OpenAI(**kwargs)


def _create_completion(openai_client: OpenAI, settings: Settings, text: str, url: str):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Source URL: {url}\n\nPage text:\n{text}",
        },
    ]
    try:
        return openai_client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except OpenAIError as exc:
        message = str(exc).lower()
        if "response_format" not in message and "json_object" not in message:
            raise
        return openai_client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
        )


def parse_model_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def uses_anthropic(settings: Settings) -> bool:
    host = urlparse(settings.openai_base_url).netloc.lower()
    return "agentrouter.org" in host


def anthropic_base_url(raw: str) -> str:
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return "https://agentrouter.org"
    return f"{parsed.scheme}://{parsed.netloc}"


def _complete_with_anthropic(
    settings: Settings,
    text: str,
    url: str,
    *,
    client: Anthropic | None = None,
) -> tuple[str, str]:
    anthropic_client = client or Anthropic(
        api_key=settings.openai_api_key,
        base_url=anthropic_base_url(settings.openai_base_url),
        timeout=settings.openai_timeout_seconds,
    )
    last_error: AnthropicStatusError | None = None
    for attempt in range(3):
        try:
            message = anthropic_client.messages.create(
                model=settings.openai_model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Source URL: {url}\n\nPage text:\n{text}",
                    }
                ],
            )
            parts = [
                block.text
                for block in message.content
                if getattr(block, "type", None) == "text" or hasattr(block, "text")
            ]
            content = "".join(parts)
            return content, message.model or settings.openai_model
        except AnthropicStatusError as exc:
            last_error = exc
            if exc.status_code != 503 or attempt == 2:
                raise
            time.sleep(1.5)
    assert last_error is not None
    raise last_error


def _anthropic_error_message(exc: AnthropicStatusError) -> str:
    body = ""
    try:
        payload = exc.response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                body = str(error.get("message") or "")
            elif isinstance(error, str):
                body = error
            if not body:
                body = str(payload.get("message") or "")
    except Exception:
        body = (exc.response.text or "")[:300]
    if exc.status_code == 503:
        return body or "AI provider has no available channel for this model"
    if body:
        return f"AI provider request failed: {body}"
    return f"AI provider request failed: {exc}"
