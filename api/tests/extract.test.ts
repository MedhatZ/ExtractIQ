import { afterEach, describe, expect, it, vi } from "vitest";
import request from "supertest";

import { createApp } from "../src/app.js";
import { AppError } from "../src/errors.js";
import { callExtractor } from "../src/extractorClient.js";
import { validateExtractInput } from "../src/validate.js";

const successPayload = {
  source: {
    url: "https://example.com/",
    fetchedAt: "2026-01-01T00:00:00+00:00",
    contentType: "text/html",
    truncated: false,
  },
  extraction: {
    title: "Example Domain",
    summary: "This domain is for use in documentation examples.",
    topics: ["sample", "extraction"],
    entities: { people: [], organizations: [], locations: [] },
    keyFacts: ["Source URL: https://example.com/"],
  },
  meta: { model: "mock", mock: true },
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("validateExtractInput", () => {
  it("accepts a public https URL", () => {
    expect(validateExtractInput({ url: "https://example.com/page" }).url).toContain(
      "example.com",
    );
  });

  it("rejects missing url", () => {
    expect(() => validateExtractInput({})).toThrow(/url is required/);
  });

  it("rejects non-http schemes", () => {
    expect(() => validateExtractInput({ url: "file:///etc/passwd" })).toThrow(
      /only http and https/,
    );
  });

  it("rejects loopback and private hosts", () => {
    expect(() => validateExtractInput({ url: "http://127.0.0.1/admin" })).toThrow(
      /not allowed/,
    );
    expect(() => validateExtractInput({ url: "http://localhost/admin" })).toThrow(
      /not allowed/,
    );
    expect(() => validateExtractInput({ url: "http://192.168.0.10/" })).toThrow(
      /not allowed/,
    );
  });
});

describe("POST /extract", () => {
  it("returns structured extraction on success", async () => {
    const app = createApp({
      callExtractor: async () => successPayload,
    });
    const response = await request(app)
      .post("/extract")
      .send({ url: "https://example.com/" });
    expect(response.status).toBe(200);
    expect(response.body.extraction.title).toBe("Example Domain");
    expect(response.body.meta.mock).toBe(true);
  });

  it("rejects invalid input", async () => {
    const app = createApp();
    const response = await request(app).post("/extract").send({});
    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe("INVALID_INPUT");
  });

  it("rejects SSRF targets before calling Python", async () => {
    const spy = vi.fn();
    const app = createApp({ callExtractor: spy });
    const response = await request(app)
      .post("/extract")
      .send({ url: "http://127.0.0.1/" });
    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe("SSRF_BLOCKED");
    expect(spy).not.toHaveBeenCalled();
  });

  it("maps extractor unavailability", async () => {
    const app = createApp({
      callExtractor: async () => {
        throw new AppError("EXTRACTOR_UNAVAILABLE", "down", 503);
      },
    });
    const response = await request(app)
      .post("/extract")
      .send({ url: "https://example.com/" });
    expect(response.status).toBe(503);
    expect(response.body.error.code).toBe("EXTRACTOR_UNAVAILABLE");
  });

  it("maps extractor timeout", async () => {
    const app = createApp({
      callExtractor: async () => {
        throw new AppError("UPSTREAM_TIMEOUT", "slow", 504);
      },
    });
    const response = await request(app)
      .post("/extract")
      .send({ url: "https://example.com/" });
    expect(response.status).toBe(504);
    expect(response.body.error.code).toBe("UPSTREAM_TIMEOUT");
  });

  it("maps malformed AI responses", async () => {
    const app = createApp({
      callExtractor: async () => {
        throw new AppError("MALFORMED_AI_RESPONSE", "bad json", 502);
      },
    });
    const response = await request(app)
      .post("/extract")
      .send({ url: "https://example.com/" });
    expect(response.status).toBe(502);
    expect(response.body.error.code).toBe("MALFORMED_AI_RESPONSE");
  });
});

describe("callExtractor", () => {
  it("parses a successful extractor payload", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify(successPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    const result = await callExtractor("https://example.com/", {
      fetchImpl,
      extractorUrl: "http://extractor.test",
    });
    expect(result.extraction.title).toBe("Example Domain");
  });

  it("treats a down service as EXTRACTOR_UNAVAILABLE", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;

    await expect(
      callExtractor("https://example.com/", {
        fetchImpl,
        extractorUrl: "http://extractor.test",
      }),
    ).rejects.toMatchObject({ code: "EXTRACTOR_UNAVAILABLE", status: 503 });
  });

  it("treats abort as UPSTREAM_TIMEOUT", async () => {
    const fetchImpl = vi.fn(async () => {
      const error = new Error("aborted");
      error.name = "AbortError";
      throw error;
    }) as unknown as typeof fetch;

    await expect(
      callExtractor("https://example.com/", {
        fetchImpl,
        extractorUrl: "http://extractor.test",
      }),
    ).rejects.toMatchObject({ code: "UPSTREAM_TIMEOUT", status: 504 });
  });

  it("rejects malformed success JSON", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    await expect(
      callExtractor("https://example.com/", {
        fetchImpl,
        extractorUrl: "http://extractor.test",
      }),
    ).rejects.toMatchObject({ code: "MALFORMED_AI_RESPONSE", status: 502 });
  });

  it("passes through Python error codes", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(
        JSON.stringify({
          error: { code: "FETCH_FAILED", message: "could not fetch" },
        }),
        { status: 502, headers: { "Content-Type": "application/json" } },
      ),
    ) as unknown as typeof fetch;

    await expect(
      callExtractor("https://example.com/", {
        fetchImpl,
        extractorUrl: "http://extractor.test",
      }),
    ).rejects.toMatchObject({ code: "FETCH_FAILED" });
  });
});
