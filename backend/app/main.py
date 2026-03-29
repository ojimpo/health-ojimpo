import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

from .database import init_db
from .routers import dashboard, ingest, notification, settings, shared
from .routers import oauth
from .scheduler import start_scheduler, stop_scheduler
from .sources.registry import register_adapters


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    register_adapters()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Cultural Health Dashboard API",
    description="Cultural Health Dashboard - メンタルヘルス早期察知ダッシュボード",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api")
app.include_router(shared.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(oauth.router, prefix="/api")
app.include_router(notification.router, prefix="/api")


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/site-info")
async def site_info():
    from .config import settings
    return {
        "username": settings.app_username,
        "domain": settings.app_domain,
    }
