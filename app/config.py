from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str
    admin_key: str
    cookie_dir: Path
    request_timeout_seconds: int
    max_concurrent_jobs: int
    max_formats: int
    allowed_origins: tuple[str, ...]


def load_settings() -> Settings:
    origins = tuple(
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if origin.strip()
    )
    return Settings(
        api_key=os.getenv("API_KEY", ""),
        admin_key=os.getenv("ADMIN_KEY", ""),
        cookie_dir=Path(os.getenv("COOKIE_DIR", "/run/secrets/cookies")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "90")),
        max_concurrent_jobs=max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "2"))),
        max_formats=max(1, int(os.getenv("MAX_FORMATS", "40"))),
        allowed_origins=origins or ("*",),
    )


settings = load_settings()
