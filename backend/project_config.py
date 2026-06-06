"""
Project Configuration System — DMC VCCU PM Assistant
Discovers all projects/*.json configs at startup and manages the active project.

Usage in main.py:
    from backend.project_config import get_active_project, set_active_project, list_projects

The active project's paths override the hardcoded defaults in main.py.
DMC VCCU D65P is always the fallback if no config is found or active.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pm_assistant.project_config")

_ROOT = Path(__file__).resolve().parent.parent
_PROJECTS_DIR = _ROOT / "projects"

# ── In-memory state ───────────────────────────────────────────────────────────
_projects: dict[str, dict] = {}    # {project_id: config_dict}
_active_id: str = "dmc_vccu_d65p"
_lock = threading.Lock()


# ── DMC VCCU fallback (used when no projects/ config found) ───────────────────
_DMC_VCCU_FALLBACK = {
    "project_id": "dmc_vccu_d65p",
    "display_name": "DMC VCCU D65P",
    "description": "Daihatsu Motor Company — Vehicle Control & Charging Unit",
    "active": True,
    "sharepoint": {
        "site_url": "https://sites.inside-share5.bosch.com/sites/178970/Documents",
        "webdav_base": r"\\sites.inside-share5.bosch.com@SSL\DavWWWRoot\sites\178970\Documents",
        "folder_structure": {"pm": "10_PM", "hw": "20_HW", "sw": "30_SW", "cal": "40_CAL", "sys": "50_SYS", "sc": "70_SC"},
    },
    "onedrive": {
        "tracker_pjm": r"C:\Users\GDN4HC\OneDrive - Bosch Group\DMC_D56P_VCCU - Activities_Track\DMC_VCCU_PjM_Activities tracker.xlsx",
        "tracker_sw":  r"C:\Users\GDN4HC\OneDrive - Bosch Group\DMC_D56P_VCCU - Activities_Track\DMC_VCCU_SW_Activities tracker.xlsx",
        "file_index":  r"C:\Users\GDN4HC\OneDrive - Bosch Group\DMC_D56P_VCCU - 99_Demo_AI_VCCU\Sharepoint_understand\DMC_VCCU_File_Path.xlsx",
        "ci_status_report": r"C:\Users\GDN4HC\OneDrive - Bosch Group\DMC_D56P_VCCU - 99_Demo_AI_VCCU\Sharepoint_understand\CI_Status_report.xlsx",
        "requirements_path": r"C:\Users\GDN4HC\OneDrive - Bosch Group\DMC_D56P_VCCU - 99_Demo_AI_VCCU\DMC_VCCU_Specific_Requirement",
    },
    "rag": {
        "project_collection": "dmc_vccu_d65p",
        "shared_collections": ["aspice_bosch", "ps_sc_system"],
        "source_folders": {},
    },
    "tracker_sheets": {
        "pjm_status": ["General"],
        "pjm_risk": ["Risk HW", "Risk CAL"],
        "pjm_ll": ["LL HW", "LL CAL"],
        "pjm_milestone": ["Master Sche."],
        "pjm_openpoints": {"overall": "General", "ecu_pjm": "Summary", "hw": "HW", "cal": "CAL"},
        "sw_risk": ["Risk SW"],
        "sw_ll": ["LL SW"],
        "sw_milestone": ["Master Sche.", "SW Sche."],
        "sw_openpoints": {"sw": "SW"},
    },
    "doc_passwords": ["boschdmc", "dmcbosch", "bosch2dmc", "db49db49"],
    "stable_folders": ["10_PM/B-Mngt", "50_SYS", "70_SC"],
    "volatile_folders": ["30_SW", "40_CAL"],
}


# ── Discovery & Loading ────────────────────────────────────────────────────────

def discover_projects() -> int:
    """Scan projects/*.json and load all configs into memory. Returns count."""
    global _projects, _active_id
    found: dict[str, dict] = {}

    if _PROJECTS_DIR.exists():
        for f in sorted(_PROJECTS_DIR.glob("*.json")):
            try:
                cfg = json.loads(f.read_text(encoding="utf-8"))
                pid = cfg.get("project_id")
                if not pid:
                    logger.warning(f"projects/{f.name}: missing project_id — skipped")
                    continue
                found[pid] = cfg
                logger.info(f"Loaded project config: {pid} ({cfg.get('display_name', '')})")
            except Exception as e:
                logger.warning(f"Failed to load {f}: {e}")

    # Always ensure DMC VCCU fallback is available
    if "dmc_vccu_d65p" not in found:
        found["dmc_vccu_d65p"] = _DMC_VCCU_FALLBACK

    with _lock:
        _projects = found
        # Set active: prefer existing _active_id, then first with active=True, then first found
        if _active_id not in found:
            active_candidates = [p for p in found.values() if p.get("active")]
            _active_id = active_candidates[0]["project_id"] if active_candidates else next(iter(found))

    logger.info(f"Projects loaded: {list(found.keys())} | active: {_active_id}")
    return len(found)


def get_active_project() -> dict:
    """Return the currently active project config dict."""
    with _lock:
        return dict(_projects.get(_active_id, _DMC_VCCU_FALLBACK))


def set_active_project(project_id: str) -> bool:
    """Switch the active project. Returns True if successful."""
    global _active_id
    with _lock:
        if project_id not in _projects:
            return False
        # Deactivate all, activate chosen
        for pid, cfg in _projects.items():
            cfg["active"] = (pid == project_id)
        _active_id = project_id
    logger.info(f"Active project switched to: {project_id}")
    return True


def list_projects() -> list[dict]:
    """Return list of all project configs (summary fields only)."""
    with _lock:
        return [
            {
                "project_id": cfg.get("project_id"),
                "display_name": cfg.get("display_name", cfg.get("project_id")),
                "description": cfg.get("description", ""),
                "active": cfg.get("project_id") == _active_id,
            }
            for cfg in _projects.values()
        ]


def get_project(project_id: str) -> Optional[dict]:
    """Return full config for a specific project_id, or None if not found."""
    with _lock:
        cfg = _projects.get(project_id)
        return dict(cfg) if cfg else None


def save_project(project_id: str, config: dict) -> bool:
    """Persist an updated project config to projects/<id>.json and update in-memory."""
    try:
        _PROJECTS_DIR.mkdir(exist_ok=True)
        config["project_id"] = project_id
        path = _PROJECTS_DIR / f"{project_id}.json"
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        with _lock:
            _projects[project_id] = config
        logger.info(f"Saved project config: {project_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to save project {project_id}: {e}")
        return False


# ── Convenience accessors (used in main.py endpoints) ─────────────────────────

def get_tracker_pjm_path() -> str:
    return get_active_project().get("onedrive", {}).get("tracker_pjm", "")


def get_tracker_sw_path() -> str:
    return get_active_project().get("onedrive", {}).get("tracker_sw", "")


def get_sp_file_index_path() -> str:
    return get_active_project().get("onedrive", {}).get("file_index", "")


def get_ci_status_xlsx_path() -> str:
    return get_active_project().get("onedrive", {}).get("ci_status_report", "")


def get_requirements_path() -> str:
    return get_active_project().get("onedrive", {}).get("requirements_path", "")


def get_sp_site_url() -> str:
    return get_active_project().get("sharepoint", {}).get("site_url", "")


def get_sp_webdav_base() -> str:
    return get_active_project().get("sharepoint", {}).get("webdav_base", "")


def get_rag_project_collection() -> str:
    return get_active_project().get("rag", {}).get("project_collection", "dmc_vccu_d65p")


def get_doc_passwords() -> list[str]:
    return get_active_project().get("doc_passwords", ["boschdmc", "dmcbosch", "bosch2dmc", "db49db49"])


def get_tracker_sheets() -> dict:
    return get_active_project().get("tracker_sheets", _DMC_VCCU_FALLBACK["tracker_sheets"])
