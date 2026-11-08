"""ApplyPilot AI - FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .automation.engine import manager
from .config import get_settings
from .db import init_db
from .routers import account, applications, auth, automation, profile, resumes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("applypilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.environment == "production":
        if not s.encryption_key or s.jwt_secret.startswith("change-me"):
            raise RuntimeError("Set JWT_SECRET and ENCRYPTION_KEY before running in production")
    init_db()
    log.info("ApplyPilot started (AI %s)", "enabled" if s.ai_enabled else "disabled - heuristic mode")
    yield
    await manager.shutdown()


settings = get_settings()
app = FastAPI(title="ApplyPilot AI API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)  # no bodies logged
    return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)


@app.get("/api/health")
def health():
    return {"status": "ok"}


for r in (auth.router, profile.router, resumes.router, applications.router, automation.router, account.router):
    app.include_router(r)
