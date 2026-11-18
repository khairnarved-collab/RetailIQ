"""
RetailIQ API - FastAPI application entry point.

Run locally:   uvicorn app.main:app --reload        (from the backend/ folder)
API docs:      http://localhost:8000/docs           (interactive Swagger UI)
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, analytics, auth, datasets, operations
from app.core.config import settings
from app.core.logging import setup_logging
from app.database.session import SessionLocal

setup_logging()
log = logging.getLogger("retailiq")

app = FastAPI(
    title="RetailIQ API",
    description="Turn Retail Data Into Smarter Decisions - analytics, forecasting and inventory optimisation.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def security_headers_and_timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/api"):
        log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, ms)
    return response


# ---------------------------------------------------------------- error handling
@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    # Turn pydantic's error list into one readable message for the UI
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query"))
        msgs.append(f"{loc}: {e.get('msg', '').replace('Value error, ', '')}" if loc else e.get("msg", ""))
    return JSONResponse({"detail": "; ".join(msgs)}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)
    return JSONResponse({"detail": "An unexpected error occurred. The error has been logged."}, status_code=500)


# ---------------------------------------------------------------- routes
API = "/api"
for r in (auth.router, admin.router, datasets.router, analytics.router, operations.router):
    app.include_router(r, prefix=API)


@app.get("/api/health", tags=["system"])
def health():
    """Liveness + database connectivity check (used by Docker health checks)."""
    db_ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "connected" if db_ok else "unavailable",
            "database_engine": "sqlite" if settings.is_sqlite else "postgresql",
            "llm_assistant": settings.llm_provider or "rule-based", "version": app.version}


# ---------------------------------------------------------------- serve the built frontend (optional)
# In the single-container deployment the React build is copied next to the API,
# so one URL serves both. In development Vite serves the frontend instead.
if settings.FRONTEND_DIST and Path(settings.FRONTEND_DIST).exists():
    dist = Path(settings.FRONTEND_DIST)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            headers = {"Cache-Control": "no-cache"} if full_path in ("sw.js", "manifest.webmanifest") else None
            return FileResponse(candidate, headers=headers)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
