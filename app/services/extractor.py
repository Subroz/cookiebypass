import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yt_dlp

from app.config import settings
from app.models import (
    DirectUrlResponse,
    FormatSummary,
    HealthDiagnostics,
    MediaMetadata,
    PlatformHealth,
)


PLATFORM_HOSTS: dict[str, tuple[str, ...]] = {
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.watch"),
}

PLATFORM_HEALTH_URLS = {
    "youtube": "https://www.youtube.com/generate_204",
    "tiktok": "https://www.tiktok.com/",
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/",
}


class ExtractionError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ExtractorService:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs)
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    async def metadata(self, url: str) -> MediaMetadata:
        info = await self._extract(url, download=False)
        return self._metadata_from_info(url, info)

    async def direct_url(self, url: str, format_id: str | None) -> DirectUrlResponse:
        info = await self._extract(url, download=False)
        selected = self._select_format(info, format_id)
        direct_url = selected.get("url")
        if not direct_url:
            raise ExtractionError("FORMAT_UNAVAILABLE", "No direct URL was returned for this format")
        return DirectUrlResponse(
            platform=self.platform_for_url(url),
            webpage_url=url,
            format_id=str(selected.get("format_id", "unknown")),
            url=direct_url,
            ext=selected.get("ext"),
            title=info.get("title"),
            expires_at=selected.get("expiry") or selected.get("expires_at"),
        )

    def cookie_status(self) -> list[dict[str, str | bool]]:
        result = []
        for platform in PLATFORM_HOSTS:
            path = self.cookie_path(platform)
            result.append({
                "platform": platform,
                "configured": path is not None,
                "readable": bool(path and os.access(path, os.R_OK)),
                "path": str(path or self.cookie_dir / f"{platform}.txt"),
            })
        return result

    async def diagnostics(self) -> HealthDiagnostics:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=min(settings.request_timeout_seconds, 4),
            headers={"User-Agent": "media-extraction-api/1.0"},
        ) as client:
            checks = await asyncio.gather(
                *(
                    self._probe_platform(client, platform, endpoint)
                    for platform, endpoint in PLATFORM_HEALTH_URLS.items()
                )
            )

        failed = [check for check in checks if check.status != "ok"]
        return HealthDiagnostics(
            status="ok" if not failed else "degraded",
            service="media-extraction-api",
            checks=checks,
            checked_at=int(__import__("time").time()),
        )

    async def _probe_platform(
        self, client: httpx.AsyncClient, platform: str, endpoint: str
    ) -> PlatformHealth:
        cookie_configured = self.cookie_path(platform) is not None
        try:
            response = await client.get(endpoint)
        except httpx.TimeoutException:
            return PlatformHealth(
                platform=platform,
                status="network_error",
                endpoint=endpoint,
                cookie_configured=cookie_configured,
                detail="The platform probe timed out",
            )
        except httpx.HTTPError as exc:
            return PlatformHealth(
                platform=platform,
                status="network_error",
                endpoint=endpoint,
                cookie_configured=cookie_configured,
                detail=f"The platform probe failed: {type(exc).__name__}",
            )

        if 200 <= response.status_code < 400:
            return PlatformHealth(
                platform=platform,
                status="ok",
                endpoint=endpoint,
                http_status=response.status_code,
                cookie_configured=cookie_configured,
                detail="Platform endpoint is reachable from this server",
            )

        likely_block = response.status_code in {401, 403, 429, 451, 503}
        return PlatformHealth(
            platform=platform,
            status="possible_ip_block" if likely_block else "http_error",
            endpoint=endpoint,
            http_status=response.status_code,
            cookie_configured=cookie_configured,
            likely_ip_block=likely_block,
            detail=(
                "The platform rejected or rate-limited this server; this may be an IP, region, or authentication block"
                if likely_block
                else "The platform returned an unexpected HTTP status"
            ),
        )

    async def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def _extract(self, url: str, download: bool) -> dict:
        platform = self.platform_for_url(url)
        options = self._options(platform, download)
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(self._executor, self._extract_sync, url, options),
                    timeout=settings.request_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise ExtractionError("EXTRACTION_TIMEOUT", "The extractor timed out") from exc
            except yt_dlp.utils.DownloadError as exc:
                raise self._map_error(str(exc)) from exc
            except ExtractionError:
                raise
            except Exception as exc:
                raise ExtractionError("EXTRACTION_FAILED", "The extractor failed") from exc

    @staticmethod
    def _extract_sync(url: str, options: dict) -> dict:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ExtractionError("NO_RESULT", "No media information was returned")
            return info

    def _options(self, platform: str, download: bool) -> dict:
        options: dict = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": settings.request_timeout_seconds,
            "retries": 2,
            "extract_flat": False,
            "skip_download": not download,
        }
        cookie_path = self.cookie_path(platform)
        if cookie_path:
            options["cookiefile"] = str(cookie_path)
        return options

    @property
    def cookie_dir(self) -> Path:
        return settings.cookie_dir

    def cookie_path(self, platform: str) -> Path | None:
        path = self.cookie_dir / f"{platform}.txt"
        return path if path.is_file() else None

    @staticmethod
    def platform_for_url(url: str) -> str:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        for platform, hosts in PLATFORM_HOSTS.items():
            if any(host == item or host.endswith(f".{item}") for item in hosts):
                return platform
        raise ExtractionError("UNSUPPORTED_PLATFORM", "Only YouTube, TikTok, Instagram, and Facebook URLs are supported")

    def _metadata_from_info(self, url: str, info: dict) -> MediaMetadata:
        formats: list[FormatSummary] = []
        for item in info.get("formats", [])[-settings.max_formats:]:
            formats.append(FormatSummary(
                format_id=str(item.get("format_id", "unknown")),
                ext=item.get("ext"),
                resolution=item.get("resolution") or item.get("format_note"),
                abr=item.get("abr"),
                filesize=item.get("filesize") or item.get("filesize_approx"),
                has_video=bool(item.get("vcodec") not in (None, "none")),
                has_audio=bool(item.get("acodec") not in (None, "none")),
            ))
        return MediaMetadata(
            id=info.get("id"),
            platform=self.platform_for_url(url),
            webpage_url=info.get("webpage_url") or url,
            title=info.get("title"),
            uploader=info.get("uploader") or info.get("channel"),
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            formats=formats,
        )

    @staticmethod
    def _select_format(info: dict, format_id: str | None) -> dict:
        formats = [item for item in info.get("formats", []) if item.get("url")]
        if format_id:
            for item in formats:
                if str(item.get("format_id")) == format_id:
                    return item
            raise ExtractionError("FORMAT_NOT_FOUND", f"Format '{format_id}' was not found")
        if not formats:
            raise ExtractionError("FORMAT_UNAVAILABLE", "No direct media formats were returned")
        return max(formats, key=lambda item: (bool(item.get("vcodec") not in (None, "none")), item.get("height") or 0, item.get("tbr") or 0))

    @staticmethod
    def _map_error(message: str) -> ExtractionError:
        lowered = message.lower()
        if "sign in" in lowered or "login" in lowered or "cookies" in lowered or "not a bot" in lowered:
            return ExtractionError("AUTH_REQUIRED", "The platform requires valid session cookies or rejected this server request")
        if "private" in lowered or "unavailable" in lowered:
            return ExtractionError("MEDIA_UNAVAILABLE", "The media is private or unavailable")
        if "unsupported" in lowered:
            return ExtractionError("UNSUPPORTED_MEDIA", "The URL is not supported by the extractor")
        return ExtractionError("EXTRACTION_FAILED", "The platform extractor failed")
