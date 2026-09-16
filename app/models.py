from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class MediaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    format_id: str | None = Field(default=None, max_length=80)


class FormatSummary(BaseModel):
    format_id: str
    ext: str | None = None
    resolution: str | None = None
    abr: float | None = None
    filesize: int | None = None
    has_video: bool = False
    has_audio: bool = False


class MediaMetadata(BaseModel):
    id: str | None = None
    platform: str
    webpage_url: str
    title: str | None = None
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    formats: list[FormatSummary] = Field(default_factory=list)


class DirectUrlResponse(BaseModel):
    platform: str
    webpage_url: str
    format_id: str
    url: str
    ext: str | None = None
    title: str | None = None
    expires_at: int | None = None
    note: str = "The media URL is signed by the source and may expire quickly."


class CookieStatus(BaseModel):
    platform: str
    configured: bool
    readable: bool
    path: str


class PlatformHealth(BaseModel):
    platform: str
    status: str
    endpoint: str
    http_status: int | None = None
    cookie_configured: bool = False
    likely_ip_block: bool = False
    detail: str


class HealthDiagnostics(BaseModel):
    status: str
    service: str
    checks: list[PlatformHealth] = Field(default_factory=list)
    checked_at: int


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str
    context: dict[str, Any] | None = None
