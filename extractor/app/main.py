from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import AppError
from app.extract import extract_from_url
from app.models import ErrorBody, ErrorResponse, ExtractRequest

app = FastAPI(title="AI Extraction Service", version="1.0.0")


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(error=ErrorBody(code=code, message=message)).model_dump(),
    )


@app.exception_handler(AppError)
async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return error_response(400, "INVALID_INPUT", "request body is invalid")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract")
def extract(payload: ExtractRequest):
    return extract_from_url(payload.url)
