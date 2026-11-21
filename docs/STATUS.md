# Status

The pilot in `docs/PLAN.md` is complete.

- FastAPI and SQLite: 25 claims, customer history, policies, plan limits, add-ons,
  complete policy wording, handlers, decisions, sign-off, payments and activity.
- LangChain agent: reviews one claim using only HTTP tools, reads the backend's
  instructions, records approve/decline/refer decisions and simulated payments.
- React dashboard: queue, complete claim details, documents, context, decision,
  calculation, policy reference, live activity and read-only agent instructions.
- Handler sign-off: the backend blocks payouts over $1,000 until an authorized
  handler signs off, even if the agent directly attempts payment. Payment is a
  separate, repeat-safe operation. No real money is transferred.

## Install and run

Use Python 3.12 and Node 26, from the repository root:

```sh
uv sync
npm install
npm run dev
```

Open `http://localhost:5173`. The backend is at `http://localhost:8000`;
`/docs` describes the API and `/api/health` returns `{"status":"ok"}`.
The install sets up the pre-commit hook and Playwright Chromium.

With the backend running, open another terminal:

```sh
uv run -m agent CLM-1001
uv run -m agent
```

The first command reviews one claim; the second processes all waiting claims in
queue order. Each attempt has a unique thread ID. The CLI continues after a case
fails and exits nonzero if any case fails. It never reruns a completed decision.
`uv run -m agent --help` describes the commands.

Set `OPENROUTER_API_KEY` in `.env` for real agent runs. The default model is
`openai/gpt-6-luna` with low reasoning effort; `MODEL_NAME` overrides it, including
`openrouter/free`. `BACKEND_URL` overrides the HTTP backend address for the agent
and Vite proxy. The agent defaults to `http://localhost:8000`.

## Working a claim

Select a claim in the queue. Expand its documents and customer/cover panels to
read all the evidence, claim history, policy, travelers, limits and add-ons.
Queue, detail and activity refresh every two seconds. **Agent instructions**
shows the same read-only prompt the agent loads from the API. Start agent runs
from the CLI; the dashboard does not trigger them.

The queue states are `waiting`, `in_progress`, `waiting_for_sign_off` and
`decided`. Approve, decline and refer are separate decision outcomes. A referral
completes the automated review and preserves the need for handler attention.
An approval up to $1,000 completes when its simulated payment is recorded.
An approval above the limit waits for a handler: select a handler and choose
**Authorize and pay**. If payment fails after sign-off, retry just the payment.
The UI also allows retrying an approved lower-value payment that failed.

Decisions are immutable. Repeating the same successful payment request never
creates another payment. Tool calls/results, decisions, authorizations, payments
and failures appear in the activity feed; private model reasoning is not stored.
A caught execution failure releases an undecided claim back to the queue and
preserves the activity. Existing decisions and payments are never erased.

## Storage and checks

The backend initializes `backend/undercover.sqlite3` at startup; the environment
variable `UNDERCOVER_DB` overrides this path. Only a new database is seeded.
Restarts preserve work. SQLite files and `.env` are ignored by git. Business
source files are not modified. The seed loader uses an explicit file allowlist;
the claims manual, knowledge records, security cases and evaluation files are
not loaded or exposed to the agent.

```sh
npm run check
```

Verified: Ruff, Pyright, 35 Python tests (99.24% coverage), Prettier, ESLint,
TypeScript, 15 dashboard tests (99.1% statement coverage) and six Playwright tests.
The Playwright suite starts its own backend on port 8001 and dashboard on 5174,
with a new temporary database, and runs the actual claim agent with a scripted
model. No model keys or paid calls are needed for checks. If uv is installed
outside its usual user `.local/bin` directory, set `UV_EXECUTABLE` to its absolute
path before running the browser tests.

Playwright MCP also verified live events, sign-off, current instructions,
keyboard focus and USD formatting at 1440 px and 390 px, with no horizontal
overflow or browser console errors. Backend integration tests verify persistence
across application restarts and concurrent claim reservation.

## Pilot limits

No sign-in, real payments, customer messages, AWS resources, claims manual,
external knowledge, evaluations or later-course features were added. Tests verify
workflow and payment controls with scripted decisions; real-model claim accuracy
has not been measured against handler decisions. Abruptly terminating a process
can leave a claim in progress; automatic crash recovery is outside this pilot.
The current course dependency lock still reports 20 npm audit advisories
(14 moderate, four high and two critical); dependency upgrades were not part of
this pilot implementation.
