# NEPL NEXUS — Cost Intelligence Platform (v5.0)

Lean, single-discipline (swamp lay & weld) operator-grade benchmarking platform.
Rebuilt from v4.1 per the Session 1 task order.

## What shipped in v5.0

**Backend (Phase A)**
- `fuzzy_matcher.py` — **hard sub-category gate**. The v4.1 demo-killer (flanges/gaskets
  matching HDD crossings at −97%) is fixed: any candidate whose `sub_category` differs
  from the line's `sub_category_hint` (no exact match, no containment) is dropped outright.
  Verified: flange line now yields 0 HDD false matches; real lay&weld still matches HIGH @1.0.
- `normalizer_fx.py` — FX + US PPI-FG normalisation. Reproduces all 440 existing
  observations exactly (NGN 2023 → /645.16 × PPI = factor 0.001569 = $20.26/m for the
  Seplat anchor; USD 2017 → ×1.28908 = $26.68/m SPDC). No fabrication — sourced from
  `FX_Inflation_Lookup_Table.xlsx`.
- `project_modeller.py` — the 13-input scope → catalogue-backed BOQ. Wraps the untouched,
  field-tested `estimate_pipeline` spine (calibration preserved: default = **$870,175**),
  re-derives lay & weld per selected operator from raw observations (SPDC → its own
  $26.68/m, HIGH, n=9), gates sections via toggles, attaches per-line source transparency
  (operators, obs count, years, confidence), and pulls crossings/tie-ins from real rates.
  Unbacked lines are flagged `MODELLED`, never faked.
- `model_routes.py` — registered on **both** `serve.py` and `main.py`:
  - `POST /api/model/project` — 13-input scope → rolling estimate + BOQ
  - `POST /api/model/generate-budget` — same (Budget page consumer)
  - `GET  /api/observations/summary` — dataset counts
  - `POST /api/observations/add` — **Data Entry front door**: normalise → append →
    rebuild catalogue cell → live pickup (verified OBS00441 end-to-end).

**Frontend (Phases B–F)**
- New **left-rail enterprise shell** (App.jsx): sectioned nav (Estimating / Procurement /
  Data / Roadmap), locked items greyed with lock icons, top context strip.
- `components/Enterprise.jsx` — the evidence system: `ConfidencePill`, `SourcePopover`
  (per-line provenance), `LockedPill`, dense `Panel`, `Segmented`, `CoverageBar`.
- Pages: **Home** (thesis + four-stage flow), **ProjectModeller** (4 panels, debounced
  300ms live estimate, locked roadmap pills, Save/Load), **Budget** (collapsible BOQ,
  per-line source popover + confidence, CSV export), **BidIntake** (≤10 vendors, demo-bid
  generator, ranked cards, sticky line matrix), **DataEntry** (live normalisation preview),
  **ComingSoon** (Well Services / Vendor Verification roadmap stubs).
- Product title purged of "Cost Intelligence" → "NNPC Cost Modelling Platform".

## Calibration guardrail (must not drift)
| Case | Target | v5.0 |
|---|---|---|
| Pipeline default (6″ Sch 40 Swamp, 5km, 30d) | $870,175 | **$870,175** ✓ |
| Well default | $20,276,534 | $20,276,534 ✓ |
| CT default (1w × 5d) | $84,253 | $84,253 ✓ |

The Project Modeller total differs from the pipeline default by design — it layers
catalogue-backed civil/hydrotest/crossings lines the raw engine doesn't include.

## Deploy
- **VITE_API_URL** = `https://cost-modelling.up.railway.app` — NO trailing slash, NO `/api`
  suffix (the api client adds `/api`). This is already correct in `frontend/.env.local`.
- Frontend → Vercel (auto-build). Backend → Railway (Dockerfile: `uvicorn app.main:app`).
- Repo: `NGD-costModelling-main`. Currently deployed live: v2.1.
- Data Entry writes to `raw_observations.json` / `line_items_catalogue.json` on the
  backend container. On Railway the filesystem is ephemeral (fine for pitch demos —
  additions persist until redeploy). For durable ingestion, back these with a volume/DB.

## Not in this build (next session)
- Companion Scaling PDF (one-pager: gap → pipeline → front door → Phase 3 acquisition list).
- Legacy pages (Pipeline/Well/CT/QC/TenderUpload) remain in `src/pages/` unimported —
  safe to delete when convenient.
