"""
CI Index — parses the CI Status Report (Excel primary, HTML fallback) and provides
a structured in-memory index: CI ID → {name, filename, folder, responsible, status, keywords}.

The query router in main.py checks this index before falling back to the static _DOC_ALIASES list.
Primary source: CI_Status_report.xlsx (local OneDrive path).
Fallback: SharePoint HTML via WebDAV UNC path (requires VPN, optional).
"""

import logging
import re
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pm_assistant.ci_index")

# ── In-memory store ────────────────────────────────────────────────────────────
_CI_INDEX: dict[str, dict] = {}   # {"CI-0016": {ci_id, name, filename, folder, responsible, status, keywords}}
_CI_KEYWORDS: list[tuple[str, str]] = []  # [(keyword_lower, ci_id), ...] sorted by keyword length desc
_ci_lock = threading.Lock()


# ── Public API ─────────────────────────────────────────────────────────────────

def get_ci_index() -> dict[str, dict]:
    """Return a copy of the current CI index."""
    with _ci_lock:
        return dict(_CI_INDEX)


def get_ci_count() -> int:
    with _ci_lock:
        return len(_CI_INDEX)


def lookup_by_keyword(query: str) -> Optional[dict]:
    """
    Find the best CI entry matching the user query.
    Returns the CI entry dict or None if no match.
    Uses longest-keyword-wins strategy (same as _DOC_ALIASES).
    """
    q_lower = query.lower()
    with _ci_lock:
        best_entry = None
        best_score = 0
        for kw, ci_id in _CI_KEYWORDS:
            if kw in q_lower and len(kw) > best_score:
                best_score = len(kw)
                best_entry = _CI_INDEX.get(ci_id)
    return best_entry


def load_ci_index(entries: list[dict]) -> int:
    """Populate the in-memory CI index from a parsed list. Returns entry count."""
    global _CI_INDEX, _CI_KEYWORDS
    new_index: dict[str, dict] = {}
    new_keywords: list[tuple[str, str]] = []

    for entry in entries:
        ci_id = entry.get("ci_id", "").strip()
        if not ci_id:
            continue
        # Normalise CI ID format: "CI0016" → "CI-0016"
        ci_id = re.sub(r"^CI\.?-?\s*(\d+)$", r"CI-\1", ci_id, flags=re.IGNORECASE)
        entry["ci_id"] = ci_id
        new_index[ci_id] = entry

        # Build keyword list: CI name words + explicit keywords list
        kws: list[str] = list(entry.get("keywords", []))
        name = entry.get("name", "")
        if name:
            kws.append(name.lower())
            # Also add abbreviated name (skip common words)
            words = [w for w in name.lower().split() if w not in {"the", "a", "an", "and", "of", "for", "plan", "report"}]
            if len(words) >= 2:
                kws.append(" ".join(words[:2]))

        for kw in kws:
            kw = kw.strip().lower()
            if kw and len(kw) >= 3:
                new_keywords.append((kw, ci_id))

    # Sort longest keyword first (longest-wins matching)
    new_keywords.sort(key=lambda x: -len(x[0]))

    with _ci_lock:
        _CI_INDEX = new_index
        _CI_KEYWORDS = new_keywords

    logger.info(f"CI index loaded: {len(new_index)} entries, {len(new_keywords)} keywords")
    return len(new_index)


# ── Excel parser (primary) ─────────────────────────────────────────────────────

def parse_ci_xlsx(path: Path) -> list[dict]:
    """
    Parse CI_Status_report.xlsx.
    The file has a preamble (general info) then a data table starting at a row
    where column 0 is 'ID' and column 1 is 'Configuration item (CI)'.
    Columns: ID | CI name | Responsibles | Baselines | Storage locations | Artefact name | Document Control | Remarks
    """
    try:
        import pandas as pd
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

        xl = pd.ExcelFile(str(path), engine="openpyxl")
        entries: list[dict] = []

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, header=None, dtype=str)

            # Find header row: col[0]=="ID" and col[1] contains "configuration item" or "CI"
            header_row = None
            for i, row in df.iterrows():
                c0 = str(row.iloc[0]).strip().lower() if pd.notna(row.iloc[0]) else ""
                c1 = str(row.iloc[1]).strip().lower() if len(row) > 1 and pd.notna(row.iloc[1]) else ""
                if c0 == "id" and ("configuration" in c1 or "ci" in c1 or "item" in c1):
                    header_row = i
                    break

            if header_row is None:
                logger.debug(f"Sheet '{sheet_name}': header row not found, skipping")
                continue

            # Use positional columns (more reliable than name matching for this file)
            data = df.iloc[header_row + 1:].reset_index(drop=True)

            # col positions: 0=ID, 1=CI name, 2=Responsible, 3=Baselines,
            #                4=Storage location, 5=Artefact name, 6=Doc Control, 7=Remarks
            for _, row in data.iterrows():
                ci_id = _clean(row.iloc[0]) if len(row) > 0 else ""
                if not ci_id or not re.search(r"CI.?\d+", ci_id, re.IGNORECASE):
                    continue

                name        = _clean(row.iloc[1]) if len(row) > 1 else ""
                responsible = _clean(row.iloc[2]) if len(row) > 2 else ""
                filename    = _clean(row.iloc[5]) if len(row) > 5 else ""
                folder      = _clean(row.iloc[4]) if len(row) > 4 else ""  # Storage location
                status      = _clean(row.iloc[6]) if len(row) > 6 else ""  # Document Control

                # Normalise CI-XXXX format
                ci_id = re.sub(r"^CI\.?-?\s*(\d+)$", r"CI-\1", ci_id, flags=re.IGNORECASE)

                # Extract folder prefix from filename path (e.g. "10_PM" from storage location)
                if not folder or folder == "Main SharePoint":
                    # Try to infer folder from filename prefix or CI range
                    num = re.search(r"\d+", ci_id)
                    if num:
                        n = int(num.group())
                        if n < 100:
                            folder = "10_PM"
                        elif n < 200:
                            folder = "20_HW"
                        elif n < 300:
                            folder = "30_SW"
                        elif n < 400:
                            folder = "40_CAL"

                entries.append({
                    "ci_id": ci_id,
                    "name": name,
                    "filename": filename,
                    "folder": folder,
                    "responsible": responsible,
                    "status": status,
                    "keywords": _derive_keywords(ci_id, name),
                    "source": "xlsx",
                })

        logger.info(f"parse_ci_xlsx: parsed {len(entries)} entries from {path.name}")
        return entries

    except FileNotFoundError:
        logger.warning(f"CI Status xlsx not found: {path}")
        return []
    except Exception as e:
        logger.error(f"parse_ci_xlsx failed: {e}", exc_info=True)
        return []


# ── HTML parser via WebDAV (fallback) ─────────────────────────────────────────

def parse_ci_html_webdav(webdav_path: str) -> list[dict]:
    """
    Parse CI Status Report HTML via WebDAV UNC path.
    Returns empty list if unreachable (VPN required).
    """
    try:
        p = Path(webdav_path)
        if not p.exists():
            logger.warning(f"CI HTML WebDAV path not reachable: {webdav_path}")
            return []

        html = p.read_text(encoding="utf-8", errors="replace")
        return _parse_ci_html_content(html, source="webdav")

    except Exception as e:
        logger.warning(f"parse_ci_html_webdav failed: {e}")
        return []


def _parse_ci_html_content(html: str, source: str = "html") -> list[dict]:
    """Extract CI entries from HTML table content."""
    try:
        # Simple regex-based HTML table row extraction (no BeautifulSoup dependency)
        # Find <tr>...</tr> blocks
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
        entries: list[dict] = []
        header_cols: list[str] = []

        for row_html in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.DOTALL | re.IGNORECASE)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]  # strip inner tags

            if not cells:
                continue

            # Detect header row
            if not header_cols and any(re.search(r"ci.?id|ci.?no|document.?id", c, re.IGNORECASE) for c in cells):
                header_cols = [c.lower() for c in cells]
                continue

            if header_cols and len(cells) >= 2:
                row_dict = dict(zip(header_cols, cells))
                ci_id = row_dict.get(next((k for k in header_cols if "id" in k or "ci" in k), ""), "")
                name = row_dict.get(next((k for k in header_cols if "name" in k or "document" in k), ""), "")
                if ci_id and re.search(r"ci.?\d+", ci_id, re.IGNORECASE):
                    filename = row_dict.get(next((k for k in header_cols if "file" in k or "artifact" in k), ""), "")
                    folder = row_dict.get(next((k for k in header_cols if "folder" in k or "path" in k), ""), "")
                    responsible = row_dict.get(next((k for k in header_cols if "responsible" in k or "role" in k or "owner" in k), ""), "")
                    status = row_dict.get(next((k for k in header_cols if "status" in k or "state" in k), ""), "")
                    entries.append({
                        "ci_id": ci_id,
                        "name": name,
                        "filename": filename,
                        "folder": folder,
                        "responsible": responsible,
                        "status": status,
                        "keywords": _derive_keywords(ci_id, name),
                        "source": source,
                    })

        logger.info(f"_parse_ci_html_content: found {len(entries)} entries")
        return entries

    except Exception as e:
        logger.error(f"HTML CI parse failed: {e}")
        return []


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_col(columns, candidates: list[str]) -> Optional[str]:
    """Return the first column name that matches any candidate (case-insensitive)."""
    cols_lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    return None


def _clean(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in {"nan", "none", "nat", "-", "n/a"} else s


def _derive_keywords(ci_id: str, name: str) -> list[str]:
    """Generate search keywords from CI ID and name."""
    kws = []
    if name:
        kws.append(name.lower())
        # Abbreviation: first letters of significant words
        words = name.lower().split()
        abbr = "".join(w[0] for w in words if w not in {"the", "a", "an", "and", "of", "for"})
        if len(abbr) >= 2:
            kws.append(abbr)
        # Remove trailing common words and add shorter variant
        clean_words = [w for w in words if w not in {"plan", "report", "document", "strategy", "specification"}]
        if len(clean_words) >= 2:
            kws.append(" ".join(clean_words))
    return kws
