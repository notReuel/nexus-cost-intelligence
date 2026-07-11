"""
NNPC Cost Intelligence Platform — FastAPI Backend
Mirrors the Excel engine v2.0. Exposes ONLY aggregated outputs.
The underlying database is never exposed via API.
"""
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
import os

from app.engine import (
    PipelineInput, WellInput, CTInput, QCInput,
    EstimateResult, QCResult,
    estimate_pipeline, estimate_well, estimate_ct, check_quote,
    LAY_WELD, CT_BENCHMARKS,
    get_findings, get_ct_cross_tender, get_coverage_matrix,
    get_catalogue_summary, query_catalogue, get_catalogue_item,
)

app = FastAPI(
    title="NNPC Cost Modelling Platform",
    description="Operator-grade benchmarking on NNPC tender data. Internal/customer-only.",
    version="5.0.0",
)

# CORS — locked down by default (was previously "*" combined with
# allow_credentials=True below, which Starlette resolves by reflecting back
# whatever Origin header the request sent — effectively any origin, WITH
# credentials attached. That combination is worse than a plain wildcard.
import logging
_log = logging.getLogger("nexus.cors")
_ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "").strip()
if _ALLOWED_ORIGINS_ENV:
    ALLOWED_ORIGINS = [o.strip() for o in _ALLOWED_ORIGINS_ENV.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:4173"]
    _log.warning(
        "ALLOWED_ORIGINS not set — defaulting to localhost dev origins only "
        f"({ALLOWED_ORIGINS}). Set ALLOWED_ORIGINS (comma-separated) to the real "
        "frontend origin(s) before deploying anywhere reachable by real users."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # Bearer tokens go in the Authorization header,
                              # not cookies — credentials mode is unnecessary
                              # here and only adds risk when combined with
                              # multiple allowed origins.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Lightweight watermarking — adds user-session header to every response ──
@app.middleware("http")
async def add_watermark_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Platform"] = "NNPC Cost Modelling v5.0"
    response.headers["X-Confidential"] = "Internal use only"
    return response

# ════════════════════════════════════════════════════════════════════════
# Public endpoints
# ════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat(), "version": "5.0.0"}

@app.get("/api/metadata")
def metadata():
    """Surface coverage info to the frontend without exposing the underlying database."""
    # Count unique operators/scopes from lay-weld, anonymise
    operators_count = 5   # SPDC, Seplat, NPDC/ARAHAS, NAOC, HEOSL, Sahara (Well only)
    return {
        "platform": "NNPC Cost Modelling Platform",
        "version": "5.0.0",
        "modules": ["Pipeline", "Well", "CT"],
        "coverage": {
            "operators_count": 6,    # incl. Sahara on Well
            "operator_names": "SPDC · Seplat · NPDC/ARAHAS · NAOC/Oando · HEOSL · Sahara Energy",
            "date_range": "2017–2025",
            "currency_basis": "USD 2024 real terms",
            "line_items_normalised": 662,
            "ct_tenders": 2,
            "ct_unique_vendors": 17,
        },
        "field_test": {
            "benchmark": "SPDC EGWA-2 swamp bypass BEME",
            "actual_usd": 202922,
            "engine_mid_usd": 178728,
            "delta_pct": -0.119,
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
    """Return valid input options for dropdowns. No rates exposed."""
    return {
        "diameter_inches": [2, 3, 4, 6, 8, 10, 12, 16],
        "schedule":        ["Sch 40", "Sch 80", "Sch 120", "Sch 160"],
        "terrain":         ["Land", "Swamp"],
        "scope_class":     ["LINEAR LAY", "ON-SUPPORT FAB", "BURIED"],
        "well_type":       ["Onshore vertical", "Onshore deviated", "Swamp vertical", "Swamp deviated"],
        "ct_size":         ['1.25"', '1.5"', '1.75"'],
        "ct_reference":    list(CT_BENCHMARKS.keys()),
        "currency":        ["USD", "NGN"],
        "modules":         ["Pipeline", "Well", "CT"],
    }

@app.post("/api/estimate/pipeline", response_model=EstimateResult)
def post_estimate_pipeline(inp: PipelineInput):
    try:
        return estimate_pipeline(inp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline estimate failed: {e}")

@app.post("/api/estimate/well", response_model=EstimateResult)
def post_estimate_well(inp: WellInput):
    try:
        return estimate_well(inp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Well estimate failed: {e}")

@app.post("/api/estimate/ct", response_model=EstimateResult)
def post_estimate_ct(inp: CTInput):
    try:
        return estimate_ct(inp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CT estimate failed: {e}")

@app.post("/api/qc/check", response_model=QCResult)
def post_qc_check(inp: QCInput):
    try:
        return check_quote(inp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QC check failed: {e}")

# ─── Root info ─────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "platform": "NNPC Cost Modelling Platform",
        "version": "5.0.0",
        "frontend": "See /app/ for the React frontend (when deployed together)",
        "docs": "/docs",
    }


# ─── Intelligence endpoints ──────────────────────────────────────────────
@app.get("/api/intelligence/findings")
def intelligence_findings():
    """All 7 market intelligence findings with evidence and 'so what' guidance."""
    return get_findings()

@app.get("/api/intelligence/ct-cross-tender")
def intelligence_ct():
    """CT cross-tender analysis: 11-vendor spread, 4-vendor deflation pattern."""
    return get_ct_cross_tender()

@app.get("/api/intelligence/coverage")
def intelligence_coverage():
    """Dataset coverage matrix — where the data is dense vs thin."""
    return get_coverage_matrix()


# ─── Line Item Catalogue endpoints (Phase 1A) ────────────────────────────
@app.get("/api/catalogue/summary")
def catalogue_summary():
    """Catalogue meta + category/sub-category/unit lookups for filter dropdowns."""
    return get_catalogue_summary()

@app.get("/api/catalogue/items")
def catalogue_items(
    category: str = None,
    sub_category: str = None,
    search: str = None,
    confidence: str = None,
    unit: str = None,
    limit: int = 100,
    offset: int = 0,
):
    """Paginated, filtered catalogue items."""
    return query_catalogue(
        category=category, sub_category=sub_category, search=search,
        confidence=confidence, unit=unit, limit=limit, offset=offset,
    )

@app.get("/api/catalogue/items/{item_id}")
def catalogue_item(item_id: str):
    item = get_catalogue_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item


# ─── v5 routes: Project Modeller, Budget, Data Entry ─────────────────
from app.model_routes import register_model_routes
register_model_routes(app)

from app.core.routes_v2 import register_v2
from app.core.migrate import run_migration
try:
    run_migration(reset=False)  # creates tables + seeds 440 obs if DB empty (idempotent)
except Exception as _e:
    import logging; logging.getLogger('nexus').warning(f'DB bootstrap: {_e}')
register_v2(app)


# ─── Tender Upload + Benchmarking endpoints (Phase 1B) ────────────────────
from fastapi import File, UploadFile, Form
from app.engine.boq_parser import parse_xlsx, parse_csv
from app.engine.variance_reporter import analyze_tender
import json as _json
import tempfile, os
from pathlib import Path

_CATALOGUE_PATH_M = Path(__file__).parent / "engine" / "line_items_catalogue.json"
_CATALOGUE_DATA_M = None
def _load_catalogue_m():
    global _CATALOGUE_DATA_M
    if _CATALOGUE_DATA_M is None:
        with open(_CATALOGUE_PATH_M) as f:
            _CATALOGUE_DATA_M = _json.load(f)
    return _CATALOGUE_DATA_M['items']

@app.post("/api/tender/upload")
async def tender_upload(
    file: UploadFile = File(...),
    project_name: str = Form(''),
    vendor_name: str  = Form(''),
):
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
        tmp.write(contents); tmp.close()
        parsed = parse_csv(tmp.name) if suffix == '.csv' else parse_xlsx(tmp.name)
        if not parsed:
            raise HTTPException(422, "Could not detect a BOQ table in the uploaded file.")
        report = analyze_tender(parsed, _load_catalogue_m(), project_name=project_name, vendor_name=vendor_name)
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
async def bid_comparison_m(
    files: List[UploadFile] = File(...),
    project_name: str = Form(''),
):
    if len(files) < 2:
        raise HTTPException(400, "Upload at least 2 vendor BOQs for comparison")
    if len(files) > 10:
        raise HTTPException(400, "Maximum 10 vendors per comparison")
    catalogue = _load_catalogue_m()
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
            vendor_label = filename.rsplit('.', 1)[0]
            report = analyze_tender(parsed, catalogue, project_name=project_name, vendor_name=vendor_label)
            if report:
                vendor_reports.append({'filename': filename, 'vendor_label': vendor_label, 'report': report})
        except Exception as e:
            vendor_reports.append({'filename': filename, 'error': str(e)})
        finally:
            try: os.unlink(tmp.name)
            except: pass
    valid = [v for v in vendor_reports if 'error' not in v]
    if len(valid) < 2:
        raise HTTPException(422, "Could not parse at least 2 valid BOQs")
    from app.engine.bid_comparator import build_bid_comparison
    return {
        'project_name': project_name or 'Untitled Bid Comparison',
        'vendor_count': len(valid),
        'errors': [v for v in vendor_reports if 'error' in v],
        **build_bid_comparison(valid),
    }
