import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_POST(self) -> None:
        api_url = os.environ.get("MEDIA_API_URL", "").rstrip("/")
        api_key = os.environ.get("MEDIA_API_KEY", "")
        if not api_url or not api_key:
            self._send_json(500, {"error": "MEDIA_API_URL and MEDIA_API_KEY are required"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            json.loads(body)
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "Request body must be valid JSON"})
            return

        try:
            upstream = Request(
                f"{api_url}/v1/metadata",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urlopen(upstream, timeout=8) as response:
                result = response.read().decode("utf-8")
                response_body = json.loads(result)
                self._send_json(response.status, response_body)
        except Exception as exc:
            self._send_json(502, {"error": "upstream_failed", "detail": str(exc)})

    def do_GET(self) -> None:
        self._send_json(405, {"error": "Use POST /api/test"})
