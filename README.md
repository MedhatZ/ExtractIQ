# AI Data Extraction Pipeline (local sample)

A small, local GitHub sample that turns a public webpage URL into structured JSON. The UI is Next.js, the coordinator is a Node.js API, and content plus GPT extraction run in Python.

This repository is source code for local development and automated tests. It is not a hosted product.

## Architecture

```
Browser (Next.js :3000)
    POST /api/extract
            |
            v
Node.js API (:3001)     validates input, enforces timeout
            POST /extract
            |
            v
Python FastAPI (:8000)  SSRF-safe fetch, HTML-to-text, GPT or mock
            |
            +--> public http(s) page
            +--> OpenAI Chat Completions (unless MOCK_AI=true)
```

| Service | Directory | Role |
| --- | --- | --- |
| Web UI | `web/` | Form to submit a URL and render extraction results |
| Node API | `api/` | Input validation, timeout, error mapping, Python client |
| Extractor | `extractor/` | URL fetch, HTML text extraction, structured GPT output |

## Data flow

1. The UI posts `{ "url": "https://example.com/" }` to `/api/extract`. Next.js rewrites that path to the Node API.
2. Node validates the body with Zod, rejects non-http(s) URLs, credentials-in-URL, localhost, and private IP literals, then calls Python with a hard timeout.
3. Python parses the URL again, resolves DNS, and blocks loopback, RFC1918, link-local, CGNAT, multicast, and metadata-style hosts. Redirects are followed one hop at a time and re-validated. The response body is size-capped.
4. Visible HTML text is extracted and truncated, then sent to OpenAI with `response_format: json_object`, or replaced by a deterministic mock when `MOCK_AI=true`.
5. The model JSON is validated against the extraction schema. Invalid JSON or missing fields return `MALFORMED_AI_RESPONSE`.

Extraction schema:

```json
{
  "title": "string",
  "summary": "string",
  "topics": ["string"],
  "entities": {
    "people": [],
    "organizations": [],
    "locations": []
  },
  "keyFacts": ["string"]
}
```

Error shape for both APIs:

```json
{ "error": { "code": "INVALID_INPUT", "message": "..." } }
```

Codes: `INVALID_INPUT`, `SSRF_BLOCKED`, `FETCH_FAILED`, `UPSTREAM_TIMEOUT`, `EXTRACTOR_UNAVAILABLE`, `MALFORMED_AI_RESPONSE`, `INTERNAL_ERROR`.

## Prerequisites

- Node.js 20+
- Python 3.11+
- An OpenAI API key only if you set `MOCK_AI=false`

## Local setup

Use three terminals. Mock mode is the default and does not need a key. Fetching the source URL still happens.

```bash
cp .env.example extractor/.env
cp .env.example api/.env
cp web/.env.example web/.env.local
```

Python extractor:

```bash
cd extractor
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Node API:

```bash
cd api
npm install
npm run dev
```

Next.js UI:

```bash
cd web
npm install
npm run dev
```

Open http://127.0.0.1:3000, keep the sample URL or paste another public http(s) URL, and choose Extract.

To call a real model, set these in `extractor/.env` and restart the Python process:

```
MOCK_AI=false
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_MODEL=your-model-id
```

`OPENAI_BASE_URL` is optional. Leave it empty to use the official OpenAI API. OpenAI-compatible gateways should set it. AgentRouter Claude models (`agentrouter.org`) use the Anthropic Messages API automatically. Do not commit real keys.

## Testing

Extractor (no network, no API key):

```bash
cd extractor
pytest
```

Node API:

```bash
cd api
npm test
```

Web production build check:

```bash
cd web
npm run build
```

The tests cover successful mock extraction, invalid input, SSRF-blocked URLs, extractor/fetch/provider failures, timeouts, and malformed AI JSON.

## Limitations

- Local sample only. Nothing here was deployed, load-tested, or run as a production service.
- Mock mode exercises the pipeline without OpenAI. Live model quality, cost, and latency were not measured in this repository.
- SSRF checks are a focused defense (scheme, credentials, hostname, resolved IP, redirect re-validation, size and time limits). They are not a full network policy or WAF.
- Only public `http`/`https` URLs are accepted. There is no file upload, crawl, auth, queue, or persistence.
- HTML-to-text is a simple BeautifulSoup pass. JavaScript-rendered pages and binary documents are out of scope.
- Default bind addresses are localhost. Do not expose these processes to the internet as-is.
