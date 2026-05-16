"""
Main FastAPI application entry point.
"""
import asyncio
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from omninet import __version__
from omninet.config import settings
from omninet.database import close_db, get_db_context, init_db
from omninet.routes import (
    admin_router,
    auth_router,
    battles_router,
    modules_router,
    rewards_router,
    seasons_router,
    shop_router,
    teams_router,
    users_router,
)
from omninet.services.cache import verification_cache
from omninet.services.season import SeasonService
from omninet.services.shop_sync import shop_sync_worker


async def cleanup_cache_task():
    """Background task to clean up expired verification codes."""
    while True:
        await asyncio.sleep(60)  # Run every minute
        await verification_cache.cleanup_expired()


async def season_status_task():
    """
    Background task: roll season statuses and pay out top-3 prizes.

    Runs every 5 minutes.  ``update_season_statuses`` flips
    UPCOMING→ACTIVE / ACTIVE→COMPLETED based on dates and, on the
    transition to COMPLETED, calls ``close_season`` to add top-3 prize
    coins to the winning teams' ``rewarded_coins``.
    """
    while True:
        try:
            async with get_db_context() as db:
                await SeasonService(db).update_season_statuses()
        except Exception as exc:
            print(f"[season_status_task] error: {exc}")
        await asyncio.sleep(300)  # 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    # Startup
    print(f"Starting Omninet v{__version__} ({settings.environment} environment)")

    # Inject game client simulator path so server can import battle code directly
    if settings.game_client_path:
        client_path = settings.game_client_path
        if client_path not in sys.path:
            sys.path.insert(0, client_path)
            print(f"[Omninet] Game client path added to sys.path: {client_path}")

    # Initialize database
    await init_db()

    # Start background tasks
    cleanup_task = asyncio.create_task(cleanup_cache_task())
    shop_sync_task = asyncio.create_task(shop_sync_worker())
    season_task = asyncio.create_task(season_status_task())

    yield

    # Shutdown
    cleanup_task.cancel()
    shop_sync_task.cancel()
    season_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await shop_sync_task
    except asyncio.CancelledError:
        pass
    try:
        await season_task
    except asyncio.CancelledError:
        pass

    await close_db()
    print("Omninet shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Omninet API",
    description="Backend API for Omnipet virtual pet game",
    version=__version__,
    lifespan=lifespan,
    root_path=settings.root_path,
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_dev else (
        settings.cors_origin_list or [
            "https://omnipet.app.br",
        ]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    if settings.is_dev:
        # In development, show full error details
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc),
                "type": type(exc).__name__,
            },
        )
    else:
        # In production, hide error details
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )


# Include routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(modules_router, prefix="/api/v1")
app.include_router(teams_router, prefix="/api/v1")
app.include_router(battles_router, prefix="/api/v1")
app.include_router(seasons_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(shop_router, prefix="/api/v1")
app.include_router(rewards_router, prefix="/api/v1")

# When a root_path prefix is configured (e.g. "/dev"), Swagger UI generates the
# openapi URL as "{root_path}/openapi.json".  FastAPI only registers "/openapi.json",
# so direct access (bypassing the reverse proxy) returns 404.  This alias makes the
# prefixed URL work without relying solely on the proxy to strip the prefix.
if settings.root_path:

    @app.get(f"{settings.root_path}/openapi.json", include_in_schema=False)
    async def prefixed_openapi_json() -> JSONResponse:
        """Alias so Swagger loads correctly when accessed without a reverse proxy."""
        return JSONResponse(app.openapi())


# Health check endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": __version__}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Omninet API",
        "version": __version__,
        "environment": settings.environment,
        "docs": "/docs" if settings.is_dev else None,
    }


def run():
    """Run the application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "omninet.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_dev,
        log_level="debug" if settings.is_dev else "info",
    )


if __name__ == "__main__":
    run()
