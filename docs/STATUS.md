# Status

The pilot is being implemented from `docs/PLAN.md`.

- `backend/`: `GET /api/health` and SQLite storage with the 25 pilot claims,
  customers, policies, plans, handlers and policy wording
- `agent/`: the entry point `run(claim_id, thread_id)`, with one tool that calls the health route
- `dashboard/`: one page that shows whether the backend is up
- `e2e/`: one test of that page

Phase 1 is complete. The backend initializes `backend/undercover.sqlite3` at startup
(override with `UNDERCOVER_DB`). It seeds only a new database and preserves existing
work on restart. SQLite files are ignored by git. Tests use temporary databases.

Install with `uv sync` and `npm install` (Python 3.12, Node 26). Run the backend and
dashboard with `npm run dev`. Run checks with `npm run check`.
