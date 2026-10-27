class AppError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def invalid_input(message: str) -> AppError:
    return AppError("INVALID_INPUT", message, 400)


def ssrf_blocked(message: str) -> AppError:
    return AppError("SSRF_BLOCKED", message, 400)


def fetch_failed(message: str) -> AppError:
    return AppError("FETCH_FAILED", message, 502)


def upstream_timeout(message: str) -> AppError:
    return AppError("UPSTREAM_TIMEOUT", message, 504)


def malformed_ai(message: str) -> AppError:
    return AppError("MALFORMED_AI_RESPONSE", message, 502)


def internal_error(message: str) -> AppError:
    return AppError("INTERNAL_ERROR", message, 500)
