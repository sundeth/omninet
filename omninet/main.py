"""
Main FastAPI application entry point.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from omninet import __version__
from omninet.config import settings
from omninet.database import init_db, close_db
from omninet.routes import (
    auth_router,
    users_router,
    modules_router,
    teams_router,
    battles_router,
    seasons_router,
    admin_router,
    shop_router,
)
from omninet.services.cache import verification_cache
from omninet.services.shop_sync import shop_sync_worker


async def cleanup_cache_task():
    """Background task to clean up expired verification codes."""
    while True:
        await asyncio.sleep(60)  # Run every minute
        await verification_cache.cleanup_expired()


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

    yield

    # Shutdown
    cleanup_task.cancel()
    shop_sync_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await shop_sync_task
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
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_dev else [
        "https://omnipet.duckdns.org",
    ],
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
