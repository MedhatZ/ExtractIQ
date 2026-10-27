import dotenv from "dotenv";

dotenv.config();

function numberEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) {
    return fallback;
  }
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
}

export const config = {
  port: numberEnv("API_PORT", 3001),
  pythonExtractorUrl: (
    process.env.PYTHON_EXTRACTOR_URL ?? "http://127.0.0.1:8000"
  ).replace(/\/$/, ""),
  extractorTimeoutMs: numberEnv("EXTRACTOR_TIMEOUT_MS", 30_000),
};
