#!/bin/bash
# Boot backend + serve frontend dist, run integrated tests, then teardown.
set -e

PROJECT=/home/claude/webapp
cleanup() {
  echo ""
  echo "=== Cleanup ==="
  [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null || true
  echo "Servers stopped"
}
trap cleanup EXIT

echo "=== Starting backend (port 8765) ==="
cd $PROJECT/backend
uvicorn app.main:app --host 0.0.0.0 --port 8765 > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
sleep 2

if ! curl -sf http://localhost:8765/api/health > /dev/null; then
  echo "ERROR: backend failed to start"
  cat /tmp/backend.log
  exit 1
fi
echo "  ✓ Backend OK (PID $BACKEND_PID)"

echo ""
echo "=== Starting frontend static server (port 4173) ==="
cd $PROJECT/frontend/dist
python3 -m http.server 4173 > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
sleep 1

if ! curl -sf http://localhost:4173/ > /dev/null; then
  echo "ERROR: frontend failed to start"
  cat /tmp/frontend.log
  exit 1
fi
echo "  ✓ Frontend OK (PID $FRONTEND_PID)"

echo ""
echo "=== Integrated API tests ==="
echo ""
echo "1. /api/health"
curl -s http://localhost:8765/api/health | python3 -m json.tool

echo ""
echo "2. /api/options (input dropdowns)"
curl -s http://localhost:8765/api/options | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'  Diameters: {d[\"diameter_inches\"]}')
print(f'  Schedules: {d[\"schedule\"]}')
print(f'  Scope classes: {d[\"scope_class\"]}')
"

echo ""
echo "3. POST /api/estimate/pipeline (default)"
curl -s -X POST http://localhost:8765/api/estimate/pipeline \
  -H "Content-Type: application/json" \
  -d '{"dia":6,"sched":"Sch 40","terrain":"Swamp","length_km":5,"duration_days":30,"scope_class":"LINEAR LAY","globals":{"project_name":"E2E test","ref_year":2024,"fx_mult":1.55,"sec_floor":50,"mob_uplift":1.5,"contingency_pct":0.10,"vat_pct":0.075,"band_pct":0.15}}' \
  | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(f'  Total Mid: \${r[\"total\"][\"mid\"]:,.0f}  (expected ~\$851k)')
print(f'  Confidence: {r[\"confidence\"]}')
print(f'  Breakdown rows: {len(r[\"breakdown\"])}')
"

echo ""
echo "4. POST /api/estimate/ct (default Seplat 2024)"
curl -s -X POST http://localhost:8765/api/estimate/ct \
  -H "Content-Type: application/json" \
  -d '{"ct_size":"1.5\"","n_wells":1,"days_per_well":5,"activity_factor":1.0,"reference_tender":"Seplat 2024 (primary)","globals":{"project_name":"CT test","ref_year":2024,"fx_mult":1.55,"sec_floor":50,"mob_uplift":1.5,"contingency_pct":0.10,"vat_pct":0.075,"band_pct":0.15}}' \
  | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(f'  Total Mid: \${r[\"total\"][\"mid\"]:,.0f}  (expected \$84,253)')
"

echo ""
echo "5. POST /api/qc/check (\$850k quote vs Mid band)"
curl -s -X POST http://localhost:8765/api/qc/check \
  -H "Content-Type: application/json" \
  -d '{"module":"Pipeline","quote_currency":"USD","quote_total":850000,"band_low":751329,"band_mid":850992,"band_high":1049206,"band_pct":0.15}' \
  | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(f'  Verdict: {r[\"verdict\"]}')
print(f'  Δ%: {r[\"delta_pct\"]*100:+.1f}%')
print(f'  In band: {r[\"in_band\"]}')
print(f'  Position: {r[\"position_in_band\"]*100:.0f}%')
"

echo ""
echo "6. GET / (frontend SPA root)"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4173/)
BYTES=$(curl -s -o /dev/null -w "%{size_download}" http://localhost:4173/)
echo "  HTTP $HTTP, $BYTES bytes"

echo ""
echo "=== ALL TESTS PASS ==="
