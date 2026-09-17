from __future__ import annotations

import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import router
from .config import get_settings
from .database import SessionLocal, create_schema
from .schemas import HealthView
from .services.seed import seed_demo


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    create_schema()
    if settings.auto_seed:
        with SessionLocal() as session:
            seed_demo(session)
    yield


settings = get_settings()
app = FastAPI(
    title="Claim Power House API",
    version=__version__,
    description="Synthetic-data, human-in-the-loop multi-agent claim review API.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "X-CPH-User"],
)


@app.middleware("http")
async def sidecar_auth(request: Request, call_next):
    """Protect local sidecar API routes when the extension supplies a session token."""
    expected = settings.sidecar_token
    protected = request.url.path.startswith(("/api/", "/mcp"))
    if expected and protected:
        authorization = request.headers.get("authorization", "")
        bearer = (
            authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        )
        cookie = request.cookies.get("cph_sidecar", "")
        if not (hmac.compare_digest(bearer, expected) or hmac.compare_digest(cookie, expected)):
            return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return await call_next(request)


app.include_router(router)


@app.get("/health/live", response_model=HealthView)
def live() -> HealthView:
    return HealthView(status="ok", version=__version__, demo_mode=settings.demo_mode)


@app.get("/health/ready", response_model=HealthView)
def ready() -> HealthView:
    return HealthView(status="ok", version=__version__, demo_mode=settings.demo_mode)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Claim Power House",
        "version": __version__,
        "warning": "Synthetic demo only — not for clinical or payment use.",
        "docs": "/docs",
    }


@app.get("/sidecar-bootstrap")
def sidecar_bootstrap(token: str, claim_id: str | None = None) -> RedirectResponse:
    if not settings.sidecar_token or not hmac.compare_digest(token, settings.sidecar_token):
        raise HTTPException(status_code=401, detail="Invalid sidecar bootstrap token")
    target = "/app/" if not claim_id else f"/app/?claim_id={claim_id}"
    response = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        "cph_sidecar",
        token,
        httponly=True,
        samesite="strict",
        max_age=8 * 60 * 60,
        path="/",
    )
    return response


if settings.web_root.exists():
    app.mount("/app", StaticFiles(directory=settings.web_root, html=True), name="web")

try:
    from .mcp_server import mcp

    app.mount("/mcp", mcp.streamable_http_app(), name="mcp")
except ImportError:
    pass
