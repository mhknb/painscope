from __future__ import annotations

import base64
import binascii
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from painscope.config import get_settings
from painscope.storage import get_scan, list_scans
from painscope.topics import list_available_profiles, load_profile
from painscope.web.jobs import ScanJobRunner
from painscope.web.schemas import JobSnapshot, StartScanRequest, StartScanResponse

STATIC_DIR = Path(__file__).parent / "static"


def create_app(job_runner: ScanJobRunner | None = None) -> FastAPI:
    runner = job_runner or ScanJobRunner()
    web_password = get_settings().web_password

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        app.state.job_runner = runner
        yield
        runner.shutdown()

    app = FastAPI(title="Painscope Web", version="0.1.0", lifespan=lifespan)
    app.state.job_runner = runner

    @app.middleware("http")
    async def require_basic_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        if not web_password or request.url.path == "/api/health":
            return await call_next(request)

        if _authorized(request, web_password):
            return await call_next(request)

        return JSONResponse(
            {"detail": "Authentication required."},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Painscope"'},
        )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        settings = get_settings()
        return {
            "ok": True,
            "web_auth_enabled": bool(settings.web_password),
        }

    @app.get("/api/profiles")
    def profiles() -> dict[str, list[dict[str, Any]]]:
        items: list[dict[str, Any]] = []
        for name in list_available_profiles():
            try:
                config = load_profile(name)
            except Exception:
                continue
            items.append(
                {
                    "name": name,
                    "title": config.name,
                    "description": config.description,
                    "language": config.language,
                    "scan_type": config.scan_type,
                    "limit_per_source": config.limit_per_source,
                    "top_n": config.top_n,
                    "source_count": len(config.sources),
                    "sources": [
                        {
                            "type": source.type,
                            "target": source.target,
                            "label": source.resolved_label,
                            "language": source.language or config.language,
                            "limit": source.limit or config.limit_per_source,
                        }
                        for source in config.sources
                    ],
                }
            )
        return {"profiles": items}

    @app.post("/api/scans", response_model=StartScanResponse, status_code=202)
    def start_scan(payload: StartScanRequest, request: Request) -> StartScanResponse:
        try:
            snapshot = request.app.state.job_runner.start(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return StartScanResponse(job_id=snapshot.job_id, status=snapshot.status)

    @app.get("/api/jobs/{job_id}", response_model=JobSnapshot)
    def get_job(
        request: Request,
        job_id: str = PathParam(pattern=r"^[A-Fa-f0-9]{32}$"),
    ) -> JobSnapshot:
        snapshot = request.app.state.job_runner.get(job_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return snapshot

    @app.get("/api/scans")
    def scans(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, list[dict[str, Any]]]:
        return {"scans": list_scans(limit=limit)}

    @app.get("/api/scans/{scan_id}")
    def scan_detail(
        scan_id: str = PathParam(pattern=r"^[A-Za-z0-9_.-]+$"),
    ) -> dict[str, Any]:
        scan = get_scan(scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        return scan

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


def _authorized(request: Request, expected_password: str) -> bool:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("basic "):
        return False

    try:
        encoded = header.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, IndexError):
        return False

    _, _, supplied_password = decoded.partition(":")
    return secrets.compare_digest(supplied_password, expected_password)

