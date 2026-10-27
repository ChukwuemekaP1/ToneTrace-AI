"""FastAPI application factory, lifespan management, and middleware stack."""

import asyncio
import logging
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# Ensure Windows uses SelectorEventLoop for Psycopg 3 async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import request_id_ctx, setup_logging
from app.db.session import close_db_engine
from app.schemas.common import ResponseEnvelope, ResponseMeta

logger = logging.getLogger("tonetrace.app")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycles."""
    settings = get_settings()

    # Configure structured logging
    setup_logging(debug=settings.DEBUG, json_logs=settings.is_production)

    logger.info(
        f"Starting {settings.PROJECT_NAME} v{settings.VERSION} "
        f"[Environment: {settings.ENVIRONMENT.value}]"
    )

    yield

    # Clean shutdown
    logger.info("Initiating graceful shutdown...")
    await close_db_engine()
    logger.info("Application shutdown complete.")


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI application factory."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    # 1. Register Error Handlers
    register_error_handlers(app)

    # 2. CORS Middleware - strictly bound to configured origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # 3. Request ID & Structured Access Logging Middleware
    @app.middleware("http")
    async def request_id_and_access_log_middleware(request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = req_id
        token = request_id_ctx.set(req_id)

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Attach correlation ID to outbound response headers
            response.headers["X-Request-ID"] = req_id

            logger.info(
                f"{request.method} {request.url.path} -> {response.status_code} "
                f"({round(duration_ms, 2)}ms)",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return response
        finally:
            request_id_ctx.reset(token)

    # 4. Mount Root & Versioned API Routers
    # Direct /health probes for container/orchestrator compatibility
    app.include_router(health.router)

    # Versioned API routes under /api/v1
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # Root welcome metadata endpoint
    @app.get(
        "/",
        response_model=ResponseEnvelope[dict[str, str]],
        include_in_schema=False,
    )
    async def root_index(request: Request) -> ResponseEnvelope[dict[str, str]]:
        req_id = getattr(request.state, "request_id", None)
        return ResponseEnvelope(
            status="success",
            data={
                "name": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT.value,
                "docs": "/docs" if not settings.is_production else "disabled",
            },
            meta=ResponseMeta(request_id=req_id),
        )

    return app


# Default ASGI application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    _settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=_settings.HOST,
        port=_settings.PORT,
        loop="asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto",
        reload=not _settings.is_production,
    )
