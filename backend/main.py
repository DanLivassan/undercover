"""The UnderCover backend."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from backend.instructions import INSTRUCTIONS
from backend.models import Decision, Event, Execution, Failure, Payment, SignOff
from backend.service import Claims, Conflict
from backend.store import Store


@asynccontextmanager
async def lifespan(application: FastAPI):
    store = Store(Path(os.environ.get("UNDERCOVER_DB", "backend/undercover.sqlite3")))
    store.initialize()
    application.state.store = store
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


@app.exception_handler(KeyError)
async def missing(_request: Request, _error: Exception):
    return JSONResponse(status_code=404, content={"detail": "Record not found."})


@app.exception_handler(Conflict)
async def conflict(_request: Request, error: Exception):
    return JSONResponse(status_code=409, content={"detail": str(error)})


def claims_service(request: Request) -> Claims:
    return Claims(request.app.state.store)


Service = Annotated[Claims, Depends(claims_service)]


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims(service: Service) -> list[dict[str, Any]]:
    """List claims in queue order."""
    return service.store.claims()


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, service: Service) -> dict[str, Any]:
    """Read a claim and its decision and payment."""
    return service.get(claim_id)


@app.get("/api/claims/{claim_id}/context", operation_id="get_claim_context")
def get_context(claim_id: str, service: Service) -> dict[str, Any]:
    """Read the customer history, policy, plan and applicable add-ons."""
    return service.store.context(claim_id)


@app.get("/api/policy-wording", operation_id="get_policy_wording")
def get_wording(service: Service) -> dict[str, str]:
    """Read the complete policy wording and version."""
    with service.store.connect() as db:
        return service.store.record(db, "settings", "wording")


@app.get("/api/agent/instructions", operation_id="get_agent_instructions")
def get_instructions() -> dict[str, str]:
    """Read the instructions used by the agent."""
    return {"text": INSTRUCTIONS}


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers(service: Service) -> list[dict[str, Any]]:
    """List handlers available for payment sign-off."""
    with service.store.connect() as db:
        ids = db.execute("SELECT id FROM records WHERE kind = 'handlers' ORDER BY id")
        return [service.store.record(db, "handlers", row["id"]) for row in ids]


@app.get("/api/claims/{claim_id}/events", operation_id="list_claim_events")
def list_events(claim_id: str, service: Service) -> list[dict[str, Any]]:
    """Read the observable activity for a claim in order."""
    return service.events(claim_id)


@app.post("/api/claims/{claim_id}/start", operation_id="start_claim")
def start(claim_id: str, body: Execution, service: Service) -> dict[str, Any]:
    """Reserve a waiting claim for an agent execution."""
    return service.start(claim_id, body)


@app.post("/api/claims/{claim_id}/events", operation_id="record_claim_event")
def add_event(claim_id: str, body: Event, service: Service) -> dict[str, str]:
    """Record an observable tool action for the active execution."""
    return service.add_event(claim_id, body)


@app.post("/api/claims/{claim_id}/decision", operation_id="record_decision")
def decide(claim_id: str, body: Decision, service: Service) -> dict[str, Any]:
    """Record the agent's decision and supporting explanation."""
    return service.decide(claim_id, body)


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_payment")
def sign_off(claim_id: str, body: SignOff, service: Service) -> dict[str, Any]:
    """Authorize an over-limit payment as a handler."""
    return service.sign_off(claim_id, body)


@app.post("/api/claims/{claim_id}/pay", operation_id="pay_claim")
def pay(claim_id: str, body: Payment, service: Service) -> dict[str, Any]:
    """Record a separate simulated payment of the approved amount."""
    return service.pay(claim_id, body)


@app.post("/api/claims/{claim_id}/failure", operation_id="record_execution_failure")
def fail(claim_id: str, body: Failure, service: Service) -> dict[str, Any]:
    """Record an execution failure and release an undecided claim."""
    return service.fail(claim_id, body)
