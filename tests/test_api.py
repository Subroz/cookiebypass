from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, extractor
from app.models import DirectUrlResponse, MediaMetadata


client = TestClient(app)
object.__setattr__(settings, "api_key", "test-key")
object.__setattr__(settings, "admin_key", "admin-key")


def test_health_is_public():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_route_requires_key():
    response = client.post("/v1/metadata", json={"url": "https://youtu.be/example"})
    assert response.status_code == 401


def test_metadata_uses_extractor(monkeypatch):
    async def fake_metadata(url: str):
        return MediaMetadata(platform="youtube", webpage_url=url, title="Example", formats=[])

    monkeypatch.setattr(extractor, "metadata", fake_metadata)
    response = client.post(
        "/v1/metadata",
        headers={"Authorization": "Bearer test-key"},
        json={"url": "https://youtu.be/example"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Example"


def test_invalid_url_is_rejected():
    response = client.post(
        "/v1/metadata",
        headers={"Authorization": "Bearer test-key"},
        json={"url": "file:///secret"},
    )
    assert response.status_code == 422


def test_direct_url_uses_requested_format(monkeypatch):
    async def fake_direct_url(url: str, format_id: str | None):
        assert format_id == "18"
        return DirectUrlResponse(
            platform="youtube",
            webpage_url=url,
            format_id="18",
            url="https://cdn.example/media.mp4",
            ext="mp4",
            title="Example",
        )

    monkeypatch.setattr(extractor, "direct_url", fake_direct_url)
    response = client.post(
        "/v1/direct-url",
        headers={"Authorization": "Bearer test-key"},
        json={"url": "https://youtu.be/example", "format_id": "18"},
    )
    assert response.status_code == 200
    assert response.json()["format_id"] == "18"


def test_admin_cookie_status_requires_admin_key(monkeypatch):
    monkeypatch.setattr(extractor, "cookie_status", lambda: [])
    response = client.get(
        "/v1/cookies/status",
        headers={"Authorization": "Bearer admin-key"},
    )
    assert response.status_code == 200
    assert response.json() == []
