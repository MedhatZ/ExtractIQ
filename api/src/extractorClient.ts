import { z } from "zod";

import { config } from "./config.js";
import {
  AppError,
  extractorUnavailable,
  upstreamTimeout,
} from "./errors.js";

const entitiesSchema = z.object({
  people: z.array(z.string()),
  organizations: z.array(z.string()),
  locations: z.array(z.string()),
});

const extractResponseSchema = z.object({
  source: z.object({
    url: z.string(),
    fetchedAt: z.string(),
    contentType: z.string(),
    truncated: z.boolean(),
  }),
  extraction: z.object({
    title: z.string(),
    summary: z.string(),
    topics: z.array(z.string()),
    entities: entitiesSchema,
    keyFacts: z.array(z.string()),
  }),
  meta: z.object({
    model: z.string(),
    mock: z.boolean(),
  }),
});

const errorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
  }),
});

export type ExtractResponse = z.infer<typeof extractResponseSchema>;

const PASS_THROUGH_CODES = new Set([
  "INVALID_INPUT",
  "SSRF_BLOCKED",
  "FETCH_FAILED",
  "UPSTREAM_TIMEOUT",
  "MALFORMED_AI_RESPONSE",
  "INTERNAL_ERROR",
]);

export async function callExtractor(
  url: string,
  options: {
    fetchImpl?: typeof fetch;
    extractorUrl?: string;
    timeoutMs?: number;
  } = {},
): Promise<ExtractResponse> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const extractorUrl = options.extractorUrl ?? config.pythonExtractorUrl;
  const timeoutMs = options.timeoutMs ?? config.extractorTimeoutMs;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetchImpl(`${extractorUrl}/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ url }),
      signal: controller.signal,
    });

    const text = await response.text();
    let parsed: unknown = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        throw new AppError(
          "MALFORMED_AI_RESPONSE",
          "extractor returned a non-JSON response",
          502,
        );
      }
    }

    if (!response.ok) {
      const err = errorSchema.safeParse(parsed);
      if (err.success && PASS_THROUGH_CODES.has(err.data.error.code)) {
        throw new AppError(err.data.error.code, err.data.error.message, response.status);
      }
      throw new AppError(
        "INTERNAL_ERROR",
        "extractor request failed",
        response.status >= 500 ? 502 : response.status,
      );
    }

    const success = extractResponseSchema.safeParse(parsed);
    if (!success.success) {
      throw new AppError(
        "MALFORMED_AI_RESPONSE",
        "extractor response did not match the expected schema",
        502,
      );
    }
    return success.data;
  } catch (error) {
    if (error instanceof AppError) {
      throw error;
    }
    if (error instanceof Error && error.name === "AbortError") {
      throw upstreamTimeout("timed out waiting for the extraction service");
    }
    throw extractorUnavailable("extraction service is unavailable");
  } finally {
    clearTimeout(timer);
  }
}
