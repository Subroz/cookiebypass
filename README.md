# Media Extraction API

FastAPI service for an existing bot to retrieve metadata and short-lived direct media URLs from authorized YouTube, TikTok, Instagram, and Facebook URLs.

The service runs yt-dlp on a persistent VPS. It supports operator-managed Netscape cookie files, but cookies do not guarantee access: platforms can still reject datacenter IPs, expire sessions, require additional verification, or restrict content.

For Vercel-only metadata extraction, use `POST /api/metadata.py`. This function runs yt-dlp directly in Vercel and does not require a VPS URL.

## Run locally

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Metadata request:

```powershell
$headers = @{ Authorization = "Bearer $env:API_KEY" }
$body = @{ url = "https://www.youtube.com/watch?v=VIDEO_ID" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/v1/metadata -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

Direct URL request:

```powershell
$body = @{ url = "https://www.youtube.com/watch?v=VIDEO_ID"; format_id = "18" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/v1/direct-url -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

Direct URLs are signed by the source and may expire quickly. Request them immediately before the bot sends or streams the media.

## Cookie files

Create a private `cookies` directory on the VPS and mount these files as read-only:

```text
cookies/youtube.txt
cookies/tiktok.txt
cookies/instagram.txt
cookies/facebook.txt
```

The files must be in Netscape cookies format and should be exported only from accounts and content you are authorized to use. Never commit them, paste them into API requests, or print them in logs.

Check file presence with the admin key:

```text
GET /v1/cookies/status
Authorization: Bearer <ADMIN_KEY>
```

Cookie rotation is a VPS deployment operation. Replace the appropriate file, preserve its permissions, and restart the container if your deployment requires it.

## Docker / VPS

```powershell
Copy-Item .env.example .env
# Edit .env and set long random API_KEY and ADMIN_KEY values.
New-Item -ItemType Directory -Force cookies
docker compose up -d --build
```

Put HTTPS in front of the container using a reverse proxy such as Caddy or nginx. Do not expose the container directly to the public internet without TLS and API-key protection.

The container runs as a non-root user, mounts cookies read-only, and includes ffmpeg for extractor workflows that need it. The service intentionally does not proxy large media files; it returns source URLs instead.

## Vercel testing

Vercel is supported only as a thin test proxy. It is not a suitable place to run yt-dlp or persist cookies because serverless functions have execution, storage, and response limits.

The repository also includes a direct Vercel metadata function. Configure `API_KEY` optionally, then call:

```text
POST https://your-project.vercel.app/api/metadata.py
Content-Type: application/json
Authorization: Bearer <API_KEY>

{"url":"https://youtu.be/VIDEO_ID"}
```

Optional Vercel environment variables can contain Netscape cookie text for authorized access: `YOUTUBE_COOKIES`, `TIKTOK_COOKIES`, `INSTAGRAM_COOKIES`, and `FACEBOOK_COOKIES`. These are written only to the function's temporary filesystem and are not returned.

For authorized network routing, configure `EXTRACTOR_PROXY` in Vercel, for example `http://user:password@host:port`. The proxy value is read only from the environment and is never hardcoded or returned. Rotate the proxy credential if it is exposed.

Deploy the `api/test.js` function and configure these Vercel environment variables:

```text
MEDIA_API_URL=https://api.example.com
MEDIA_API_KEY=<same key configured on the VPS>
```

Send the same JSON body used by `/v1/metadata` to `/api/test`. Keep the API key server-side; never expose it in browser JavaScript.

The Vercel proxy health check is available at `/api/test.js` with `GET`. The VPS API health check is available at `/health` on the VPS domain.

## Existing bot integration

The bot should call the VPS API with a server-side key:

```python
async with session.post(
    f"{MEDIA_API_URL}/v1/metadata",
    headers={"Authorization": f"Bearer {MEDIA_API_KEY}"},
    json={"url": source_url},
) as response:
    response.raise_for_status()
    metadata = await response.json()
```

Then call `/v1/direct-url` immediately before sending media. Handle these API error codes explicitly:

- `AUTH_REQUIRED`: the platform rejected the request or cookies are missing/expired.
- `MEDIA_UNAVAILABLE`: the URL is private or unavailable.
- `UNSUPPORTED_PLATFORM`: the URL is outside the four configured platforms.
- `EXTRACTION_TIMEOUT`: the VPS extractor exceeded its configured time limit.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The tests mock yt-dlp-facing service calls. A real platform test should use a public or explicitly authorized URL and should be run only against the deployed VPS.