# Status

The pilot is being implemented from `docs/PLAN.md`.

- `backend/`: `GET /api/health` and SQLite storage with the 25 pilot claims,
  customers, policies, plans, handlers and policy wording
- `agent/`: `run(claim_id, thread_id)` reads claims, context, wording and
  instructions through HTTP tools, records decisions and makes simulated payments
- `dashboard/`: queue, claim details, observable agent activity, customer and policy
  context, read-only instructions, handler sign-off and simulated payments
- `e2e/`: integration tests are being added in phase 6

Phases 1–5 are complete. The backend initializes `backend/undercover.sqlite3` at startup
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

Open `http://localhost:5173` after `npm run dev`. Select a claim to read its
documents, decision, calculation and activity; expand the context panels for the
customer history, policy, travelers, limits and add-ons. Queue, detail and activity
refresh every two seconds. Use **Agent instructions** for the current read-only
prompt. For an over-limit approval, select a handler and choose **Authorize and
pay**. If payment fails after sign-off, repeat just the payment. A decision and
its authorization survive reloads. The interface adapts to mobile screens.

Validation: 34 Python tests pass with 99% combined coverage; Ruff and Pyright pass.
Tests use a scripted model and make no calls to OpenRouter.
The 15 dashboard tests pass with 99% statement coverage. Prettier, ESLint and
TypeScript pass. Playwright MCP verified keyboard focus, current instructions,
live events and sign-off at 1440 px and 390 px without horizontal overflow or
console errors.

Install with `uv sync` and `npm install` (Python 3.12, Node 26). Run the backend and
dashboard with `npm run dev`. Run checks with `npm run check`.
