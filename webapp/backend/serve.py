"""
Combined backend + frontend server.
For dev/preview: FastAPI serves API + static frontend dist.
For prod: use this with nginx in front, or split deploy backend/frontend.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime
from pathlib import Path
import os
import sys

# Ensure app/ is on path
sys.path.insert(0, str(Path(__file__).parent))

from app.engine import (
    PipelineInput, WellInput, CTInput, QCInput,
    EstimateResult, QCResult,
    estimate_pipeline, estimate_well, estimate_ct, check_quote,
    LAY_WELD, CT_BENCHMARKS,
    get_findings, get_ct_cross_tender, get_coverage_matrix,
    get_catalogue_summary, query_catalogue, get_catalogue_item,
)
from app.engine.boq_parser import parse_xlsx, parse_csv
from app.engine.variance_reporter import analyze_tender
import json as _json
import tempfile, os

app = FastAPI(title="NNPC Cost Modelling Platform", version="5.0.0")

import logging
_log = logging.getLogger("nexus.cors")
_ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "").strip()
if _ALLOWED_ORIGINS_ENV:
    ALLOWED_ORIGINS = [o.strip() for o in _ALLOWED_ORIGINS_ENV.split(",") if o.strip()]
else:
    # Safe default for local dev/preview only — NOT "*". Loudly warn so a
    # deploy that forgets to set ALLOWED_ORIGINS doesn't silently ship with
    # an over-broad default.
    ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:4173", "http://localhost:8765"]
    _log.warning(
        "ALLOWED_ORIGINS not set — defaulting to localhost dev origins only "
        f"({ALLOWED_ORIGINS}). Set ALLOWED_ORIGINS (comma-separated) to the real "
        "frontend origin(s) before deploying anywhere reachable by real users."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS, allow_credentials=False,
    allow_methods=["GET","POST"], allow_headers=["*"],
)

@app.middleware("http")
async def add_watermark_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Platform"] = "NNPC Cost Modelling v5.0"
    response.headers["X-Confidential"] = "Internal use only"
    return response

# ─── API endpoints (same as main.py) ─────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat(), "version": "5.0.0"}

@app.get("/api/metadata")
def metadata():
    return {
        "platform": "NNPC Cost Modelling Platform", "version": "5.0.0",
        "modules": ["Pipeline", "Well", "CT"],
        "coverage": {
            "operators_count": 6,
            "operator_names": "SPDC · Seplat · NPDC/ARAHAS · NAOC/Oando · HEOSL · Sahara Energy",
            "date_range": "2017–2025", "currency_basis": "USD 2024 real terms",
            "line_items_normalised": 662, "ct_tenders": 2, "ct_unique_vendors": 17,
        },
        "field_test": {
            "benchmark": "SPDC EGWA-2 swamp bypass BEME",
            "actual_usd": 202922, "engine_mid_usd": 178728, "delta_pct": -0.119,
            "verdict": "GREEN — within ±15% of Mid",
        },
        "module_status": {
            "Pipeline": {"version": "1.1.1", "confidence": "HIGH",   "notes": "Field-tested (EGWA-2 GREEN)"},
            "Well":     {"version": "1.0",   "confidence": "LOW",    "notes": "Single source (Sahara). No field test."},
            "CT":       {"version": "2.0",   "confidence": "MEDIUM", "notes": "11+6 vendors, cross-tender validated"},
        },
    }

@app.get("/api/options")
def options():
    return {
        "diameter_inches": [2, 3, 4, 6, 8, 10, 12, 16],
        "schedule": ["Sch 40", "Sch 80", "Sch 120", "Sch 160"],
        "terrain": ["Land", "Swamp"],
        "scope_class": ["LINEAR LAY", "ON-SUPPORT FAB", "BURIED"],
        "well_type": ["Onshore vertical", "Onshore deviated", "Swamp vertical", "Swamp deviated"],
        "ct_size": ['1.25"', '1.5"', '1.75"'],
        "ct_reference": list(CT_BENCHMARKS.keys()),
        "currency": ["USD", "NGN"], "modules": ["Pipeline", "Well", "CT"],
    }

@app.post("/api/estimate/pipeline", response_model=EstimateResult)
def post_estimate_pipeline(inp: PipelineInput):
    try: return estimate_pipeline(inp)
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/api/estimate/well", response_model=EstimateResult)
def post_estimate_well(inp: WellInput):
    try: return estimate_well(inp)
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/api/estimate/ct", response_model=EstimateResult)
def post_estimate_ct(inp: CTInput):
    try: return estimate_ct(inp)
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/api/qc/check", response_model=QCResult)
def post_qc_check(inp: QCInput):
    try: return check_quote(inp)
    except Exception as e: raise HTTPException(500, str(e))

# ─── Intelligence endpoints ──────────────────────────────────────────────
@app.get("/api/intelligence/findings")
def intelligence_findings():
    return get_findings()

@app.get("/api/intelligence/ct-cross-tender")
def intelligence_ct():
    return get_ct_cross_tender()

@app.get("/api/intelligence/coverage")
def intelligence_coverage():
    return get_coverage_matrix()

# ─── Line Item Catalogue endpoints (Phase 1A) ────────────────────────────
@app.get("/api/catalogue/summary")
def catalogue_summary():
    return get_catalogue_summary()

@app.get("/api/catalogue/items")
def catalogue_items(
    category: str = None, sub_category: str = None, search: str = None,
    confidence: str = None, unit: str = None,
    limit: int = 100, offset: int = 0,
):
    return query_catalogue(
        category=category, sub_category=sub_category, search=search,
        confidence=confidence, unit=unit, limit=limit, offset=offset,
    )

@app.get("/api/catalogue/items/{item_id}")
def catalogue_item(item_id: str):
    item = get_catalogue_item(item_id)
    if not item:
        raise HTTPException(404, f"Item {item_id} not found")
    return item

# ─── Tender Upload + Benchmarking endpoints (Phase 1B) ────────────────────
from fastapi import File, UploadFile, Form

# Load catalogue once for benchmarking
_CATALOGUE_PATH = Path(__file__).parent / "app" / "engine" / "line_items_catalogue.json"
_CATALOGUE_DATA = None
def _load_catalogue():
    global _CATALOGUE_DATA
    if _CATALOGUE_DATA is None:
        with open(_CATALOGUE_PATH) as f:
            _CATALOGUE_DATA = _json.load(f)
    return _CATALOGUE_DATA['items']

@app.post("/api/tender/upload")
async def tender_upload(
    file: UploadFile = File(...),
    project_name: str = Form(''),
    vendor_name: str  = Form(''),
):
    """Upload a BOQ (XLSX/CSV) and run the full benchmark workflow."""
    filename = file.filename or 'upload'
    suffix = ''
    if filename.lower().endswith('.csv'):  suffix = '.csv'
    elif filename.lower().endswith('.xlsx'): suffix = '.xlsx'
    elif filename.lower().endswith('.xls'):  suffix = '.xls'
    else:
        raise HTTPException(400, "File must be .xlsx or .csv")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 20 MB)")

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(contents)
        tmp.close()
        if suffix == '.csv':
            parsed = parse_csv(tmp.name)
        else:
            parsed = parse_xlsx(tmp.name)
        if not parsed:
            raise HTTPException(422, "Could not detect a BOQ table in the uploaded file.")
        catalogue = _load_catalogue()
        report = analyze_tender(parsed, catalogue, project_name=project_name, vendor_name=vendor_name)
        if not report:
            raise HTTPException(422, "Could not analyze the parsed BOQ.")
        return report
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Parse error: {type(e).__name__}: {e}")
    finally:
        try: os.unlink(tmp.name)
        except: pass

# ─── Multi-vendor bid comparison (Phase 1B+) ─────────────────────────────
from typing import List
@app.post("/api/bid-comparison")
async def bid_comparison(
    files: List[UploadFile] = File(...),
    project_name: str = Form(''),
):
    """Upload 2+ vendor BOQs for the same scope. Returns side-by-side comparison
    plus a recommended bid based on deviation analysis."""
    if len(files) < 2:
        raise HTTPException(400, "Upload at least 2 vendor BOQs for comparison")
    if len(files) > 10:
        raise HTTPException(400, "Maximum 10 vendors per comparison")

    catalogue = _load_catalogue()
    vendor_reports = []
    for f in files:
        filename = f.filename or 'upload'
        suffix = ''
        if filename.lower().endswith('.csv'):  suffix = '.csv'
        elif filename.lower().endswith('.xlsx'): suffix = '.xlsx'
        elif filename.lower().endswith('.xls'):  suffix = '.xls'
        else: continue
        contents = await f.read()
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            tmp.write(contents); tmp.close()
            parsed = parse_csv(tmp.name) if suffix == '.csv' else parse_xlsx(tmp.name)
            if not parsed: continue
            # Use filename (without extension) as default vendor name
            vendor_label = filename.rsplit('.', 1)[0]
            report = analyze_tender(parsed, catalogue, project_name=project_name, vendor_name=vendor_label)
            if report:
                vendor_reports.append({'filename': filename, 'vendor_label': vendor_label, 'report': report})
        except Exception as e:
            vendor_reports.append({'filename': filename, 'error': str(e)})
        finally:
            try: os.unlink(tmp.name)
            except: pass

    valid_reports = [v for v in vendor_reports if 'error' not in v]
    if len(valid_reports) < 2:
        raise HTTPException(422, "Could not parse at least 2 valid BOQs")

    # Build the comparison + recommendation
    from app.engine.bid_comparator import build_bid_comparison
    comparison = build_bid_comparison(valid_reports)
    return {
        'project_name': project_name or 'Untitled Bid Comparison',
        'vendor_count': len(valid_reports),
        'errors': [v for v in vendor_reports if 'error' in v],
        **comparison,
    }
# ─── v5 routes: Project Modeller, Budget, Data Entry ─────────────────
from app.model_routes import register_model_routes
register_model_routes(app)

# ─── Secured v2 platform (auth + tenancy + review queue) ───────────
from app.core.routes_v2 import register_v2
from app.core.migrate import run_migration
try:
    run_migration(reset=False)  # creates tables + seeds 440 obs if DB empty (idempotent)
except Exception as _e:
    import logging; logging.getLogger('nexus').warning(f'DB bootstrap: {_e}')
register_v2(app)

# ─── Serve frontend dist ────────────────────────────────────────────
DIST = Path(__file__).parent.parent / 'frontend' / 'dist'
if DIST.exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

    @app.get('/{full_path:path}')
    def spa(full_path: str):
        # SPA: any non-/api path returns index.html (React Router handles route)
        index = DIST / 'index.html'
        if not index.exists():
            raise HTTPException(404, 'index.html not found')
        return FileResponse(index)
