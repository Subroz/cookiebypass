import json
import os
from urllib.request import Request, urlopen


def handler(request):
    if request.method != "POST":
        return {"statusCode": 405, "body": "Method Not Allowed"}
    api_url = os.environ.get("MEDIA_API_URL", "").rstrip("/")
    api_key = os.environ.get("MEDIA_API_KEY", "")
    if not api_url or not api_key:
        return {"statusCode": 500, "body": "MEDIA_API_URL and MEDIA_API_KEY are required"}
    try:
        body = request.body
        if isinstance(body, str):
            body = body.encode()
        upstream = Request(
            f"{api_url}/v1/metadata",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(upstream, timeout=30) as response:
            result = response.read().decode()
            return {"statusCode": response.status, "headers": {"Content-Type": "application/json"}, "body": result}
    except Exception as exc:
        return {"statusCode": 502, "body": json.dumps({"error": "upstream_failed", "detail": str(exc)})}
