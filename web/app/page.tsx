"use client";

import { FormEvent, useState } from "react";

type Entities = {
  people: string[];
  organizations: string[];
  locations: string[];
};

type ExtractSuccess = {
  source: {
    url: string;
    fetchedAt: string;
    contentType: string;
    truncated: boolean;
  };
  extraction: {
    title: string;
    summary: string;
    topics: string[];
    entities: Entities;
    keyFacts: string[];
  };
  meta: {
    model: string;
    mock: boolean;
  };
};

type ExtractError = {
  error: {
    code: string;
    message: string;
  };
};

const SAMPLE_URL = "https://example.com/";

function ChipList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <p>None found.</p>;
  }
  return (
    <ul className="chips">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export default function HomePage() {
  const [url, setUrl] = useState(SAMPLE_URL);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExtractSuccess | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/api/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const body = (await response.json()) as ExtractSuccess | ExtractError;
      if (!response.ok || "error" in body) {
        const err = body as ExtractError;
        setError(err.error?.message ?? "Extraction failed.");
        return;
      }
      setResult(body);
    } catch {
      setError("Could not reach the API. Confirm the Node and Python services are running.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <section className="hero">
        <p className="kicker">Local sample</p>
        <h1>AI data extraction pipeline</h1>
        <p className="lede">
          Submit a public webpage URL. The Node API validates the request, Python
          fetches the page, and GPT (or mock mode) returns structured metadata.
        </p>
      </section>

      <form onSubmit={onSubmit}>
        <label htmlFor="url">Source URL</label>
        <div className="row">
          <input
            id="url"
            type="url"
            required
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com/"
          />
          <button type="submit" disabled={loading}>
            {loading ? "Extracting…" : "Extract"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => setUrl(SAMPLE_URL)}
          >
            Use sample URL
          </button>
        </div>
        <p className="hint">
          Private, loopback, and metadata addresses are rejected. Mock mode does
          not need an OpenAI key.
        </p>
      </form>

      {error ? <div className="error">{error}</div> : null}

      {result ? (
        <section>
          <div className="meta-row">
            {result.meta.mock ? <span className="badge">Mock AI</span> : null}
            <span className="hint">
              Model: {result.meta.model}
              {result.source.truncated ? " · text truncated" : ""}
            </span>
          </div>
          <div className="grid">
            <article className="card">
              <h2>Title</h2>
              <p>{result.extraction.title}</p>
            </article>
            <article className="card">
              <h2>Summary</h2>
              <p>{result.extraction.summary}</p>
            </article>
            <article className="card">
              <h2>Topics</h2>
              <ChipList items={result.extraction.topics} />
            </article>
            <article className="card">
              <h2>People</h2>
              <ChipList items={result.extraction.entities.people} />
            </article>
            <article className="card">
              <h2>Organizations</h2>
              <ChipList items={result.extraction.entities.organizations} />
            </article>
            <article className="card">
              <h2>Locations</h2>
              <ChipList items={result.extraction.entities.locations} />
            </article>
            <article className="card">
              <h2>Key facts</h2>
              {result.extraction.keyFacts.length === 0 ? (
                <p>None found.</p>
              ) : (
                <ul className="facts">
                  {result.extraction.keyFacts.map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              )}
            </article>
          </div>
          <details>
            <summary>Raw JSON</summary>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </section>
      ) : null}
    </main>
  );
}
