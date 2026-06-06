# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Standalone project management tool for Bosch DMC D65P BEV VCCU project. Provides a local Super OPL (Open Point List), Gantt/planning management, and a bridge to Bosch's external Super OPL API. No LLM dependencies — purely a task/risk tracker with a React frontend.

## Commands

### Setup (one-time)
```bat
Setup.bat
```
- Copies `.venv` from sibling `AI_PM_Assisstant_Final` project (or creates fresh venv), installs `requirements.txt`
- Also runs `npm install` in `frontend/` if Node.js (fnm) is available

### Run — Production mode
```bat
Start.bat
```
Kills any processes on ports 8000 and 8080, then starts:
- FastAPI backend on `http://127.0.0.1:8000`
- Python HTTP server on `http://127.0.0.1:8080` (serves `html/standalone.html`)
- Opens browser automatically

### Run — Development mode (hot-reload)
```bat
Dev.bat
```
Starts backend with `--reload` on port 8000 + Vite dev server on port 5173. Changes to `frontend/src/` reflect instantly without rebuild.

### Build frontend
```bat
Build.bat
```
Runs `npm run build` in `frontend/`, outputs `html/standalone.html`. Run this before committing UI changes or before using `Start.bat` with the latest code.

### Manual backend only
```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Manual frontend dev only
```powershell
cd frontend
npm run dev   # Vite at http://localhost:5173 — proxies /api/* → port 8000
```

No test suite — verify changes manually via browser.

## Architecture

```
Production (Start.bat):
  Browser (localhost:8080)
      ↓ serves
  Python HTTP server → html/standalone.html   (Vite-compiled single-file React app)
      ↓ fetch() calls
  FastAPI (localhost:8000)

Development (Dev.bat):
  Browser (localhost:5173)
      ↓ Vite dev server (hot reload)
  frontend/src/   (React + TypeScript source)
      ↓ /api/* proxied to
  FastAPI (localhost:8000) + --reload
```

All data is persisted as flat JSON files inside `outputs/` (created at first run). There is no database.

## Key Files

| File | Role |
|------|------|
| `backend/main.py` | FastAPI app — CORS, rate limiting (slowapi), router registration |
| `backend/super_opl_api.py` | Local OPL CRUD; soft-delete; auto-overdue on read |
| `backend/bosch_opl_api.py` | Bridge to `rb-superopl.emea.bosch.com`; sync/push/pull |
| `backend/planning_api.py` | Gantt task management; versioned snapshots (max 50) |
| `backend/project_config.py` | Multi-project config loader from `projects/*.json`; fallback to hardcoded DMC VCCU |
| `backend/ci_index.py` | CI lookup from `CI_Status_report.xlsx`; in-memory index keyed by CI ID (e.g. `CI-0016`) |
| `backend/prompts/system_prompts.py` | System prompt strings — not wired into this standalone tool; kept for future use |
| `frontend/src/` | React + TypeScript source — **edit here, not standalone.html** |
| `frontend/src/api/client.ts` | Typed API client for all backend endpoints |
| `frontend/src/types/index.ts` | TypeScript types: OPLEntry, Risk, PlanningTask, etc. |
| `frontend/src/components/` | UI components by domain: opl/, risks/, lessons/, planning/, ui/ |
| `html/standalone.html` | Vite build output (single-file) — DO NOT edit directly |
| `.env` | All runtime config: ports, Bosch API key, proxy, OneDrive paths |

## Frontend Development

### Tech stack
- React 18 + TypeScript (strict mode)
- Vite 5 + vite-plugin-singlefile (compiles everything into one HTML file)
- Plain CSS with CSS variables (no Tailwind, no CSS-in-JS)
- No external UI component library

### Component structure
```
frontend/src/
  api/client.ts           ← all fetch() calls, typed
  types/index.ts          ← shared TypeScript types
  components/
    opl/
      OPLTab.tsx          ← list view (filter, search, paginate, import/export)
      OPLDetail.tsx       ← slide-in drawer (notes, status change)
      OPLForm.tsx         ← create modal
      OPLForm.css         ← scoped styles for OPLForm
    opl/BoschTab.tsx      ← Bosch tasks + sync/push-all
    risks/RisksTab.tsx    ← risk table + expandable measures
    lessons/LessonsTab.tsx
    planning/PlanningTab.tsx ← sheet tabs + Gantt table + version history
    ui/StatusBadge.tsx    ← StatusBadge, PriorityBadge
  App.tsx                 ← tab router + nav header
  index.css               ← design tokens + shared classes (btn-*, badge-*, card, table)
```

### CSS conventions
- Design tokens in `:root` in `index.css`: `--bosch-blue`, `--danger`, `--border`, etc.
- Shared utility classes: `.btn-primary`, `.btn-ghost`, `.btn-danger`, `.card`, `.badge`, `.badge-<status>`
- Component-scoped CSS in `ComponentName.css` files (import from the `.tsx` file)
- **No inline `style={{...}}`** unless value is dynamic/computed at runtime

### Build → standalone.html
`npm run build` in `frontend/` → TypeScript check → Vite build → auto-renames `html/index.html` to `html/standalone.html`

In production (`standalone.html`), the Python HTTP server injects `window.__API_BASE__` so that `api/client.ts` points to `http://127.0.0.1:8000`. In dev mode (`localhost:5173`), Vite proxies `/api/*` to port 8000 directly — no injection needed.

### Inline styles in App.tsx
`App.tsx` uses inline `style={{...}}` for the top-level layout shell (header, nav, main). This is intentional — those values are static layout constants, not component-scoped CSS. Do not move them to CSS files; it would break the single-file bundle structure.

## Data Conventions

- **IDs:** Integer, assigned as `max(existing_ids) + 1`. Never reused.
- **Soft delete:** OPL entries set `status = "deleted"`, never physically removed from `super_opl.json`.
- **Bosch sync:** Idempotent — matched via `bosch_task_id` field; local entries with a `bosch_task_id` are treated as synced.
- **Planning versions:** Keyed by `sheet` (`master`, `sw`, `peru`, `opl`); capped at 50 snapshots per sheet (oldest deleted). `master` and `sw` load from `Project_document/Project_plan_mpp_extract.xlsx` on first access; `opl` is populated from OPL entries directly; `peru` starts empty.
- **Status auto-upgrade:** On any `GET /api/opl` response, entries with `due_date < today` and non-terminal status are returned as `overdue` (not saved, computed on read).
- **Atomic writes:** All JSON saves use temp-file + `os.replace()` to prevent corruption on crash.

## Configuration (.env)

```
OUTPUT_DIR=outputs          # relative to project root
CORS_ORIGIN=http://localhost:8080
CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,null
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
Super_OPL_API=<base64 key>  # Bosch Super OPL API key
BOSCH_OPL_NUMBER=340408     # Bosch OPL project number
BOSCH_LOGIN_USER=<nt_login> # NT login passed in Bosch API headers
```

The Bosch API calls use `http://rb-proxy-apac.bosch.com:8080` as HTTP proxy (set in `.env` or inherited from environment).

## OPL Entry Types & Status Values

**entry_type:** `Task` | `Information` | `Decision` | `Subtask`

**status:** `running` | `closed` | `overdue` | `rejected` | `waiting_approval` | `draft` | `on_hold` | `deleted`

Bosch type→local mapping: `1→Task`, `2/3→Information`, `4→Decision`, `5→Risk`, `6→Problem`
Bosch status→local: `0→running`, `1→closed`, `2→on_hold`, `3→rejected`

## Forbidden Actions

- **DO NOT** edit `html/standalone.html` directly — edit `frontend/src/` then run `Build.bat`
- **DO NOT** delete `outputs/` — contains production data
- **DO NOT** commit `.env` — contains API keys
- **DO NOT** change OPL ID generation logic without a data migration plan
- **DO NOT** hardcode NT login or API key as fallback values in code

## Verification Standard

Before marking any change "done":
- **Backend change:** Run `Start.bat` (or backend manually), hit the affected endpoint with curl or browser
- **Frontend change:** Run `Dev.bat`, test the feature in browser at `localhost:5173`
- **UI feature:** Test create → read → update → status-change cycle on a real OPL entry
- **Bosch sync:** Only testable on Bosch network with VPN — note if verification was skipped
- Never say "it should work" without actually running it
