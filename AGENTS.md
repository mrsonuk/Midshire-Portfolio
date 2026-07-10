# AGENTS.md

## Cursor Cloud specific instructions

### What this is
Single product, "Model ED Optimiser": a Flask backend (`uec_hybrid/`, the whole
product — HTML surfaces, JSON API, PDF reports) plus an optional React/Vite shell
(`web/`) mounted at `/app`. Persistence is embedded SQLite (auto-created on
startup); no separate database process is needed. See `README.md` for the product
overview and architecture.

### Services / commands (dependencies are pre-installed by the update script)
- Backend (required, port 5000): `python3 -m uec_hybrid.app.server` — serves `/`,
  `/exec`, `/planner`, `/analyst`, the React shell at `/app`, and `/api/*`.
- Backend tests (end-to-end, single command): `python3 -m uec_hybrid.tests.run`.
- Frontend (optional, only for live React dev): in `web/`, `npm run dev`
  (Vite, port 5173), or `npm run build` / `npm run preview`. `npm run build` runs
  `tsc` (type-check) then `vite build`.

### Non-obvious gotchas
- Use `python3`; there is no `python` alias in this environment.
- The prebuilt `web/dist/` is committed and served by Flask, so the product runs
  fully at `/app` without the Vite dev server. Only run Vite for live React work.
- The Vite dev server proxies `/api` → `http://127.0.0.1:5000`, so the Flask
  backend must also be running for the React app to work in dev.
- Vite binds to `localhost` (resolves to IPv6 `::1`), not `127.0.0.1`; probe it as
  `http://localhost:5173/app/`.
- The analyst/simulation JSON endpoints (`/api/simulate`, `/api/validate`,
  `/api/montecarlo`, `/api/scenarios`) require a full request body including a
  `pathway` key (the frontend sends this via `cfg()`); POSTing an empty/partial
  body returns HTTP 500 by design, not an environment failure.
- CI (`.github/workflows/tests.yml`) targets Python 3.11; this environment uses
  3.12, which runs the suite cleanly. `requirements.txt` is unpinned (`>=`).
