import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

PLATFORM_HOSTS = {
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.watch"),
}


def platform_for_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for platform, hosts in PLATFORM_HOSTS.items():
        if any(host == item or host.endswith(f".{item}") for item in hosts):
            return platform
    raise ValueError("Only YouTube, TikTok, Instagram, and Facebook URLs are supported")


def cookie_file(platform: str) -> str | None:
    value = os.environ.get(f"{platform.upper()}_COOKIES", "").strip()
    if not value:
        return None
    path = Path(tempfile.gettempdir()) / f"{platform}_cookies.txt"
    path.write_text(value, encoding="utf-8")
    return str(path)


def extract_metadata(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError(
            "yt-dlp is not installed in the Vercel Python runtime"
        ) from exc

    platform = platform_for_url(url)
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 8,
        "retries": 1,
    }
    proxy = os.environ.get("EXTRACTOR_PROXY") or os.environ.get("HTTPS_PROXY")
    if proxy:
        options["proxy"] = proxy
    cookies = cookie_file(platform)
    if cookies:
        options["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)

    formats = []
    for item in (info.get("formats") or [])[-40:]:
        formats.append(
            {
                "format_id": str(item.get("format_id", "unknown")),
                "ext": item.get("ext"),
                "resolution": item.get("resolution") or item.get("format_note"),
                "filesize": item.get("filesize") or item.get("filesize_approx"),
                "has_video": item.get("vcodec") not in (None, "none"),
                "has_audio": item.get("acodec") not in (None, "none"),
                "url": item.get("url"),
            }
        )

    return {
        "id": info.get("id"),
        "platform": platform,
        "webpage_url": info.get("webpage_url") or url,
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "formats": formats,
    }


class handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        expected_key = os.environ.get("API_KEY", "")
        supplied_key = self.headers.get("Authorization", "")
        if expected_key and supplied_key != f"Bearer {expected_key}":
            self._json(401, {"error": "A valid API key is required"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            url = payload.get("url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                raise ValueError("Request must contain an HTTP(S) url")
            result = extract_metadata(url)
            self._json(200, result)
        except ValueError as exc:
            self._json(422, {"error": "invalid_request", "detail": str(exc)})
        except Exception as exc:
            message = str(exc).lower()
            if "no module named" in message and "yt_dlp" in message:
                self._json(
                    502,
                    {
                        "error": "RUNTIME_DEPENDENCY_MISSING",
                        "detail": "yt-dlp is not installed in the Vercel Python runtime",
                    },
                )
                return
            code = "AUTH_REQUIRED" if any(
                text in message for text in ("sign in", "login", "cookies", "not a bot")
            ) else "EXTRACTION_FAILED"
            self._json(502, {"error": code, "detail": str(exc)[-1000:]})

    def do_GET(self) -> None:
        self._json(405, {"error": "Use POST /api/metadata.py"})
