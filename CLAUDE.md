# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Standalone project management tool for Bosch DMC D65P BEV VCCU project. Provides a local Super OPL (Open Point List), Gantt/planning management, and a bridge to Bosch's external Super OPL API. No LLM dependencies — purely a task/risk tracker with a React frontend.

## Commands

### Setup (one-time)
```bat
Setup.bat
```
Copies `.venv` from sibling `AI_PM_Assisstant_Final` project, or creates a fresh venv if not found, then installs `requirements.txt`.

### Run
```bat
Start.bat
```
Kills any processes on ports 8000 and 8080, then starts:
- FastAPI backend on `http://127.0.0.1:8000`
- Python HTTP server on `http://127.0.0.1:8080` (serves `html/standalone.html`)
- Opens browser automatically

### Manual backend (for development)
```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Manual frontend server
```powershell
.venv\Scripts\python.exe -m http.server 8080 --directory html --bind 127.0.0.1
```

No test suite or lint configuration exists — verify changes manually via the browser at `http://localhost:8080`.

## Architecture

```
Browser (localhost:8080)
    ↓
Python HTTP server → html/standalone.html   (React app, compiled single file)
    ↓ fetch() calls
FastAPI (localhost:8000)
    ├── super_opl_api.py  → outputs/super_opl.json
    ├── bosch_opl_api.py  → Bosch API + outputs/bosch_*.json
    └── planning_api.py   → outputs/planning_data.json / planning_versions.json
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
| `backend/ci_index.py` | CI lookup from `CI_Status_report.xlsx` |
| `html/standalone.html` | Compiled React SPA — edit the source React code, not this directly |
| `.env` | All runtime config: ports, Bosch API key, proxy, OneDrive paths |

## Data Conventions

- **IDs:** Integer, assigned as `max(existing_ids) + 1`. Never reused.
- **Soft delete:** OPL entries set `status = "deleted"`, never physically removed from `super_opl.json`.
- **Bosch sync:** Idempotent — matched via `bosch_task_id` field; local entries with a `bosch_task_id` are treated as synced.
- **Planning versions:** Keyed by `sheet` (master, sw, peru, opl); capped at 50 snapshots per sheet (oldest deleted).
- **Status auto-upgrade:** On any `GET /api/opl` response, entries with `due_date < today` and non-terminal status are returned as `overdue` (not saved, computed on read).

## Configuration (.env)

```
OUTPUT_DIR=outputs          # relative to project root
CORS_ORIGIN=http://localhost:8080
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
Super_OPL_API=<base64 key>  # Bosch Super OPL API key
BOSCH_OPL_NUMBER=340408     # Bosch OPL project number
BOSCH_LOGIN_USER=gdn4hc     # NT login passed in Bosch API headers
```

The Bosch API calls use `http://rb-proxy-apac.bosch.com:8080` as HTTP proxy (set in `.env` or inherited from environment).

## OPL Entry Types & Status Values

**entry_type:** `Task` | `Information` | `Decision` | `Subtask`

**status:** `running` | `closed` | `overdue` | `rejected` | `waiting_approval` | `draft` | `on_hold` | `deleted`

Bosch type→local mapping: `1→Task`, `2/3→Information`, `4→Decision`, `5→Risk`, `6→Problem`
Bosch status→local: `0→running`, `1→closed`, `2→on_hold`, `3→rejected`
