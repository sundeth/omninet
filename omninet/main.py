"""
Main FastAPI application entry point.
"""
import asyncio
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
    arena_router,
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
    Background task: the arena season clock.

    Every ``arena_tick_seconds`` it closes a season whose time is up (final
    ranks, top-3 prizes), installs queued Omnipet/module updates at that
    boundary, and opens the next season.  See SeasonService.tick.
    """
    while True:
        try:
            async with get_db_context() as db:
                report = await SeasonService(db).tick()
            if report and set(report) - {"skipped"}:
                print(f"[season_status_task] {report}")
        except Exception as exc:
            print(f"[season_status_task] error: {exc}")
        await asyncio.sleep(max(5, settings.arena_tick_seconds))


async def arena_bot_task():
    """Development only: dummy arena players attack on a timer."""
    from omninet.arena.bots import run_bot_battles

    while True:
        await asyncio.sleep(max(5, settings.arena_dev_bot_interval_seconds))
        try:
            async with get_db_context() as db:
                await run_bot_battles(db, settings.arena_dev_bot_battles_per_tick)
        except Exception as exc:
            print(f"[arena_bot_task] error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    # Startup
    print(f"Starting Omninet v{__version__} ({settings.environment} environment)")

    # Initialize database
    await init_db()

    # Start background tasks
    cleanup_task = asyncio.create_task(cleanup_cache_task())
    shop_sync_task = asyncio.create_task(shop_sync_worker())
    season_task = asyncio.create_task(season_status_task())
    bot_task = (asyncio.create_task(arena_bot_task())
                if settings.is_dev and settings.arena_dev_bots else None)

    yield

    # Shutdown
    cleanup_task.cancel()
    shop_sync_task.cancel()
    season_task.cancel()
    if bot_task is not None:
        bot_task.cancel()
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
app.include_router(arena_router, prefix="/api/v1")
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
