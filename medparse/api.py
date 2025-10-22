"""FastAPI application exposing health checks for Medparse."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from medparse.config import AppConfig


settings = AppConfig.model_construct_from_env({})


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = True
    yield
    app.state.ready = False


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    """Legacy health endpoint maintained for backwards compatibility."""
    return {"status": "ok", "ready": getattr(app.state, "ready", False)}


@app.get("/healthz")
async def healthz() -> dict:
    """Kubernetes-style health probe."""
    return {
        "ok": True,
        "ready": getattr(app.state, "ready", False),
        "status": "ok",
    }
