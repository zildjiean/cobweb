"""FastAPI app factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from cobweb import __version__
from cobweb.api.public.router import public_router
from cobweb.api.v1.router import api_router
from cobweb.core.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logger.info("cobweb-api starting | env={} debug={}", settings.env, settings.debug)
    yield
    logger.info("cobweb-api shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Cobweb API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = request_id
        logger.info(
            "{} {} -> {} {:.1f}ms rid={}",
            request.method, request.url.path, response.status_code, elapsed_ms, request_id,
        )
        return response

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": __version__}

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(api_router)
    app.include_router(public_router)
    return app


app = create_app()
