"""
Planning API — DMC VCCU PM Assistant
Data source: Project_document/Project_plan_mpp_extract.xlsx
  Sheet "Master"      → master schedule
  Sheet "SW schedule" → SW detail schedule

GET    /api/planning?sheet=              → return current tasks
POST   /api/planning                     → save tasks + create version snapshot
DELETE /api/planning?sheet=              → reset to Excel source

GET    /api/planning/versions?sheet=     → list all versions (newest first)
GET    /api/planning/versions/{vid}      → get full tasks for one version
DELETE /api/planning/versions/{vid}      → delete a version
"""

import json
import logging
import os
import re
import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("opl_standalone.planning")

router = APIRouter()

_ROOT          = Path(__file__).resolve().parent.parent
_OUTPUT_DIR    = Path(os.getenv("OUTPUT_DIR", str(_ROOT / "outputs")))
_PLANNING_FILE = _OUTPUT_DIR / "planning_data.json"
_VERSIONS_FILE = _OUTPUT_DIR / "planning_versions.json"
_MPP_XLSX      = _ROOT / "Project_document" / "Project_plan_mpp_extract.xlsx"

VALID_SHEETS   = {"master", "sw", "peru", "opl"}
SHEET_MAP      = {"master": "Master", "sw": "SW schedule", "peru": "Peru"}
MAX_VERSIONS   = 50   # keep at most 50 versions per sheet

# OPL tracker sheet mapping (mirrors main.py _PJM_OP_SHEETS / _SW_OP_SHEETS)
_OPL_AREAS = [
    ("overall", "📋 Overall OPL", "pjm", "General"),
    ("ecu_pjm", "📋 ECU PjM OPL", "pjm", "Summary"),
    ("hw",      "📋 HW OPL",      "pjm", "HW"),
    ("cal",     "📋 CAL OPL",     "pjm", "CAL"),
    ("sw",      "📋 SW OPL",      "sw",  "SW"),
]


# ── Models ─────────────────────────────────────────────────────────────────────

class SavePlanningRequest(BaseModel):
    sheet: str
    tasks: list[dict]
    label: str = ""   # optional user label for this version


# ── Date parsing ───────────────────────────────────────────────────────────────

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

def _parse_excel_date(val: Any) -> str:
    """
    Parse Excel date values → ISO YYYY-MM-DD string.
    Handles:
      - datetime / date objects  (pandas already converted)
      - "10 January 2025 5:00 pm" (MS Project text export)
      - "2025-01-10" ISO strings
    Returns "" on failure.
    """
    if val is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")

    s = str(val).strip()
    if not s or s in ("nan", "NaN", "None", "NaT"):
        return ""

    # ISO YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # "10 January 2025 5:00 pm"  /  "18 August 2025 8:00 am"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if m:
        day  = int(m.group(1))
        mon  = _MONTH_MAP.get(m.group(2).lower())
        year = int(m.group(3))
        if mon:
            return f"{year}-{mon:02d}-{day:02d}"

    return ""


def _parse_duration_days(val: Any) -> int:
    """'40 days', '0 days?', '87 days' → int."""
    if not val:
        return 0
    s = str(val).strip()
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return int(float(m.group(1))) if m else 0


def _safe_str(val: Any) -> str:
    try:
        import pandas as pd
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return "" if s in ("nan", "NaN", "None", "NaT", "undefined") else s


# ── Excel → Gantt tasks ────────────────────────────────────────────────────────

def _build_id_map(rows: list[dict]) -> dict[int, str]:
    """Map Excel row ID column → our gantt task id string."""
    return {int(float(_safe_str(r.get("ID", "0")) or "0")): f"t{int(float(_safe_str(r.get('ID','0')) or 0))}"
            for r in rows if _safe_str(r.get("ID", ""))}


def _parse_predecessors(raw: str, id_map: dict[int, str]) -> list:
    """
    Parse MS Project predecessor string like "74", "7FS", "7FS+2d", "7,8SS-1d"
    → list of { id, type, lag } dicts (backward compatible with plain string ids).
    """
    if not raw:
        return []
    result = []
    for part in re.split(r"[,;\s]+", raw.strip()):
        part = part.strip()
        if not part:
            continue
        # Pattern: <number>[FS|SS|FF|SF][+/-<n>d]
        m = re.match(r"^(\d+)(FS|SS|FF|SF)?([+-]\d+d?)?$", part, re.IGNORECASE)
        if m:
            excel_id = int(m.group(1))
            dep_type = (m.group(2) or "FS").upper()
            lag_str  = m.group(3) or ""
            lag_days = 0
            if lag_str:
                lag_days = int(re.sub(r"[^\d-]", "", lag_str) or "0")
            if excel_id in id_map:
                entry = {"id": id_map[excel_id], "type": dep_type, "lag": lag_days}
                result.append(entry)
    return result


def _outline_to_parent(rows: list[dict], id_map: dict[int, str]) -> dict[str, str | None]:
    """
    Build parent_id map from Outline Level column.
    Outline Level 1 → parent None
    Outline Level 2 → parent = nearest ancestor at level 1
    etc.
    """
    parent_map: dict[str, str | None] = {}
    stack: list[tuple[int, str]] = []   # (outline_level, task_id)

    for row in rows:
        raw_id    = _safe_str(row.get("ID", ""))
        raw_level = _safe_str(row.get("Outline Level", ""))
        if not raw_id or not raw_level:
            continue
        try:
            excel_id = int(float(raw_id))
            level    = int(float(raw_level))
        except (ValueError, TypeError):
            continue

        task_id = id_map.get(excel_id)
        if not task_id:
            continue

        # Pop stack until top level < current level
        while stack and stack[-1][0] >= level:
            stack.pop()

        parent_map[task_id] = stack[-1][1] if stack else None
        stack.append((level, task_id))

    return parent_map


def _rows_to_gantt(rows: list[dict], sheet_key: str) -> list[dict]:
    """Convert raw Excel rows → Gantt task dicts with hierarchy + dependencies."""
    if not rows:
        return []

    # Filter out rows with no ID or no Name
    rows = [r for r in rows if _safe_str(r.get("ID", "")) and _safe_str(r.get("Name", ""))]

    id_map      = _build_id_map(rows)
    parent_map  = _outline_to_parent(rows, id_map)

    tasks = []
    for row in rows:
        raw_id = _safe_str(row.get("ID", ""))
        if not raw_id:
            continue
        try:
            excel_id = int(float(raw_id))
        except (ValueError, TypeError):
            continue

        task_id = id_map.get(excel_id)
        if not task_id:
            continue

        name        = _safe_str(row.get("Name", "")) or f"Task {excel_id}"
        start       = _parse_excel_date(row.get("Start"))
        finish      = _parse_excel_date(row.get("Finish"))
        dur_days    = _parse_duration_days(row.get("Duration"))
        active_raw  = _safe_str(row.get("Active", "")).lower()
        active      = active_raw in ("yes", "true", "1", "")

        # Compute duration from dates if column value is 0
        if not dur_days and start and finish:
            try:
                s_dt = datetime.fromisoformat(start)
                f_dt = datetime.fromisoformat(finish)
                dur_days = max(0, (f_dt - s_dt).days)
            except Exception:
                pass

        # Milestone: duration == 0 in source
        raw_dur_str = _safe_str(row.get("Duration", ""))
        is_milestone = re.search(r"^0\s*days?", raw_dur_str, re.IGNORECASE) is not None

        # Predecessors
        pred_raw  = _safe_str(row.get("Predecessors", ""))
        deps      = _parse_predecessors(pred_raw, id_map)

        # Outline level for bar_label (show short label on milestones)
        try:
            outline_level = int(float(_safe_str(row.get("Outline Level", "0")) or "0"))
        except (ValueError, TypeError):
            outline_level = 0

        tasks.append({
            "id":               task_id,
            "parent_id":        parent_map.get(task_id),
            "task_name":        name,
            "start_date":       start,
            "finish_date":      finish,
            "duration":         dur_days,
            "percent_complete": 0,
            "status":           "grey",
            "resource_names":   "",
            "milestone":        is_milestone,
            "dependencies":     deps,
            "bar_label":        name[:12] if is_milestone else "",
            "bar_annotation":   "",
            "row_color":        "",
            "outline_level":    outline_level,
            "active":           active,
            "source":           sheet_key,
        })

    return tasks


# ── OPL → Gantt converters ────────────────────────────────────────────────────

def _col(record: dict, *keywords) -> str:
    """Return first non-empty value whose column name contains any keyword (case-insensitive)."""
    for kw in keywords:
        for k, v in record.items():
            if kw.lower() in k.lower():
                val = _safe_str(v)
                if val:
                    return val
    return ""


def _opl_due_date(record: dict) -> str:
    """Find a due/target date column and parse it. Prefers 'due/target' over generic 'date'."""
    for pattern in (r"due|target|finish|end", r"date"):
        for k, v in record.items():
            if re.search(pattern, k, re.I):
                parsed = _parse_excel_date(v)
                if parsed:
                    return parsed
    return ""


def _opl_status(record: dict, due_str: str) -> tuple[str, int]:
    """Return (gantt_status, percent_complete) from OPL record."""
    status_val = _col(record, "status", "state").lower()
    if any(w in status_val for w in ("close", "done", "complet", "finish")):
        return "green", 100
    if due_str:
        try:
            due_dt = datetime.fromisoformat(due_str).date()
            today  = date.today()
            if due_dt < today:
                return "red", 0
            if (due_dt - today).days <= 7:
                return "yellow", 0
        except Exception:
            pass
    return "grey", 0


def _import_opl_from_tracker() -> list[dict]:
    """Read OPL from both trackers and return Gantt task list grouped by area."""
    import sys as _sys
    _sys.path.insert(0, str(_ROOT))
    try:
        from backend.tracker_reader import read_sheets
    except ImportError:
        return []

    pjm_path = os.getenv("TRACKER_PJM", "")
    sw_path  = os.getenv("TRACKER_SW",  "")
    paths    = {"pjm": pjm_path, "sw": sw_path}
    today    = date.today().isoformat()
    tasks: list[dict] = []
    ctr = [0]

    def nid() -> str:
        ctr[0] += 1
        return f"opl_{ctr[0]}"

    for area_key, area_label, tracker_key, sheet_name in _OPL_AREAS:
        path = paths.get(tracker_key, "")
        if not path or not Path(path).exists():
            continue
        try:
            data = read_sheets(path, [sheet_name])
        except Exception:
            continue
        records = data.get(sheet_name, [])
        if not records:
            continue

        parent_id   = nid()
        child_tasks = []

        for rec in records:
            name = (
                _col(rec, "topic", "issue", "action", "description", "subject", "item")
                or next((str(v) for v in rec.values() if _safe_str(v) and len(_safe_str(v)) > 4), "Open Point")
            )
            name  = name[:150]
            due   = _opl_due_date(rec) or today
            owner = _col(rec, "owner", "responsible", "assignee", "pic", "person")
            status, pct = _opl_status(rec, due)

            try:
                f_dt  = datetime.fromisoformat(due)
                n_dt  = datetime.combine(date.today(), datetime.min.time())
                delta = max(1, int((f_dt - n_dt).days * 0.5) or 7)
                start = (n_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                if f_dt <= n_dt:
                    start = (f_dt - timedelta(days=7)).strftime("%Y-%m-%d")
            except Exception:
                start = today

            try:
                dur = max(1, (datetime.fromisoformat(due) - datetime.fromisoformat(start)).days)
            except Exception:
                dur = 1

            cid = nid()
            child_tasks.append({
                "id": cid, "parent_id": parent_id,
                "task_name": name, "start_date": start, "finish_date": due,
                "duration": dur, "percent_complete": pct, "status": status,
                "resource_names": owner, "milestone": False, "dependencies": [],
                "bar_label": "", "bar_annotation": f"[{area_key.upper()}]",
                "row_color": "", "outline_level": 2, "active": True, "source": "opl",
                "_opl_data": {k: _safe_str(v) for k, v in rec.items() if _safe_str(v)},
            })

        if not child_tasks:
            continue

        child_starts   = [t["start_date"]  for t in child_tasks if t["start_date"]]
        child_finishes = [t["finish_date"] for t in child_tasks if t["finish_date"]]
        p_start  = min(child_starts)   if child_starts   else today
        p_finish = max(child_finishes) if child_finishes else today
        try:
            p_dur = max(0, (datetime.fromisoformat(p_finish) - datetime.fromisoformat(p_start)).days)
        except Exception:
            p_dur = 0

        tasks.append({
            "id": parent_id, "parent_id": None,
            "task_name": area_label, "start_date": p_start, "finish_date": p_finish,
            "duration": p_dur, "percent_complete": 0, "status": "grey",
            "resource_names": "", "milestone": False, "dependencies": [],
            "bar_label": "", "bar_annotation": "", "row_color": "",
            "outline_level": 1, "active": True, "source": "opl",
        })
        tasks.extend(child_tasks)

    return tasks


# ── File I/O ──────────────────────────────────────────────────────────────────

def _load_saved() -> dict:
    """Load planning_data.json → {master: [...], sw: [...]}."""
    if not _PLANNING_FILE.exists():
        return {}
    try:
        return json.loads(_PLANNING_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error("planning_data.json is corrupt: %s", e)
        return {}
    except OSError as e:
        logger.error("Cannot read planning_data.json: %s", e)
        return {}


def _save_all(data: dict) -> str:
    """Atomic write to planning_data.json, return saved_at timestamp."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved_at = datetime.now().isoformat()
    data["saved_at"] = saved_at
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=_OUTPUT_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, _PLANNING_FILE)
        except Exception:
            os.unlink(tmp_path)
            raise
    except OSError as e:
        logger.error("Failed to save planning_data.json: %s", e)
        raise
    return saved_at


def _import_from_excel(sheet_key: str) -> list[dict]:
    """Read sheet from Project_plan_mpp_extract.xlsx → list of gantt tasks."""
    import pandas as pd, warnings
    warnings.filterwarnings("ignore")

    if not _MPP_XLSX.exists():
        return []

    excel_sheet = SHEET_MAP[sheet_key]
    df = pd.read_excel(_MPP_XLSX, sheet_name=excel_sheet, engine="openpyxl")
    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]
    rows = []
    for _, row in df.iterrows():
        rows.append({col: row[col] for col in df.columns})

    return _rows_to_gantt(rows, sheet_key)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/planning")
def get_planning(sheet: str = Query("master")):
    """Return tasks for one sheet.
    opl → imports fresh from tracker (or saved edits if user modified).
    master/sw/peru → saved JSON or Excel import.
    """
    sheet = sheet.lower()
    if sheet not in VALID_SHEETS:
        raise HTTPException(status_code=400, detail=f"sheet must be one of {sorted(VALID_SHEETS)}")

    saved = _load_saved()
    if sheet in saved and isinstance(saved[sheet], list):
        return {
            "tasks":  saved[sheet],
            "meta":   {"source": "planning_data.json", "last_saved": saved.get("saved_at", ""), "sheet": sheet},
        }

    if sheet == "opl":
        try:
            tasks = _import_opl_from_tracker()
            return {
                "tasks": tasks,
                "meta":  {"source": "tracker_import", "last_saved": "", "sheet": sheet},
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"OPL tracker import failed: {exc}")

    # Excel import (master / sw / peru)
    try:
        tasks = _import_from_excel(sheet)
        return {
            "tasks": tasks,
            "meta":  {"source": "excel_import", "last_saved": "", "sheet": sheet},
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Excel import failed: {exc}")


@router.post("/api/planning")
def save_planning(body: SavePlanningRequest):
    """Persist tasks for one sheet and create a version snapshot."""
    sheet = body.sheet.lower()
    if sheet not in VALID_SHEETS:
        raise HTTPException(status_code=400, detail=f"sheet must be one of {sorted(VALID_SHEETS)}")

    saved = _load_saved()
    saved[sheet] = body.tasks
    try:
        saved_at = _save_all(saved)
        # Create version snapshot (fire-and-forget, non-blocking)
        try:
            version = _create_version(sheet, body.tasks, body.label)
            version_id = version["id"]
            diff       = version["diff"]
        except Exception:
            version_id = ""
            diff       = ""
        return {
            "ok":         True,
            "saved_at":   saved_at,
            "task_count": len(body.tasks),
            "sheet":      sheet,
            "version_id": version_id,
            "diff":       diff,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Save failed: {exc}")


@router.delete("/api/planning")
def reset_planning(sheet: str = Query(...)):
    """Delete saved data for one sheet, forcing re-import from Excel on next GET."""
    sheet = sheet.lower()
    if sheet not in VALID_SHEETS:
        raise HTTPException(status_code=400, detail=f"sheet must be one of {sorted(VALID_SHEETS)}")

    saved = _load_saved()
    if sheet in saved:
        del saved[sheet]
        try:
            _save_all(saved)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Reset failed: {exc}")

    return {"ok": True, "sheet": sheet, "message": "Reset to Excel source"}


# ── Version helpers ────────────────────────────────────────────────────────────

def _load_versions() -> dict:
    """Load planning_versions.json → { sheet: [ version_entry, ... ] }"""
    if not _VERSIONS_FILE.exists():
        return {}
    try:
        return json.loads(_VERSIONS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error("planning_versions.json is corrupt: %s", e)
        return {}
    except OSError as e:
        logger.error("Cannot read planning_versions.json: %s", e)
        return {}


def _save_versions(data: dict) -> None:
    """Atomic write for versions file."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=_OUTPUT_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, _VERSIONS_FILE)
        except Exception:
            os.unlink(tmp_path)
            raise
    except OSError as e:
        logger.error("Failed to save planning_versions.json: %s", e)
        raise


def _diff_summary(old_tasks: list[dict], new_tasks: list[dict]) -> str:
    """
    Produce a short human-readable summary of what changed between two task lists.
    Returns a 1-3 line string.
    """
    old_map  = {t["id"]: t for t in old_tasks}
    new_map  = {t["id"]: t for t in new_tasks}
    old_ids  = set(old_map)
    new_ids  = set(new_map)

    added   = new_ids - old_ids
    removed = old_ids - new_ids
    changed = []

    FIELDS = ["task_name", "start_date", "finish_date", "duration", "percent_complete",
              "status", "dependencies", "bar_label", "milestone", "resource_names"]

    for tid in old_ids & new_ids:
        o, n = old_map[tid], new_map[tid]
        diffs = [f for f in FIELDS if o.get(f) != n.get(f)]
        if diffs:
            changed.append((n.get("task_name", tid), diffs))

    parts = []
    if added:
        names = ", ".join(new_map[i].get("task_name", i)[:20] for i in list(added)[:3])
        parts.append(f"Added {len(added)} task(s): {names}{'…' if len(added)>3 else ''}")
    if removed:
        names = ", ".join(old_map[i].get("task_name", i)[:20] for i in list(removed)[:3])
        parts.append(f"Removed {len(removed)} task(s): {names}{'…' if len(removed)>3 else ''}")
    if changed:
        sample = changed[:3]
        desc = "; ".join(f"{name[:20]} ({', '.join(fs)})" for name, fs in sample)
        parts.append(f"Changed {len(changed)} task(s): {desc}{'…' if len(changed)>3 else ''}")
    if not parts:
        parts.append("No changes detected")
    return " | ".join(parts)


def _create_version(sheet: str, tasks: list[dict], label: str = "") -> dict:
    """
    Snapshot current tasks into versions file.
    Returns the new version entry (without full tasks for the list endpoint).
    """
    versions_data = _load_versions()
    sheet_versions: list = versions_data.get(sheet, [])

    # Build diff vs. previous version
    prev_tasks = sheet_versions[0]["tasks"] if sheet_versions else []
    diff = _diff_summary(prev_tasks, tasks)

    vid = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
    entry = {
        "id":         vid,
        "sheet":      sheet,
        "saved_at":   datetime.now().isoformat(),
        "label":      label.strip() or "",
        "task_count": len(tasks),
        "diff":       diff,
        "tasks":      tasks,   # full snapshot
    }

    # Prepend (newest first), trim to MAX_VERSIONS
    sheet_versions = [entry] + sheet_versions
    if len(sheet_versions) > MAX_VERSIONS:
        sheet_versions = sheet_versions[:MAX_VERSIONS]
    versions_data[sheet] = sheet_versions
    _save_versions(versions_data)
    return entry


# ── Version endpoints ──────────────────────────────────────────────────────────

@router.get("/api/planning/versions")
def list_versions(sheet: str = Query("master"), limit: int = Query(20)):
    """Return version list for a sheet (newest first). Tasks are NOT included (too large)."""
    sheet = sheet.lower()
    if sheet not in VALID_SHEETS:
        raise HTTPException(status_code=400, detail=f"sheet must be one of {sorted(VALID_SHEETS)}")
    data   = _load_versions()
    entries = data.get(sheet, [])[:limit]
    # Strip tasks from list view — return metadata only
    return {
        "sheet":    sheet,
        "versions": [
            {k: v for k, v in e.items() if k != "tasks"}
            for e in entries
        ]
    }


@router.get("/api/planning/versions/{vid}")
def get_version(vid: str, sheet: str = Query("master")):
    """Return full task list for a specific version."""
    sheet = sheet.lower()
    data  = _load_versions()
    for entry in data.get(sheet, []):
        if entry["id"] == vid:
            return entry
    raise HTTPException(status_code=404, detail=f"Version {vid} not found for sheet '{sheet}'")


@router.delete("/api/planning/versions/{vid}")
def delete_version(vid: str, sheet: str = Query("master")):
    """Delete a specific version."""
    sheet = sheet.lower()
    data  = _load_versions()
    before = len(data.get(sheet, []))
    data[sheet] = [e for e in data.get(sheet, []) if e["id"] != vid]
    if len(data[sheet]) == before:
        raise HTTPException(status_code=404, detail=f"Version {vid} not found")
    _save_versions(data)
    return {"ok": True, "deleted": vid}
