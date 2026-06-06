# CONTEXT.md — AI_PM_Plan_Task

## Project Purpose
Standalone project management tool for the **DMC D65P BEV VCCU** project at Bosch.
Manages tasks, risks, and decisions by syncing with Bosch's Super OPL API and maintaining a local tracker.

## Domain Language

### Core Concepts
- **OPL** (Open Point List) — Bosch's standard task/action tracker. Entries can be Tasks, Decisions, Information, or Subtasks.
- **Super OPL** — Bosch's web system at `rb-superopl.emea.bosch.com`. This tool is a local bridge to it.
- **VCCU** — Vehicle Control and Communication Unit. The ECU being developed.
- **DMC D65P** — The specific Bosch project (Drive Module Controller, platform D65P, BEV = Battery Electric Vehicle).
- **NT login** — Bosch network login (max 8 chars, lowercase alphanumeric, e.g. `gdn4hc`).

### Entry Types
| Type | Meaning |
|---|---|
| `Task` | Action item with owner and due date |
| `Information` | Read-only reference entry |
| `Decision` | Recorded team decision |
| `Subtask` | Child item under a Task (has `parent_id`) |
| `Risk` | Risk entry (local: LRISK-xxx, Bosch: BRISK-xxx) |

### Status Values
| Status | Meaning |
|---|---|
| `running` | In progress |
| `closed` | Done |
| `overdue` | Past due date, computed on read (not stored) |
| `rejected` | Cancelled |
| `waiting_approval` | Awaiting sign-off |
| `draft` | Not yet active |
| `on_hold` | Paused |
| `deleted` | Soft-deleted, never physically removed |

### ID Schemes
- Local OPL: `OPL-001`, `OPL-002`, ... (auto-increment max+1)
- Bosch-synced tasks: `BOSCH-xxxxxxx` (Bosch's numeric ID prefixed)
- Local risks: `LRISK-001`, Bosch risks: `BRISK-001`
- Local lessons learned: `LLL-001`, Bosch: `BLL-001`

### Planning / Gantt Sheets
| Sheet key | Meaning |
|---|---|
| `master` | Master project schedule |
| `sw` | Software activities plan |
| `peru` | Peru variant schedule |
| `opl` | OPL-derived schedule |

### Bosch API Type Mapping
```
Bosch type 1 → Task
Bosch type 2/3 → Information
Bosch type 4 → Decision
Bosch type 5 → Risk
Bosch type 6 → Problem
```

### Bosch API Status Mapping
```
Bosch status 0 → running
Bosch status 1 → closed
Bosch status 2 → on_hold
Bosch status 3 → rejected
```

## Architecture Summary
```
Browser (port 8080)
    ↓ fetch()
FastAPI (port 8000)
    ├── super_opl_api.py  → outputs/super_opl.json          (local OPL CRUD)
    ├── bosch_opl_api.py  → Bosch API + outputs/bosch_*.json (sync bridge)
    └── planning_api.py   → outputs/planning_data.json       (Gantt/versioning)
```

All data persisted as flat JSON in `outputs/`. No database.

## Key People
- **Nguyen Ngoc Duy** (gdn4hc) — PjM, developer of this tool
- **Mai Hong Sang** — SW Project Manager
- **Osakabe Yuki** — HW Project Manager

## Constraints & Gotchas
- Soft-delete only: OPL entries are never physically deleted (`status = "deleted"`).
- Overdue is computed on read, never stored.
- Bosch API requires NT login credentials and HTTP proxy at `rb-proxy-apac.bosch.com:8080`.
- SSL verification disabled for Bosch API calls (Bosch internal certificate not trusted).
- Sync is idempotent: matched by `bosch_task_id`, never re-creates duplicates.
- Planning versions capped at 50 per sheet (oldest auto-deleted).
- Frontend is a compiled single-file React SPA (`html/standalone.html`) — no source JSX in repo.
- No test suite — verify changes manually via browser at `http://localhost:8080`.
