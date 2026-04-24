from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from painscope import config as config_module
from painscope.web import app as web_app
from painscope.web.schemas import JobSnapshot


def _reset_settings(monkeypatch, tmp_path, *, password: str | None = None) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    if password is None:
        monkeypatch.delenv("PAINSCOPE_WEB_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("PAINSCOPE_WEB_PASSWORD", password)
    monkeypatch.setattr(config_module, "_settings", None)


def test_health_and_profiles(monkeypatch, tmp_path):
    _reset_settings(monkeypatch, tmp_path)
    client = TestClient(web_app.create_app())

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    profiles = client.get("/api/profiles")
    assert profiles.status_code == 200
    names = {profile["name"] for profile in profiles.json()["profiles"]}
    assert {"tr", "global"}.issubset(names)


def test_start_scan_uses_job_runner(monkeypatch, tmp_path):
    _reset_settings(monkeypatch, tmp_path)

    class FakeRunner:
        def start(self, request):
            assert request.profile == "tr"
            return JobSnapshot(
                job_id="job-1",
                status="queued",
                created_at="2026-04-25T00:00:00+00:00",
                topic_name="Turkish Sources",
            )

        def get(self, job_id):
            return None

        def shutdown(self):
            return None

    client = TestClient(web_app.create_app(job_runner=FakeRunner()))

    response = client.post(
        "/api/scans",
        json={"profile": "tr", "scan_type": "pain_points", "language": "tr"},
    )

    assert response.status_code == 202
    assert response.json() == {"job_id": "job-1", "status": "queued"}


def test_optional_basic_auth_protects_web(monkeypatch, tmp_path):
    _reset_settings(monkeypatch, tmp_path, password="secret")
    client = TestClient(web_app.create_app())

    assert client.get("/").status_code == 401

    token = base64.b64encode(b"painscope:secret").decode("ascii")
    response = client.get("/", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 200

