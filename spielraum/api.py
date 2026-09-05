from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .seed import seed_preview
from .storage import connect, initialize, read_dashboard


settings = Settings.from_env()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    initialize(settings.database_path)
    if os.environ.get("SPIELRAUM_SEED_PREVIEW", "true").lower() in {"1", "true", "yes"}:
        with connect(settings.database_path) as connection:
            empty = connection.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 0
        if empty:
            seed_preview(settings.database_path)
    yield


app = FastAPI(title="Spielraum Forecast API", version="0.1.0", lifespan=lifespan)
allowed_origins = [o.strip() for o in os.environ.get("SPIELRAUM_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/healthz")
def health() -> dict[str, str]:
    try:
        with connect(settings.database_path, readonly=True) as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard():
    return read_dashboard(settings.database_path)
