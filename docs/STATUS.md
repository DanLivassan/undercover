# Status

The pilot is being implemented from `docs/PLAN.md`.

- `backend/`: `GET /api/health` and SQLite storage with the 25 pilot claims,
  customers, policies, plans, handlers and policy wording
- `agent/`: `run(claim_id, thread_id)` reads claims, context, wording and
  instructions through HTTP tools, records decisions and makes simulated payments
- `dashboard/`: one page that shows whether the backend is up
- `e2e/`: one test of that page

Phases 1–4 are complete. The backend initializes `backend/undercover.sqlite3` at startup
(override with `UNDERCOVER_DB`). It seeds only a new database and preserves existing
work on restart. SQLite files are ignored by git. Tests use temporary databases.

The API provides claims, context, wording, handlers, instructions and activity;
see `/docs` for required request bodies. Claims move through `waiting`,
`in_progress`, `waiting_for_sign_off` and `decided`. Decisions and payments are
separate. The backend atomically reserves claims and rejects payments over
$1,000 until a permitted handler signs off. Duplicate payment requests do not
create additional payments. Decisions are immutable. Payments are simulated.

The agent uses `OPENROUTER_API_KEY` from `.env`. Its default model is
`openai/gpt-6-luna` with low reasoning effort. Set `MODEL_NAME` to override it,
including `openrouter/free`. `BACKEND_URL` defaults to `http://localhost:8000`.
The backend owns the instructions and exposes them at `/api/agent/instructions`.
Tool calls, results, decisions and failures are recorded as activity. An execution
failure releases a claim with no decision; an existing decision is preserved.

With the backend running, use `uv run -m agent CLM-1001` for one claim or
`uv run -m agent` for all waiting claims in queue order. Each attempt has a unique
thread ID. The CLI skips non-waiting claims, continues after a case fails and exits
nonzero when there are failures. `uv run -m agent --help` describes both modes.
The dashboard does not start agent executions.

Validation: 34 Python tests pass with 99% combined coverage; Ruff and Pyright pass.
Tests use a scripted model and make no calls to OpenRouter.

Install with `uv sync` and `npm install` (Python 3.12, Node 26). Run the backend and
dashboard with `npm run dev`. Run checks with `npm run check`.
