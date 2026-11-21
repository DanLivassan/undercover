"""Sequential queue processing for the pilot command line."""

import argparse
import sys
from decimal import Decimal
from uuid import uuid4

import httpx

from agent.api import request
from agent.main import run


def review(claim_id: str) -> bool:
    try:
        run(claim_id, str(uuid4()))
        claim = request("GET", f"/api/claims/{claim_id}")
        decision = claim["decision"]
        print(
            f"{claim_id}: {decision['outcome']} "
            f"${Decimal(decision['amount']):,.2f} — {claim['status']}"
        )
        return True
    except Exception as error:
        print(f"{claim_id}: failed — {error}", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review UnderCover travel claims.")
    parser.add_argument(
        "claim_id", nargs="?", help="One claim; omit to work the queue."
    )
    args = parser.parse_args(argv)
    try:
        if args.claim_id:
            request("GET", f"/api/claims/{args.claim_id}")
            ids = [args.claim_id]
        else:
            ids = [
                c["claim_id"]
                for c in request("GET", "/api/claims")
                if c["status"] == "waiting"
            ]
    except httpx.HTTPError as error:
        print(
            f"Cannot read claims. Check BACKEND_URL and the claim ID: {error}",
            file=sys.stderr,
        )
        return 1
    successes = sum(review(claim_id) for claim_id in ids)
    failures = len(ids) - successes
    print(f"Completed: {successes}. Failed: {failures}.")
    return int(failures > 0)
