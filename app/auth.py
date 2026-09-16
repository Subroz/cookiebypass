import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


def _check_key(value: str | None, expected: str, message: str) -> None:
    if not expected or not value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    _check_key(authorization, settings.api_key, "A valid API key is required")


def require_admin_key(authorization: str | None = Header(default=None)) -> None:
    _check_key(authorization, settings.admin_key, "A valid admin key is required")
