export class AppError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "AppError";
  }
}

export function invalidInput(message: string): AppError {
  return new AppError("INVALID_INPUT", message, 400);
}

export function ssrfBlocked(message: string): AppError {
  return new AppError("SSRF_BLOCKED", message, 400);
}

export function extractorUnavailable(message: string): AppError {
  return new AppError("EXTRACTOR_UNAVAILABLE", message, 503);
}

export function upstreamTimeout(message: string): AppError {
  return new AppError("UPSTREAM_TIMEOUT", message, 504);
}

export function errorBody(code: string, message: string) {
  return { error: { code, message } };
}
