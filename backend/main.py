"""
AI PM Plan Task — FastAPI Backend (Standalone)
Serves only Super OPL + Bosch OPL + Planning endpoints.
No tracker, RAG, SharePoint, or LLM dependencies.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("opl_standalone")

# ── Path Setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(_ROOT / "outputs")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://localhost:8080")
_CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", f"{CORS_ORIGIN},http://127.0.0.1:8080,null")
_cors_origins = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()]

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI PM Plan Task — OPL Standalone",
    version="1.0.0",
    docs_url="/docs",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# ── Mount routers ─────────────────────────────────────────────────────────────
from backend.super_opl_api import router as _opl_router
app.include_router(_opl_router)

from backend.bosch_opl_api import router as _bosch_router
app.include_router(_bosch_router)

from backend.planning_api import router as _planning_router
app.include_router(_planning_router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    opl_file  = OUTPUT_DIR / "super_opl.json"
    risk_file = OUTPUT_DIR / "bosch_risks.json"
    ll_file   = OUTPUT_DIR / "bosch_lessons.json"
    return {
        "status": "ok",
        "output_dir": str(OUTPUT_DIR),
        "files": {
            "super_opl.json":    opl_file.exists(),
            "bosch_risks.json":  risk_file.exists(),
            "bosch_lessons.json": ll_file.exists(),
        },
    }
