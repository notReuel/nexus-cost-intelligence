# NNPC Cost Intelligence Platform — Web App v2.0

Production-ready full-stack web application. Mirrors the Excel engine v2.0
exactly. Outputs aggregated cost bands only — the underlying database stays
server-side.

## Architecture

```
+---------------------------+     +---------------------------+
|  React + Vite Frontend    |     |  FastAPI Backend          |
|  (port 5173 dev / 4173)   | --> |  (port 8765)              |
|                           |     |                           |
|  - Home / Overview        |     |  /api/health              |
|  - Pipeline / Well / CT   |     |  /api/metadata            |
|  - Quote Checker          |     |  /api/options             |
|  - Export (print-to-PDF)  |     |  /api/estimate/{module}   |
|                           |     |  /api/qc/check            |
+---------------------------+     +---------------------------+
                                              |
                                              v
                                  +---------------------------+
                                  |  engine/__init__.py       |
                                  |  - Proprietary rate tables|
                                  |  - Calculation logic      |
                                  |  - NEVER exposed via API  |
                                  +---------------------------+
```

Three deploy modes:

1. **Dev mode** (separate ports, hot-reload): backend on 8765, frontend on 5173 with Vite proxy
2. **Preview mode** (separate processes, built): backend on 8765, frontend `npm run preview` on 4173
3. **Combined mode** (single process): backend serves API + built frontend on 8765 — use `backend/serve.py`

## Quick start (dev)

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

## Quick start (combined production)

```bash
# Build frontend
cd frontend
npm install
npm run build

# Run combined server (serves API + static dist)
cd ../backend
pip install -r requirements.txt
uvicorn serve:app --host 0.0.0.0 --port 8765
# Open http://localhost:8765
```

## Docker deploy

```bash
cd backend
docker build -t ndcip-backend .
docker run -p 8765:8000 ndcip-backend
```

For combined deploy with frontend baked in, see `deploy/Dockerfile.combined`.

## Data exposure policy

This platform follows the **Wood Mackenzie Lens model** for data protection:

| Surface           | Visible to users     |
|-------------------|----------------------|
| Cost bands (L/M/H)| ✅ Yes                |
| Confidence ratings | ✅ Yes                |
| Aggregate stats   | ✅ Yes (5 ops, n=4)   |
| Vendor identities | ❌ Never              |
| Operator names    | ❌ Anonymised         |
| Source documents  | ❌ Never              |
| Raw line items    | ❌ Never              |

The proprietary rate tables live in `backend/app/engine/__init__.py` and
`backend/app/engine/lay_weld_data.json`. These files should NOT be committed
to a public repo. Treat them like a credentials file.

## Module status

| Module    | Version | Confidence | Field-tested |
|-----------|---------|------------|--------------|
| Pipeline  | v1.1.1  | HIGH       | EGWA-2 BEME (GREEN) |
| Well      | v1.0    | LOW        | Not yet      |
| CT        | v2.0    | MEDIUM     | Sanity-only  |

## Tested

```bash
cd /home/claude/webapp
./smoke_test.sh
```

All 6 API endpoints + frontend SPA route return expected values.
Engine output matches Excel v2.0 within 1% on Pipeline, exact on Well and CT.

## Files

```
webapp/
├── backend/
│   ├── app/
│   │   ├── engine/
│   │   │   ├── __init__.py        (PROPRIETARY — calculation engine)
│   │   │   └── lay_weld_data.json (PROPRIETARY — rate tables)
│   │   └── main.py                (FastAPI routes — API-only)
│   ├── serve.py                   (FastAPI — API + static frontend)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx                (Router shell + nav)
│   │   ├── main.jsx
│   │   ├── index.css              (Tailwind base)
│   │   ├── components/
│   │   │   └── UI.jsx             (Shared UI primitives)
│   │   ├── lib/
│   │   │   └── api.js             (Backend client + formatters)
│   │   └── pages/
│   │       ├── Home.jsx           (Landing / overview)
│   │       ├── Pipeline.jsx
│   │       ├── Well.jsx
│   │       ├── CT.jsx
│   │       ├── QC.jsx             (Unified Quote Checker)
│   │       └── Export.jsx         (1-page printable summary)
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── index.html
├── deploy/                        (placeholder for production configs)
└── smoke_test.sh                  (E2E test script)
```

## Visual design

Dark navy (`#0E1820`) base + amber (`#E5A445`) accent. Matches the Tigerton
pitch deck for buying-journey coherence. All interactive elements use the
same palette. Inter typeface throughout.

## License & confidentiality

This codebase is internal use only. The proprietary rate tables in
`backend/app/engine/` are derived from operator-confidential tender data
and are not licensed for redistribution.
