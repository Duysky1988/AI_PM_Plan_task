"""
Bosch Super OPL Bridge — DMC VCCU PM Assistant
Connects to rb-superopl.emea.bosch.com REST API using API key auth.

GET  /api/bosch-opl/tasks          → fetch all tasks from Bosch OPL
POST /api/bosch-opl/sync           → pull Bosch tasks → merge into Local OPL
POST /api/bosch-opl/push/{local_id} → push one Local OPL entry → create on Bosch
POST /api/bosch-opl/push-all       → push all local entries not yet on Bosch
GET  /api/bosch-opl/status         → connectivity check

Bosch API reference:
  GET  https://rb-superopl.emea.bosch.com/api/opls/{opl}/tasks/?key={key}
  POST https://rb-superopl.emea.bosch.com/api/opls/{opl}/tasks/?key={key}
       Required fields: subject, owner, loginUser, taskStart (Y-m-d), endDate (Y-m-d), type (int)
"""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
import urllib3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("pm_assistant.bosch_opl")
router = APIRouter()

# ── Config ─────────────────────────────────────────────────────────────────────
_ROOT       = Path(__file__).resolve().parent.parent
# Use same OUTPUT_DIR as super_opl_api.py — respects .env override
_OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(_ROOT / "outputs")))
_OPL_FILE   = _OUTPUT_DIR / "super_opl.json"

def _get_opl_file() -> Path:
    """Re-resolve at call time so .env changes after import are picked up."""
    return Path(os.getenv("OUTPUT_DIR", str(_ROOT / "outputs"))) / "super_opl.json"

BOSCH_OPL_NUMBER = int(os.getenv("BOSCH_OPL_NUMBER", "340408"))
BOSCH_API_KEY    = os.getenv("Super_OPL_API", "MjgwNDgzMjA5V1BWWFVNamcyTWpJM0")
BOSCH_LOGIN_USER = os.getenv("BOSCH_LOGIN_USER", "gdn4hc")
BOSCH_BASE_URL   = "https://rb-superopl.emea.bosch.com"
PROXIES = {
    "https": os.getenv("HTTPS_PROXY", "http://rb-proxy-apac.bosch.com:8080"),
    "http":  os.getenv("HTTP_PROXY",  "http://rb-proxy-apac.bosch.com:8080"),
}

# ── Bosch task type mapping ────────────────────────────────────────────────────
# Bosch: 1=Task, 2=Information, 3=Information(note?), 4=Decision, 5=Risk, 6=Problem
_TYPE_BOSCH_TO_LOCAL = {1: "Task", 2: "Information", 3: "Information", 4: "Decision", 5: "Risk", 6: "Problem"}
_TYPE_LOCAL_TO_BOSCH = {"Task": 1, "Information": 2, "Decision": 4, "Risk": 5, "Subtask": 1}
_STATUS_BOSCH_TO_LOCAL = {0: "running", 1: "closed", 2: "on_hold", 3: "rejected"}
_STATUS_LOCAL_TO_BOSCH = {"running": 0, "closed": 1, "on_hold": 2, "rejected": 3, "overdue": 0, "draft": 0}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _bosch_get(path: str) -> dict:
    url = f"{BOSCH_BASE_URL}{path}?key={BOSCH_API_KEY}"
    try:
        r = requests.get(url, proxies=PROXIES, verify=False, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Bosch OPL unreachable: {e}")


def _bosch_post(path: str, payload: dict) -> dict:
    url = f"{BOSCH_BASE_URL}{path}?key={BOSCH_API_KEY}"
    try:
        r = requests.post(url, json=payload, proxies=PROXIES, verify=False, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Bosch OPL unreachable: {e}")


def _bosch_delete(path: str, payload: dict = None) -> dict:
    url = f"{BOSCH_BASE_URL}{path}?key={BOSCH_API_KEY}"
    try:
        r = requests.delete(url, json=payload or {}, proxies=PROXIES, verify=False, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Bosch OPL unreachable: {e}")


def _extract_date(val) -> str:
    """Extract ISO date string from Bosch date object or plain string."""
    if not val:
        return ""
    if isinstance(val, str):
        return val[:10]
    if isinstance(val, dict):
        return val.get("date", "")[:10]
    return ""


def _load_local() -> list:
    opl_file = _get_opl_file()
    opl_file.parent.mkdir(parents=True, exist_ok=True)
    if not opl_file.exists():
        return []
    try:
        return json.loads(opl_file.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_local(entries: list):
    _get_opl_file().write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _bosch_task_to_local(t: dict) -> dict:
    """Convert Bosch API task dict → Local OPL entry dict."""
    responsible = t.get("responsible", "") or ""
    # Extract connected risk IDs (dict keyed by riskId string)
    connected_risks = t.get("connectedRisks") or {}
    linked_risk_ids = [str(v.get("riskId", k)) for k, v in connected_risks.items()] if connected_risks else []
    return {
        "id":              f"BOSCH-{t['taskId']}",
        "bosch_task_id":   t["taskId"],
        "entry_type":      _TYPE_BOSCH_TO_LOCAL.get(t.get("type", 1), "Task"),
        "owner":           t.get("ownerFistName", "") + " " + t.get("ownerLastName", ""),
        "owner_login":     t.get("owner", ""),
        "input_date":      _extract_date(t.get("startDate") or t.get("taskStart")),
        "responsible":     [responsible] if responsible else [],
        "subject":         t.get("subject", ""),
        "description":     t.get("description", ""),
        "category":        t.get("category", ""),
        "source":          t.get("source", ""),
        "due_date":        _extract_date(t.get("endDateWill") or t.get("endDateActual")),
        "priority":        _normalize_priority(t.get("prio", "")),
        "status":          _STATUS_BOSCH_TO_LOCAL.get(t.get("status", 0), "running"),
        "remarks":         t.get("result", ""),
        "last_change":     _extract_date(t.get("lastChangeTime")),
        "last_change_by":  t.get("lastChangeLoginFistName", "") + " " + t.get("lastChangeLoginLastName", ""),
        "last_note":       "",
        "pinned":          False,
        "created_at":      _extract_date(t.get("startDate") or t.get("taskStart")),
        "linked_risk_ids": linked_risk_ids,  # list of Bosch riskId strings this task is a measure for
        "sync_source":     "bosch",
    }


def _normalize_priority(prio) -> str:
    """Bosch API → Local priority label."""
    if not prio:
        return ""
    p = str(prio).upper()
    if p in ("A", "HIGH", "H", "3"):    return "High"
    if p in ("B", "MEDIUM", "MED", "M", "2"): return "Medium"
    if p in ("C", "D", "E", "LOW", "L", "1"): return "Low"
    return ""


def _local_prio_to_bosch(prio) -> str:
    """Local priority label → Bosch A/B/C/D/E scale."""
    if not prio:
        return ""
    p = str(prio).lower()
    if p == "high":   return "A"
    if p == "medium": return "B"
    if p == "low":    return "C"
    return ""


def _local_to_bosch_payload(entry: dict) -> dict:
    """Convert Local OPL entry → Bosch API create payload."""
    today = date.today().isoformat()

    # Responsible: take first item from list, fallback to login user
    responsible = ""
    if isinstance(entry.get("responsible"), list) and entry["responsible"]:
        responsible = entry["responsible"][0]

    # owner_login: prefer stored login, fallback to BOSCH_LOGIN_USER
    # (local entries created via UI only have display name like "Duy", not NT login)
    owner_login = entry.get("owner_login") or BOSCH_LOGIN_USER

    # Bosch NT login is max 8 chars, all lowercase, no spaces (e.g. "gdn4hc")
    # Display names like "Duy" or "Duy Nguyen" are not valid — fall back to login user
    def _is_nt_login(s: str) -> bool:
        return bool(s) and len(s) <= 8 and s.replace("_", "").isalnum() and s == s.lower()

    if not _is_nt_login(responsible):
        responsible = BOSCH_LOGIN_USER

    bosch_prio = _local_prio_to_bosch(entry.get("priority", ""))

    payload = {
        "subject":     entry.get("subject", "(no subject)"),
        "description": entry.get("description", ""),
        "owner":       owner_login,
        "responsible": responsible or owner_login,
        "loginUser":   BOSCH_LOGIN_USER,
        "taskStart":   entry.get("input_date") or today,
        "endDate":     entry.get("due_date") or today,
        "type":        _TYPE_LOCAL_TO_BOSCH.get(entry.get("entry_type", "Task"), 1),
        "category":    entry.get("category", "") or None,
        "source":      entry.get("source", "") or None,
    }
    if bosch_prio:
        payload["prio"] = bosch_prio
    return payload


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/api/bosch-opl/status")
def bosch_opl_status():
    """Check connectivity to Bosch Super OPL API."""
    try:
        data = _bosch_get(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/")
        count = len(data.get("data", {}))
        return {"connected": True, "opl": BOSCH_OPL_NUMBER, "task_count": count}
    except HTTPException as e:
        return {"connected": False, "error": e.detail}


@router.get("/api/bosch-opl/tasks")
def get_bosch_tasks():
    """Fetch all tasks from Bosch Super OPL and return as list."""
    data = _bosch_get(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/")
    tasks_raw = data.get("data", {})
    tasks = [_bosch_task_to_local(t) for t in tasks_raw.values()]
    tasks.sort(key=lambda x: x.get("input_date", ""), reverse=True)
    return {"total": len(tasks), "opl": BOSCH_OPL_NUMBER, "tasks": tasks}


@router.post("/api/bosch-opl/sync")
def sync_from_bosch():
    """
    Pull all tasks from Bosch Super OPL → merge into Local OPL.
    - Existing BOSCH-{id} entries are updated.
    - New Bosch tasks are added.
    - Local-only entries are untouched.
    Returns counts: added, updated, unchanged, local_only.
    """
    data = _bosch_get(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/")
    bosch_tasks = data.get("data", {})

    local = _load_local()
    # Index local by bosch_task_id for fast lookup
    local_by_bosch_id = {
        str(e.get("bosch_task_id")): i
        for i, e in enumerate(local)
        if e.get("bosch_task_id")
    }

    added = updated = unchanged = 0
    for task_id_str, t in bosch_tasks.items():
        new_entry = _bosch_task_to_local(t)
        if task_id_str in local_by_bosch_id:
            idx = local_by_bosch_id[task_id_str]
            old = local[idx]
            # Preserve local-only fields
            new_entry["pinned"]    = old.get("pinned", False)
            new_entry["last_note"] = old.get("last_note", "")
            if old == new_entry:
                unchanged += 1
            else:
                local[idx] = new_entry
                updated += 1
        else:
            local.append(new_entry)
            added += 1

    local_only = sum(1 for e in local if not e.get("bosch_task_id") and e.get("status") != "deleted")
    _save_local(local)

    return {
        "success": True,
        "opl": BOSCH_OPL_NUMBER,
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "local_only": local_only,
        "total_local": len([e for e in local if e.get("status") != "deleted"]),
    }


class PushRequest(BaseModel):
    local_id: Optional[str] = None
    login_user: Optional[str] = None


@router.post("/api/bosch-opl/push/{local_id}")
def push_to_bosch(local_id: str, req: PushRequest = PushRequest()):
    """
    Push a single Local OPL entry to Bosch Super OPL (create new task).
    Saves the returned bosch_task_id back to the local entry.
    """
    local = _load_local()
    entry = next((e for e in local if e.get("id") == local_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Local entry {local_id} not found")
    if entry.get("bosch_task_id"):
        raise HTTPException(status_code=409, detail=f"Entry {local_id} already pushed (bosch_task_id={entry['bosch_task_id']}). Update not supported by Bosch API.")

    payload = _local_to_bosch_payload(entry)
    if req.login_user:
        payload["loginUser"] = req.login_user

    result = _bosch_post(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/", payload)
    if not result.get("result"):
        errors = result.get("errors", [])
        raise HTTPException(status_code=422, detail=f"Bosch API rejected: {errors}")

    bosch_id = result["data"]["taskId"]
    # Save bosch_task_id but keep original local ID (renaming causes 404 on re-push)
    entry["bosch_task_id"] = bosch_id
    entry["sync_source"] = "local→bosch"
    _save_local(local)

    return {"success": True, "bosch_task_id": bosch_id, "local_id": local_id}


@router.post("/api/bosch-opl/push-all")
def push_all_to_bosch(req: PushRequest = PushRequest()):
    """
    Push all Local OPL entries that have NOT yet been synced to Bosch.
    Skips entries that already have bosch_task_id or status=deleted.
    """
    local = _load_local()
    to_push = [
        e for e in local
        if not e.get("bosch_task_id") and e.get("status") != "deleted"
    ]

    pushed = []
    failed = []
    for entry in to_push:
        payload = _local_to_bosch_payload(entry)
        if req.login_user:
            payload["loginUser"] = req.login_user
        try:
            result = _bosch_post(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/", payload)
            if result.get("result"):
                bosch_id = result["data"]["taskId"]
                entry["bosch_task_id"] = bosch_id
                entry["sync_source"] = "local→bosch"
                pushed.append({"local_subject": entry.get("subject"), "bosch_task_id": bosch_id})
            else:
                failed.append({"subject": entry.get("subject"), "errors": result.get("errors", [])})
        except Exception as e:
            failed.append({"subject": entry.get("subject"), "error": str(e)})

    _save_local(local)
    return {"success": True, "pushed": len(pushed), "failed": len(failed), "details_pushed": pushed, "details_failed": failed}


# ── Risk mapping ────────────────────────────────────────────────────────────────
# riskType: 1=Risk, 2=Opportunity
# riskStatus: 0=New, 1=Active, 2=Closed, 3=Rejected
# riskCategory: 1=Commercial, 2=Timing, 3=Legal, 4=Resource, 5=Quality, 6=Technical, 7=Other
_RISK_STATUS_MAP = {0: "running", 1: "running", 2: "closed", 3: "rejected"}
# Bosch actual category IDs (verified from API error response)
_RISK_CATEGORY_MAP = {6: "Technical", 7: "Management", 8: "Commercial", 9: "External"}
_RISK_CATEGORY_TO_BOSCH = {v: k for k, v in _RISK_CATEGORY_MAP.items()}


def _get_risk_file() -> Path:
    return Path(os.getenv("OUTPUT_DIR", str(_ROOT / "outputs"))) / "bosch_risks.json"


def _load_risks() -> list:
    f = _get_risk_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_risks(entries: list):
    _get_risk_file().write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _measure_task_to_local(t: dict) -> dict:
    """Convert a Bosch task (that is a risk measure) to local measure dict."""
    return {
        "task_id":     t.get("taskId"),
        "bosch_task_id": t.get("taskId"),
        "subject":     t.get("subject", ""),
        "strategy":    t.get("source", ""),   # Bosch stores strategy in source field
        "description": t.get("description", ""),
        "owner":       t.get("owner", ""),
        "responsible": t.get("responsible", ""),
        "due_date":    _extract_date(t.get("endDateWill") or t.get("endDateActual")),
        "status":      _STATUS_BOSCH_TO_LOCAL.get(t.get("status", 0), "running"),
        "created_at":  _extract_date(t.get("startDate") or t.get("taskStart")),
    }


def _bosch_risk_to_local(r: dict, measures: list = None) -> dict:
    """Convert Bosch API risk dict → local risk entry. measures is pre-built list."""
    prob = r.get("probability")
    imp  = r.get("impact")
    score = round(prob * imp, 1) if prob and imp else None
    m_list = measures or []
    return {
        "id":              f"BRISK-{r['riskId']}",
        "bosch_risk_id":   r["riskId"],
        "entry_type":      "Risk",
        "subject":         r.get("riskName", ""),
        "description":     r.get("riskEffects", ""),
        "cause":           r.get("riskCause", ""),
        "category":        _RISK_CATEGORY_MAP.get(r.get("riskCategory", 7), "Other"),
        "owner":           r.get("ownerFistName", "") + " " + r.get("ownerLastName", ""),
        "owner_login":     r.get("owner", ""),
        "probability":     prob,
        "impact":          imp,
        "score":           score,
        "status":          _RISK_STATUS_MAP.get(r.get("riskStatus", 0), "running"),
        "remarks":         r.get("result", ""),
        "note":            r.get("note", ""),
        "created_at":      _extract_date(r.get("creationTime")),
        "last_change":     _extract_date(r.get("lastChangeTime")),
        "measures_count":  len(m_list),
        "measures":        m_list,
        "sync_source":     "bosch",
    }


def _build_measures_map_from_tasks(tasks_data: dict) -> dict:
    """
    Given Bosch tasks response data (dict keyed by taskId),
    return a dict mapping riskId (str) → list of measure dicts.
    Measures = tasks with connectedRisks field set.
    """
    risk_measures: dict = {}
    task_list = list(tasks_data.values()) if isinstance(tasks_data, dict) else (tasks_data or [])
    for t in task_list:
        connected = t.get("connectedRisks") or {}
        if not connected:
            continue
        for risk_id_str in connected:
            m = _measure_task_to_local(t)
            risk_measures.setdefault(risk_id_str, []).append(m)
    return risk_measures


def _local_risk_to_bosch_payload(entry: dict) -> dict:
    """Convert local risk entry → Bosch API create payload."""
    cat_name = entry.get("category", "Technical")
    # riskEffects is mandatory in Bosch — fallback to subject if description empty
    effects = entry.get("description") or entry.get("subject", "(no description)")
    return {
        "riskName":     entry.get("subject", "(no name)"),
        "riskEffects":  effects,
        "riskCause":    entry.get("cause", ""),
        "owner":        entry.get("owner_login") or entry.get("owner") or BOSCH_LOGIN_USER,
        "loginUser":    BOSCH_LOGIN_USER,
        "riskType":     1,
        "riskCategory": _RISK_CATEGORY_TO_BOSCH.get(cat_name, 7),  # fallback 7=Management
        **({"probability": entry["probability"]} if entry.get("probability") is not None else {}),
        **({"impact":      entry["impact"]}      if entry.get("impact")       is not None else {}),
    }


# ── Risk Routes ─────────────────────────────────────────────────────────────────

@router.get("/api/bosch-opl/risks")
def get_bosch_risks():
    """Fetch all risks from Bosch Super OPL, including measures from tasks."""
    risks_data = _bosch_get(f"/api/opls/{BOSCH_OPL_NUMBER}/risks/")
    tasks_data = _bosch_get(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/")
    measures_map = _build_measures_map_from_tasks(tasks_data.get("data") or {})
    risks = [
        _bosch_risk_to_local(r, measures_map.get(str(r["riskId"]), []))
        for r in (risks_data.get("data") or [])
    ]
    risks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"total": len(risks), "opl": BOSCH_OPL_NUMBER, "risks": risks}


@router.post("/api/bosch-opl/risks/sync")
def sync_risks_from_bosch():
    """
    Pull all risks + measures from Bosch → merge into local bosch_risks.json.
    Measures are fetched via tasks with connectedRisks field.
    Returns counts: added, updated, unchanged.
    """
    risks_data  = _bosch_get(f"/api/opls/{BOSCH_OPL_NUMBER}/risks/")
    tasks_data  = _bosch_get(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/")
    measures_map = _build_measures_map_from_tasks(tasks_data.get("data") or {})
    bosch_risks = risks_data.get("data") or []

    local = _load_risks()
    local_by_bosch_id = {str(e.get("bosch_risk_id")): i for i, e in enumerate(local) if e.get("bosch_risk_id")}

    added = updated = unchanged = 0
    for r in bosch_risks:
        bosch_measures = measures_map.get(str(r["riskId"]), [])
        new_entry = _bosch_risk_to_local(r, bosch_measures)
        key = str(r["riskId"])
        if key in local_by_bosch_id:
            idx = local_by_bosch_id[key]
            old = local[idx]
            # Preserve local-only fields
            new_entry["note"] = old.get("note", new_entry.get("note", ""))
            new_entry["id"]   = old.get("id", new_entry["id"])   # keep LRISK-xxx if pushed locally
            # Merge: keep locally-created measures (no bosch_task_id match) alongside Bosch ones
            bosch_task_ids = {str(m["task_id"]) for m in bosch_measures if m.get("task_id")}
            local_only_measures = [
                m for m in (old.get("measures") or [])
                if not m.get("bosch_task_id") or str(m.get("bosch_task_id")) not in bosch_task_ids
            ]
            new_entry["measures"] = bosch_measures + local_only_measures
            new_entry["measures_count"] = len(new_entry["measures"])
            if old == new_entry:
                unchanged += 1
            else:
                local[idx] = new_entry
                updated += 1
        else:
            local.append(new_entry)
            added += 1

    _save_risks(local)
    return {"success": True, "added": added, "updated": updated, "unchanged": unchanged, "total": len(local)}


class RiskPushRequest(BaseModel):
    subject:     str
    description: str = ""
    cause:       str = ""
    category:    str = "Technical"
    probability: Optional[int] = None   # Bosch scale 1-6
    impact:      Optional[int] = None   # Bosch scale 1-6
    owner_login: Optional[str] = None


@router.post("/api/bosch-opl/risks/push")
def push_risk_to_bosch(req: RiskPushRequest):
    """
    Create a new risk on Bosch Super OPL from provided data.
    Also saves it to local bosch_risks.json with the returned riskId.
    """
    entry = req.model_dump()
    entry["owner_login"] = entry.get("owner_login") or BOSCH_LOGIN_USER
    payload = _local_risk_to_bosch_payload(entry)
    result  = _bosch_post(f"/api/opls/{BOSCH_OPL_NUMBER}/risks/", payload)

    if not result.get("result"):
        raise HTTPException(status_code=422, detail=f"Bosch rejected: {result.get('errors', result)}")

    bosch_id = result["data"]["riskId"]
    local = _load_risks()
    new_local = _bosch_risk_to_local({
        "riskId":       bosch_id,
        "riskName":     req.subject,
        "riskEffects":  req.description,
        "riskCause":    req.cause,
        "riskCategory": _RISK_CATEGORY_TO_BOSCH.get(req.category, 7),
        "owner":        entry["owner_login"],
        "ownerFistName": "", "ownerLastName": "",
        "riskStatus":   0,
        "probability":  req.probability,
        "impact":       req.impact,
        "result": "", "note": "",
        "creationTime": {"date": date.today().isoformat()},
        "lastChangeTime": {"date": date.today().isoformat()},
    })
    new_local["sync_source"] = "local→bosch"
    local.append(new_local)
    _save_risks(local)

    return {"success": True, "bosch_risk_id": bosch_id}


# ── Lessons Learned ─────────────────────────────────────────────────────────────
# Bosch LL API: GET only — POST/PUT return "Method not implemented"
# status: 0=open, 1=closed, 2=rejected

_LL_STATUS_MAP = {0: "running", 1: "closed", 2: "rejected"}


def _get_ll_file() -> Path:
    return Path(os.getenv("OUTPUT_DIR", str(_ROOT / "outputs"))) / "bosch_lessons.json"


def _load_lessons() -> list:
    f = _get_ll_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_lessons(entries: list):
    _get_ll_file().write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _bosch_ll_to_local(ll: dict) -> dict:
    measures = ll.get("measures") or []
    return {
        "id":            "BLL-%d" % ll["llId"],
        "bosch_ll_id":   ll["llId"],
        "entry_type":    "Lesson",
        "subject":       ll.get("observation", ""),
        "observation":   ll.get("observation", ""),
        "cause":         ll.get("cause", ""),
        "actions":       ll.get("actions", ""),
        "phase":         ll.get("phase", ""),
        "category":      ll.get("categoryName") or "",
        "subcategory":   ll.get("subcategoryName") or "",
        "owner":         (ll.get("ownerFistName", "") + " " + ll.get("ownerLastName", "")).strip(),
        "owner_login":   ll.get("owner", ""),
        "status":        _LL_STATUS_MAP.get(ll.get("status", 0), "running"),
        "created_at":    _extract_date(ll.get("creationTime")),
        "measures_count": len(measures),
        "measures":      [
            {
                "task_id":   m.get("taskId"),
                "subject":   m.get("subject", ""),
                "owner":     m.get("owner", ""),
                "due_date":  _extract_date(m.get("endDateActual")),
                "status":    m.get("status", 0),
            }
            for m in measures
        ],
        "sync_source":   "bosch",
    }


@router.get("/api/bosch-opl/lessons")
def get_bosch_lessons():
    """Fetch all Lessons Learned from Bosch Super OPL (read-only)."""
    data = _bosch_get("/api/opls/%d/lessons/" % BOSCH_OPL_NUMBER)
    lessons = [_bosch_ll_to_local(ll) for ll in (data.get("data") or [])]
    lessons.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"total": len(lessons), "opl": BOSCH_OPL_NUMBER, "lessons": lessons,
            "push_supported": False, "note": "Bosch LL API is read-only (POST not implemented)"}


@router.post("/api/bosch-opl/lessons/sync")
def sync_lessons_from_bosch():
    """
    Pull all Lessons Learned from Bosch → merge into local bosch_lessons.json.
    Read-only sync — Bosch does not support creating LL via API.
    """
    data = _bosch_get("/api/opls/%d/lessons/" % BOSCH_OPL_NUMBER)
    bosch_lessons = data.get("data") or []

    local = _load_lessons()
    local_by_id = {str(e.get("bosch_ll_id")): i for i, e in enumerate(local) if e.get("bosch_ll_id")}

    added = updated = unchanged = 0
    for ll in bosch_lessons:
        new_entry = _bosch_ll_to_local(ll)
        key = str(ll["llId"])
        if key in local_by_id:
            idx = local_by_id[key]
            if local[idx] == new_entry:
                unchanged += 1
            else:
                local[idx] = new_entry
                updated += 1
        else:
            local.append(new_entry)
            added += 1

    _save_lessons(local)
    return {
        "success": True, "added": added, "updated": updated,
        "unchanged": unchanged, "total": len(local),
        "push_supported": False,
    }


# ── Local Risk CRUD ─────────────────────────────────────────────────────────────

def _next_local_risk_id(entries: list) -> str:
    nums = [int(e["id"].split("-")[1]) for e in entries
            if e.get("id","").startswith("LRISK-") and e["id"].split("-")[1].isdigit()]
    return "LRISK-%03d" % (max(nums) + 1 if nums else 1)


class LocalRiskEntry(BaseModel):
    subject:     str
    description: str = ""
    cause:       str = ""
    category:    str = "Technical"
    probability: Optional[int] = None   # 1-6
    impact:      Optional[int] = None   # 1-6
    owner:       str = ""
    owner_login: Optional[str] = None
    status:      str = "running"
    due_date:    Optional[str] = None


@router.get("/api/bosch-opl/local-risks")
def list_local_risks():
    """List all local risks (LRISK-xxx entries in bosch_risks.json)."""
    all_r = _load_risks()
    local = [r for r in all_r if str(r.get("id","")).startswith("LRISK-") and r.get("status") != "deleted"]
    local.sort(key=lambda x: x.get("created_at",""), reverse=True)
    return {"total": len(local), "risks": local}


@router.post("/api/bosch-opl/local-risks")
def create_local_risk(req: LocalRiskEntry):
    """Create a local risk entry (not yet pushed to Bosch)."""
    all_r = _load_risks()
    entry = {
        "id":             _next_local_risk_id(all_r),
        "entry_type":     "Risk",
        "subject":        req.subject,
        "description":    req.description,
        "cause":          req.cause,
        "category":       req.category,
        "probability":    req.probability,
        "impact":         req.impact,
        "score":          round(req.probability * req.impact, 1) if req.probability and req.impact else None,
        "owner":          req.owner or BOSCH_LOGIN_USER,
        "owner_login":    req.owner_login or BOSCH_LOGIN_USER,
        "status":         req.status,
        "due_date":       req.due_date or "",
        "created_at":     date.today().isoformat(),
        "measures":       [],
        "measures_count": 0,
        "sync_source":    "local",
    }
    all_r.append(entry)
    _save_risks(all_r)
    return entry


@router.put("/api/bosch-opl/local-risks/{risk_id}")
def update_local_risk(risk_id: str, req: LocalRiskEntry):
    all_r = _load_risks()
    idx = next((i for i, r in enumerate(all_r) if r.get("id") == risk_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"{risk_id} not found")
    all_r[idx].update({
        "subject": req.subject, "description": req.description, "cause": req.cause,
        "category": req.category, "probability": req.probability, "impact": req.impact,
        "score": round(req.probability * req.impact, 1) if req.probability and req.impact else None,
        "owner": req.owner, "owner_login": req.owner_login or BOSCH_LOGIN_USER,
        "status": req.status, "due_date": req.due_date or "",
    })
    _save_risks(all_r)
    return all_r[idx]


@router.delete("/api/bosch-opl/local-risks/{risk_id}")
def delete_local_risk(risk_id: str):
    all_r = _load_risks()
    idx = next((i for i, r in enumerate(all_r) if r.get("id") == risk_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"{risk_id} not found")
    all_r[idx]["status"] = "deleted"
    _save_risks(all_r)
    return {"success": True}


@router.post("/api/bosch-opl/local-risks/{risk_id}/push")
def push_local_risk(risk_id: str):
    """Push a local LRISK-xxx entry to Bosch Risk Management."""
    all_r = _load_risks()
    entry = next((r for r in all_r if r.get("id") == risk_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"{risk_id} not found")
    if entry.get("bosch_risk_id"):
        raise HTTPException(status_code=409, detail=f"{risk_id} already pushed (bosch_risk_id={entry['bosch_risk_id']})")
    payload = _local_risk_to_bosch_payload(entry)
    result  = _bosch_post(f"/api/opls/{BOSCH_OPL_NUMBER}/risks/", payload)
    if not result.get("result"):
        raise HTTPException(status_code=422, detail=f"Bosch rejected: {result.get('errors', result)}")
    bosch_id = result["data"]["riskId"]
    entry["bosch_risk_id"] = bosch_id
    entry["sync_source"]   = "local→bosch"
    # Init measures list if not present
    if "measures" not in entry:
        entry["measures"] = []
        entry["measures_count"] = 0
    _save_risks(all_r)
    return {"success": True, "bosch_risk_id": bosch_id, "local_id": risk_id}


# ── Risk Measures CRUD ──────────────────────────────────────────────────────────

class RiskMeasureEntry(BaseModel):
    subject:     str
    strategy:    str = "Mitigate"   # Mitigate | Transfer | Accept | Avoid
    description: str = ""
    owner_login: Optional[str] = None
    responsible: Optional[str] = None
    due_date:    Optional[str] = None


@router.get("/api/bosch-opl/local-risks/{risk_id}/measures")
def list_risk_measures(risk_id: str):
    """List all measures for a risk."""
    all_r = _load_risks()
    entry = next((r for r in all_r if r.get("id") == risk_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"{risk_id} not found")
    measures = [m for m in (entry.get("measures") or []) if m.get("status") != "deleted"]
    return {"risk_id": risk_id, "total": len(measures), "measures": measures}


@router.post("/api/bosch-opl/local-risks/{risk_id}/measures")
def create_risk_measure(risk_id: str, req: RiskMeasureEntry):
    """
    Create a measure for a risk.
    If risk has bosch_risk_id → also create task on Bosch with connectedRisks.
    Also creates a linked local OPL task in super_opl.json.
    """
    all_r = _load_risks()
    idx = next((i for i, r in enumerate(all_r) if r.get("id") == risk_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"{risk_id} not found")

    entry = all_r[idx]
    today = date.today().isoformat()
    owner_login = req.owner_login or BOSCH_LOGIN_USER
    responsible = req.responsible or owner_login

    def _is_nt_login(s):
        return bool(s) and len(s) <= 8 and s.replace("_", "").isalnum() and s == s.lower()
    if not _is_nt_login(responsible): responsible = BOSCH_LOGIN_USER
    if not _is_nt_login(owner_login):  owner_login = BOSCH_LOGIN_USER

    bosch_risk_id = entry.get("bosch_risk_id")
    bosch_task_id = None

    # Push to Bosch if risk is already on Bosch
    if bosch_risk_id:
        payload = {
            "subject":     req.subject,
            "description": req.description,
            "owner":       owner_login,
            "responsible": responsible,
            "loginUser":   BOSCH_LOGIN_USER,
            "taskStart":   today,
            "endDate":     req.due_date or today,
            "type":        7,   # Risk measure type on Bosch
            "source":      req.strategy,   # strategy stored in source field
            "connectedRisks": {str(bosch_risk_id): {"riskId": bosch_risk_id}},
        }
        result = _bosch_post(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/", payload)
        if not result.get("result"):
            raise HTTPException(status_code=422, detail=f"Bosch rejected: {result.get('errors', result)}")
        bosch_task_id = result["data"]["taskId"]

    measure = {
        "task_id":       bosch_task_id,
        "bosch_task_id": bosch_task_id,
        "subject":       req.subject,
        "strategy":      req.strategy,
        "description":   req.description,
        "owner":         owner_login,
        "responsible":   responsible,
        "due_date":      req.due_date or "",
        "status":        "running",
        "created_at":    today,
    }

    if "measures" not in entry:
        entry["measures"] = []
    entry["measures"].append(measure)
    entry["measures_count"] = len([m for m in entry["measures"] if m.get("status") != "deleted"])
    _save_risks(all_r)

    # Also create a local OPL task linked to this risk
    _create_linked_opl_task(req.subject, req.description, owner_login, req.due_date or today, risk_id, bosch_task_id)

    return {"success": True, "measure": measure,
            "bosch_task_id": bosch_task_id,
            "note": "Pushed to Bosch" if bosch_task_id else "Saved locally (risk not yet pushed to Bosch)"}


@router.delete("/api/bosch-opl/local-risks/{risk_id}/measures/{task_id}")
def delete_risk_measure(risk_id: str, task_id: str):
    """Delete a measure from a risk. If it has a Bosch task_id, also delete on Bosch."""
    all_r = _load_risks()
    idx = next((i for i, r in enumerate(all_r) if r.get("id") == risk_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"{risk_id} not found")

    entry = all_r[idx]
    measures = entry.get("measures") or []
    m_idx = next((i for i, m in enumerate(measures) if str(m.get("task_id") or m.get("bosch_task_id", "")) == task_id), None)
    if m_idx is None:
        raise HTTPException(status_code=404, detail=f"Measure {task_id} not found")

    m = measures[m_idx]
    bosch_deleted = False
    if m.get("bosch_task_id"):
        try:
            result = _bosch_delete(
                f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/{m['bosch_task_id']}/",
                {"loginUser": BOSCH_LOGIN_USER}
            )
            bosch_deleted = bool(result.get("result"))
        except Exception:
            pass  # Bosch delete failure doesn't block local delete

    measures.pop(m_idx)
    entry["measures"] = measures
    entry["measures_count"] = len([m for m in measures if m.get("status") != "deleted"])
    _save_risks(all_r)

    # Also remove from local OPL tasks if linked
    _remove_linked_opl_task(m.get("bosch_task_id"))

    return {"success": True, "bosch_deleted": bosch_deleted}


def _create_linked_opl_task(subject: str, description: str, owner: str, due_date: str, risk_id: str, bosch_task_id=None):
    """Create a local OPL task entry linked to a risk measure."""
    opl_file = _get_opl_file()
    opl_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        entries = json.loads(opl_file.read_text(encoding="utf-8")) if opl_file.exists() else []
    except Exception:
        entries = []

    # Generate next OPL-xxx ID (only count OPL- prefix)
    nums = [int(e["id"].split("-")[1]) for e in entries
            if e.get("id", "").startswith("OPL-") and e["id"].split("-")[1].isdigit()]
    next_id = "OPL-%03d" % (max(nums) + 1 if nums else 1)

    new_task = {
        "id":              next_id,
        "bosch_task_id":   bosch_task_id,
        "entry_type":      "Task",
        "subject":         subject,
        "description":     description,
        "owner":           owner,
        "responsible":     [owner],
        "due_date":        due_date,
        "status":          "running",
        "linked_risk_id":  risk_id,
        "created_at":      date.today().isoformat(),
        "sync_source":     "local",
    }
    entries.append(new_task)
    opl_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return new_task


def _remove_linked_opl_task(bosch_task_id):
    """Soft-delete local OPL task linked to a Bosch task (if exists)."""
    if not bosch_task_id:
        return
    opl_file = _get_opl_file()
    if not opl_file.exists():
        return
    try:
        entries = json.loads(opl_file.read_text(encoding="utf-8"))
        for e in entries:
            if e.get("bosch_task_id") == bosch_task_id:
                e["status"] = "deleted"
        opl_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Local LL CRUD + push workaround ────────────────────────────────────────────
# Bosch LL API (llIncluded=0 on this OPL) blocks POST /lessons/.
# Workaround: push LL as task type=7 (LL Measure) with [LL] prefix in subject.

def _next_local_ll_id(entries: list) -> str:
    nums = [int(e["id"].split("-")[1]) for e in entries
            if e.get("id","").startswith("LLL-") and e["id"].split("-")[1].isdigit()]
    return "LLL-%03d" % (max(nums) + 1 if nums else 1)


class LocalLLEntry(BaseModel):
    observation: str
    cause:       str = ""
    actions:     str = ""
    phase:       str = ""
    category:    str = ""
    owner:       str = ""
    owner_login: Optional[str] = None
    status:      str = "running"


@router.get("/api/bosch-opl/local-lessons")
def list_local_lessons():
    """List all local LL entries (LLL-xxx entries)."""
    all_ll = _load_lessons()
    local = [ll for ll in all_ll if str(ll.get("id","")).startswith("LLL-") and ll.get("status") != "deleted"]
    local.sort(key=lambda x: x.get("created_at",""), reverse=True)
    return {"total": len(local), "lessons": local}


@router.post("/api/bosch-opl/local-lessons")
def create_local_lesson(req: LocalLLEntry):
    """Create a local LL entry."""
    all_ll = _load_lessons()
    entry = {
        "id":          _next_local_ll_id(all_ll),
        "entry_type":  "Lesson",
        "subject":     req.observation,
        "observation": req.observation,
        "cause":       req.cause,
        "actions":     req.actions,
        "phase":       req.phase,
        "category":    req.category,
        "owner":       req.owner or BOSCH_LOGIN_USER,
        "owner_login": req.owner_login or BOSCH_LOGIN_USER,
        "status":      req.status,
        "measures_count": 0,
        "measures":    [],
        "created_at":  date.today().isoformat(),
        "sync_source": "local",
    }
    all_ll.append(entry)
    _save_lessons(all_ll)
    return entry


@router.put("/api/bosch-opl/local-lessons/{ll_id}")
def update_local_lesson(ll_id: str, req: LocalLLEntry):
    all_ll = _load_lessons()
    idx = next((i for i, ll in enumerate(all_ll) if ll.get("id") == ll_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"{ll_id} not found")
    all_ll[idx].update({
        "subject": req.observation, "observation": req.observation,
        "cause": req.cause, "actions": req.actions,
        "phase": req.phase, "category": req.category,
        "owner": req.owner, "owner_login": req.owner_login or BOSCH_LOGIN_USER,
        "status": req.status,
    })
    _save_lessons(all_ll)
    return all_ll[idx]


@router.delete("/api/bosch-opl/local-lessons/{ll_id}")
def delete_local_lesson(ll_id: str):
    all_ll = _load_lessons()
    idx = next((i for i, ll in enumerate(all_ll) if ll.get("id") == ll_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"{ll_id} not found")
    all_ll[idx]["status"] = "deleted"
    _save_lessons(all_ll)
    return {"success": True}


@router.post("/api/bosch-opl/local-lessons/{ll_id}/push")
def push_local_lesson(ll_id: str):
    """
    Push local LL to Bosch as task type=7 (LL Measure workaround).
    Bosch OPL #340408 has llIncluded=0 so /lessons/ POST is blocked.
    Type-7 tasks appear in Bosch OPL task list and serve as LL records.
    """
    all_ll = _load_lessons()
    entry = next((ll for ll in all_ll if ll.get("id") == ll_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"{ll_id} not found")
    if entry.get("bosch_task_id"):
        raise HTTPException(status_code=409, detail=f"{ll_id} already pushed (bosch_task_id={entry['bosch_task_id']})")

    today = date.today().isoformat()
    payload = {
        "subject":     "[LL] " + entry.get("observation", "(no observation)"),
        "description": "Cause: %s\nActions: %s" % (entry.get("cause",""), entry.get("actions","")),
        "owner":       entry.get("owner_login") or BOSCH_LOGIN_USER,
        "responsible": entry.get("owner_login") or BOSCH_LOGIN_USER,
        "loginUser":   BOSCH_LOGIN_USER,
        "taskStart":   today,
        "endDate":     today,
        "type":        7,
        "source":      entry.get("phase", ""),
        "category":    entry.get("category", ""),
    }
    result = _bosch_post(f"/api/opls/{BOSCH_OPL_NUMBER}/tasks/", payload)
    if not result.get("result"):
        raise HTTPException(status_code=422, detail=f"Bosch rejected: {result.get('errors', result)}")

    bosch_task_id = result["data"]["taskId"]
    entry["bosch_task_id"] = bosch_task_id
    entry["sync_source"]   = "local→bosch(type7)"
    _save_lessons(all_ll)
    return {"success": True, "bosch_task_id": bosch_task_id, "local_id": ll_id,
            "note": "Pushed as Bosch task type=7 (LL Measure) — llIncluded=0 on this OPL"}


# ── Sync-All convenience endpoint ───────────────────────────────────────────────

@router.post("/api/bosch-opl/sync-all")
def sync_all():
    """Sync Tasks + Risks (with measures) + Lessons from Bosch in one call."""
    tasks_result   = sync_from_bosch()
    risks_result   = sync_risks_from_bosch()
    lessons_result = sync_lessons_from_bosch()
    return {
        "success": True,
        "tasks":   tasks_result,
        "risks":   risks_result,
        "lessons": lessons_result,
    }


# ── Unified read endpoints (local cache — no live Bosch call) ─────────────────

@router.get("/api/bosch-opl/all-risks")
def get_all_risks():
    """
    Return ALL risks from bosch_risks.json: BRISK-xxx (synced from Bosch) + LRISK-xxx (local).
    Use this for display — does not call Bosch API.
    Use POST /risks/sync first to pull latest from Bosch.
    """
    all_r = [r for r in _load_risks() if r.get("status") != "deleted"]
    all_r.sort(key=lambda x: (x.get("bosch_risk_id") is None, x.get("created_at", "")), reverse=True)
    bosch_count = sum(1 for r in all_r if str(r.get("id", "")).startswith("BRISK-"))
    local_count = sum(1 for r in all_r if str(r.get("id", "")).startswith("LRISK-"))
    return {"total": len(all_r), "bosch_count": bosch_count, "local_count": local_count, "risks": all_r}


@router.get("/api/bosch-opl/all-lessons")
def get_all_lessons():
    """
    Return ALL lessons from bosch_lessons.json: BLL-xxx (synced from Bosch) + LLL-xxx (local).
    Use this for display — does not call Bosch API.
    Use POST /lessons/sync first to pull latest from Bosch.
    """
    all_ll = [ll for ll in _load_lessons() if ll.get("status") != "deleted"]
    all_ll.sort(key=lambda x: (x.get("bosch_ll_id") is None, x.get("created_at", "")), reverse=True)
    bosch_count = sum(1 for ll in all_ll if str(ll.get("id", "")).startswith("BLL-"))
    local_count = sum(1 for ll in all_ll if str(ll.get("id", "")).startswith("LLL-"))
    return {"total": len(all_ll), "bosch_count": bosch_count, "local_count": local_count, "lessons": all_ll}


@router.get("/api/bosch-opl/all-tasks")
def get_all_tasks():
    """
    Return ALL tasks from super_opl.json: BOSCH-xxx (synced) + OPL-xxx (local).
    Use this for display — does not call Bosch API.
    Use POST /sync first to pull latest from Bosch.
    """
    all_t = [e for e in _load_local() if e.get("status") != "deleted"]
    all_t.sort(key=lambda x: (x.get("bosch_task_id") is None, x.get("created_at", "")), reverse=True)
    bosch_count = sum(1 for t in all_t if str(t.get("id", "")).startswith("BOSCH-"))
    local_count = sum(1 for t in all_t if str(t.get("id", "")).startswith("OPL-"))
    return {"total": len(all_t), "bosch_count": bosch_count, "local_count": local_count, "tasks": all_t}
