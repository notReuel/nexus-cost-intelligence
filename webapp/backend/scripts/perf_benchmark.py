"""
Focused single-user performance benchmarking (Enterprise Validation sprint,
item 6) — clean baseline latencies, not under concurrent load (that's
covered separately by the multi-user simulation).
"""
import sys, os, time, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/perf_test.db")
os.environ.setdefault("JWT_SECRET", "perf-secret")

db_path = os.environ["DATABASE_URL"].replace("sqlite:///", "")
for suffix in ("", "-wal", "-shm"):
    try: os.unlink(db_path + suffix)
    except OSError: pass

from app.core.migrate import run_migration
run_migration(reset=True)

from fastapi import FastAPI
from app.core.routes_v2 import register_v2
from fastapi.testclient import TestClient

app = FastAPI()
register_v2(app)
client = TestClient(app)


def bench(label, fn, n=20):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p50 = times[len(times)//2]
    p95 = times[int(len(times)*0.95)] if len(times) > 1 else times[0]
    print(f"  {label:45s} n={n:3d}  p50={p50:7.2f}ms  p95={p95:7.2f}ms  min={min(times):7.2f}ms  max={max(times):7.2f}ms")
    return times


print("=== Login latency (scrypt hashing is the dominant cost by design) ===")
bench("POST /api/v2/auth/login", lambda: client.post(
    "/api/v2/auth/login", json={"email": "estimator@demo.io", "password": "changeme-estimator"}), n=10)

login = client.post("/api/v2/auth/login", json={"email": "estimator@demo.io", "password": "changeme-estimator"}).json()
token = login["access_token"]
headers = {"Authorization": f"Bearer {token}"}

apr_login = client.post("/api/v2/auth/login", json={"email": "approver@demo.io", "password": "changeme-approver"}).json()
apr_headers = {"Authorization": f"Bearer {apr_login['access_token']}"}

print("\n=== Benchmark query latency (against the 440-observation reference dataset) ===")
bench("GET /api/v2/benchmarks (unfiltered, limit=50)",
     lambda: client.get("/api/v2/benchmarks", headers=headers, params={"limit": 50}))
bench("GET /api/v2/benchmarks?q=Lay & Weld",
     lambda: client.get("/api/v2/benchmarks", headers=headers, params={"q": "Lay & Weld"}))

print("\n=== Observation submission latency ===")
counter = [0]
def submit():
    counter[0] += 1
    return client.post("/api/v2/observations", headers=headers, json={
        "category_path": "PerfTest > Bench > Item",
        "canonical_name": f"Perf Item {counter[0]}",  # unique each time -> new item path
        "unit": "each", "currency": "USD", "orig_rate": 10.0, "orig_year": 2024,
    })
submit_times = bench("POST /api/v2/observations (new item each time)", submit)

# Also measure submission to an ALREADY-EXISTING item (the common case in practice)
client.post("/api/v2/observations", headers=headers, json={
    "category_path": "PerfTest > Existing > Item", "canonical_name": "Existing Perf Item",
    "unit": "each", "currency": "USD", "orig_rate": 10.0, "orig_year": 2024})
bench("POST /api/v2/observations (existing item, common case)",
     lambda: client.post("/api/v2/observations", headers=headers, json={
        "category_path": "PerfTest > Existing > Item", "canonical_name": "Existing Perf Item",
        "unit": "each", "currency": "USD", "orig_rate": 10.0, "orig_year": 2024}))

print("\n=== Approval + benchmark rebuild latency ===")
# submit N observations to one item, then approve them one at a time, timing each approve+rebuild
obs_ids = []
for i in range(20):
    r = client.post("/api/v2/observations", headers=headers, json={
        "category_path": "PerfTest > RebuildBench > Item", "canonical_name": "Rebuild Bench Item",
        "unit": "each", "currency": "USD", "orig_rate": 10.0 + i, "orig_year": 2024})
    obs_ids.append(r.json()["observation_id"])

approve_times = []
for oid in obs_ids:
    t0 = time.perf_counter()
    client.post(f"/api/v2/observations/{oid}/review", headers=apr_headers, json={"approve": True})
    approve_times.append((time.perf_counter() - t0) * 1000)
approve_times.sort()
print(f"  POST .../review (approve+rebuild, item grows 1->20 obs)  "
     f"n={len(approve_times)}  p50={approve_times[len(approve_times)//2]:.2f}ms  "
     f"first={approve_times[0]:.2f}ms  last(n=20)={approve_times[-1]:.2f}ms")

print("\n=== Database query performance (raw, against the reference dataset) ===")
import sqlite3
raw = sqlite3.connect(db_path)
t0 = time.perf_counter()
raw.execute("SELECT COUNT(*) FROM observation").fetchone()
print(f"  COUNT(*) on observation table: {(time.perf_counter()-t0)*1000:.3f}ms")
t0 = time.perf_counter()
raw.execute("SELECT * FROM benchmark ORDER BY median DESC LIMIT 10").fetchall()
print(f"  ORDER BY + LIMIT on benchmark: {(time.perf_counter()-t0)*1000:.3f}ms")

import resource
print(f"\nPeak RSS memory for this run: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.1f} MB")
