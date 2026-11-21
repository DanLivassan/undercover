"""The agent's only access to UnderCover business data."""

import os
from typing import Any

import httpx


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(
        base_url=os.environ.get("BACKEND_URL", "http://localhost:8000"), timeout=30
    )


def request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    with backend() as client:
        response = client.request(method, path, json=body)
    response.raise_for_status()
    return response.json()
