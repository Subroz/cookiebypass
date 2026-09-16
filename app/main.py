from contextlib import asynccontextmanager
from time import time
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import require_admin_key, require_api_key
from app.config import settings
from app.models import (
    CookieStatus,
    DirectUrlResponse,
    ErrorResponse,
    HealthDiagnostics,
    MediaMetadata,
    MediaRequest,
)
from app.services.extractor import ExtractionError, ExtractorService


extractor = ExtractorService()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await extractor.close()


app = FastAPI(title="Authorized Media Extraction API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID", uuid4().hex)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(ExtractionError)
async def extraction_error_handler(request: Request, exc: ExtractionError):
    status = 422 if exc.code in {"UNSUPPORTED_PLATFORM", "FORMAT_NOT_FOUND", "UNSUPPORTED_MEDIA"} else 502
    if exc.code == "AUTH_REQUIRED":
        status = 424
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(error=exc.code, detail=exc.detail, request_id=request.state.request_id).model_dump(),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "media-extraction-api", "time": int(time())}


@app.get("/health/diagnostics", response_model=HealthDiagnostics)
async def health_diagnostics():
    return await extractor.diagnostics()


@app.get("/")
async def root():
    return {
        "service": "media-extraction-api",
        "status": "ok",
        "metadata_endpoint": "/v1/metadata",
        "direct_url_endpoint": "/v1/direct-url",
        "vercel_proxy": "/api/test",
    }


@app.post("/v1/metadata", response_model=MediaMetadata, dependencies=[Depends(require_api_key)])
async def metadata(payload: MediaRequest):
    return await extractor.metadata(str(payload.url))


@app.post("/v1/direct-url", response_model=DirectUrlResponse, dependencies=[Depends(require_api_key)])
async def direct_url(payload: MediaRequest):
    return await extractor.direct_url(str(payload.url), payload.format_id)


@app.get("/v1/cookies/status", response_model=list[CookieStatus], dependencies=[Depends(require_admin_key)])
async def cookie_status():
    return extractor.cookie_status()
