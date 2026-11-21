"""The UnderCover backend."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from backend.store import Store


@asynccontextmanager
async def lifespan(application: FastAPI):
    store = Store(Path(os.environ.get("UNDERCOVER_DB", "backend/undercover.sqlite3")))
    store.initialize()
    application.state.store = store
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}
