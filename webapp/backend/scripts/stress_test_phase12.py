"""
Stress test for Phase 1/2: the DB-backed estimating engine
(model_project() with session + caller_tenant_id, db_bridge.py).

This is NEW code with a NEW performance profile — every estimate now issues
live DB queries per line item instead of reading pre-loaded JSON in memory.
Tests:
  1. Multi-tenant concurrent correctness — the critical one, since this is
     brand-new tenant-blending logic in a path that didn't have tenant
     concepts at all before this session.
  2. Performance at current scale (440 obs) vs a much larger volume.
  3. Query plan verification for the new db_bridge.py query shapes.
  4. Edge cases: zero-data tenant, concurrent submit+approve during an
     in-flight estimate.
"""
import sys, os, time, random, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/phase12_stress.db")
os.environ.setdefault("JWT_SECRET", "phase12-stress-secret")

db_path = os.environ["DATABASE_URL"].replace("sqlite:///", "")
for suffix in ("", "-wal", "-shm"):
    try: os.unlink(db_path + suffix)
    except OSError: pass

from app.core.migrate import run_migration
run_migration(reset=True)

from fastapi import FastAPI
from app.core.routes_v2 import register_v2
from app.model_routes import register_model_routes
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.core.db import engine
from app.core.models import Tenant, User, Role, Item, Category, Observation, ObsStatus, SourceType
from app.core.auth import hash_password
from app.core.escalation import normalise
import concurrent.futures as cf

app = FastAPI()
register_v2(app)
register_model_routes(app)
client = TestClient(app)

print("=" * 70)
print("TEST 1: multi-tenant concurrent estimate correctness")
print("=" * 70)

N_TENANTS = 6
tenant_creds = []
with Session(engine) as s:
    cat = s.exec(select(Category).where(Category.name == "Lay & Weld")).first()
    for i in range(N_TENANTS):
        t = Tenant(name=f"Stress Co {i}", slug=f"stress-co-{i}", base_currency="USD")
        s.add(t); s.flush()
        u = User(tenant_id=t.id, email=f"est{i}@stress.io", full_name=f"Estimator {i}",
                 role=Role.ESTIMATOR, password_hash=hash_password("stress-password-1"))
        s.add(u); s.flush()
        # each tenant gets a DISTINCT, identifiable private lay & weld rate:
        # tenant i's rate = 100 + i*111 (so results are unmistakable if mixed up)
        distinct_rate = 100 + i * 111
        item = Item(tenant_id=t.id, category_id=cat.id,
                    canonical_name=f"Lay & Weld 6\" Swamp (stress-{i})",
                    unit="m", attributes={"dia_in": 6, "terrain": "Swamp"})
        s.add(item); s.flush()
        norm, _ = normalise(s, orig_rate=distinct_rate, currency="USD", year=2024, index_key="US_PPI_FG")
        obs = Observation(tenant_id=t.id, item_id=item.id, source_type=SourceType.PO,
                          operator="SPDC", currency="USD", orig_rate=distinct_rate, orig_year=2024,
                          normalised_base=norm, status=ObsStatus.APPROVED,
                          spec_snapshot={"dia_in": 6, "terrain": "Swamp"})
        s.add(obs)
        tenant_creds.append((f"est{i}@stress.io", "stress-password-1", t.id, round(norm, 2)))
    s.commit()

print(f"Created {N_TENANTS} tenants, each with a distinct private lay&weld rate.")
for email, pw, tid, rate in tenant_creds:
    print(f"  tenant {tid}: expected private-blended presence of rate ${rate}")

# log in all tenants
sessions = []
for email, pw, tid, rate in tenant_creds:
    r = client.post("/api/v2/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    sessions.append({"token": r.json()["access_token"], "tenant_id": tid, "expected_rate": rate})

def get_estimate(sess_or_none):
    headers = {"Authorization": f"Bearer {sess_or_none['token']}"} if sess_or_none else {}
    r = client.post("/api/model/project", headers=headers, json={
        "operator": "SPDC", "dia": 6, "terrain": "Swamp",
    })
    if r.status_code != 200:
        return {"error": r.status_code, "tenant": sess_or_none["tenant_id"] if sess_or_none else None}
    lw = next(l for l in r.json()["lines"] if l["description"].startswith("Lay & weld"))
    return {
        "tenant": sess_or_none["tenant_id"] if sess_or_none else None,
        "n_obs": lw["source"]["n_obs"],
        "rate_mid": lw["rate_mid"],
        "operators": lw["source"]["operator_used"],
    }

# fire many concurrent requests: mix of anonymous + each of the 6 tenants, repeated
calls = ([None] * 10) + (sessions * 10)
random.shuffle(calls)
print(f"\nFiring {len(calls)} concurrent estimate requests (mix of anonymous + {N_TENANTS} tenants)...")
t0 = time.perf_counter()
with cf.ThreadPoolExecutor(max_workers=20) as ex:
    results = list(ex.map(get_estimate, calls))
elapsed = time.perf_counter() - t0
print(f"Completed in {elapsed:.2f}s ({len(calls)/elapsed:.1f} req/s)")

# Verify correctness: every anonymous result should show n_obs=9 (reference only,
# no stress-test tenants mixed in); every tenant result should show n_obs=10
# (9 reference + exactly 1 of THEIR OWN private observations).
errors = [r for r in results if "error" in r]
anon_results = [r for r in results if r["tenant"] is None]
contamination_found = False
for r in results:
    if r.get("tenant") is not None:
        expected_n = 10  # 9 reference + 1 own
        if r["n_obs"] != expected_n:
            contamination_found = True
            print(f"  UNEXPECTED n_obs for tenant {r['tenant']}: {r['n_obs']} (expected {expected_n})")
for r in anon_results:
    if r["n_obs"] != 9:
        contamination_found = True
        print(f"  UNEXPECTED anonymous n_obs: {r['n_obs']} (expected 9, reference-only)")

print(f"\nErrors: {len(errors)} | Anonymous requests: {len(anon_results)} (all should show n_obs=9)")
print(f"Cross-tenant contamination detected: {contamination_found}")
print(f"*** TEST 1 RESULT: {'FAIL' if (errors or contamination_found) else 'PASS'} ***")

print()
print("=" * 70)
print("TEST 2: performance at current scale vs a much larger data volume")
print("=" * 70)

def bench_estimate(n=20):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        client.post("/api/model/project", json={"operator": "SPDC", "dia": 6, "terrain": "Swamp"})
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return times

baseline = bench_estimate(20)
print(f"BASELINE (~440 obs, {N_TENANTS} extra tenants): "
     f"p50={baseline[len(baseline)//2]:.1f}ms  p95={baseline[int(len(baseline)*0.95)]:.1f}ms  "
     f"max={max(baseline):.1f}ms")

# Bulk-load a much larger volume: 2000 items x ~50 obs each = 100k+ observations,
# spread across many categories/tenants, to see if the new per-line-item DB
# query pattern degrades at scale the way the old in-memory JSON approach never could.
print("\nBulk-loading ~100,000 additional observations across many items/tenants...")
t0 = time.perf_counter()
with Session(engine) as s:
    bulk_tenants = []
    for i in range(10):
        t = Tenant(name=f"Bulk Co {i}", slug=f"bulk-co-{i}")
        s.add(t); s.flush()
        bulk_tenants.append(t.id)

    cats = s.exec(select(Category)).all()
    cat_ids = [c.id for c in cats]

    items = []
    for tid in bulk_tenants:
        for cid in cat_ids[:8]:  # spread across 8 real categories
            for j in range(25):  # 25 items per tenant per category
                it = Item(tenant_id=tid, category_id=cid, canonical_name=f"BulkItem-{tid}-{cid}-{j}",
                         unit="each", attributes={"dia_in": random.choice([4,6,8,10]), "terrain": "Swamp"})
                s.add(it)
                items.append(it)
    s.flush()
    item_data = [(it.id, it.tenant_id) for it in items]
    s.commit()  # MUST commit before the separate bulk-insert transaction
                # references these tenant/item IDs — flush() alone assigns
                # IDs within the transaction but doesn't persist them; without
                # this commit, exiting the `with Session(...)` block below
                # rolls the whole thing back and the bulk insert hits a
                # foreign-key violation against rows that no longer exist.
print(f"  created {len(item_data)} items in {time.perf_counter()-t0:.2f}s")

from sqlalchemy import text
rows = []
for iid, tid in item_data:
    base = random.uniform(5, 500)
    for _ in range(random.randint(40, 60)):
        rate = round(base * random.uniform(0.85, 1.15), 4)
        rows.append(dict(tenant_id=tid, item_id=iid, source_type="PO", source_ref="", vendor="Bulk",
                        operator="SPDC", currency="USD", orig_rate=rate, orig_year=2024, qty=None,
                        spec_snapshot="{}", normalised_base=rate, norm_method="bulk", confidence_flag="OK",
                        status="APPROVED", submitted_by=None, approved_by=None, notes=None,
                        created_at="2024-01-01 00:00:00"))
t1 = time.perf_counter()
with engine.begin() as conn:
    conn.execute(text("""
        INSERT INTO observation (tenant_id, item_id, source_type, source_ref, vendor, operator,
                                 currency, orig_rate, orig_year, qty, spec_snapshot,
                                 normalised_base, norm_method, confidence_flag, status,
                                 submitted_by, approved_by, notes, created_at)
        VALUES (:tenant_id, :item_id, :source_type, :source_ref, :vendor, :operator,
               :currency, :orig_rate, :orig_year, :qty, :spec_snapshot,
               :normalised_base, :norm_method, :confidence_flag, :status,
               :submitted_by, :approved_by, :notes, :created_at)
    """), rows)
print(f"  bulk-inserted {len(rows)} observations in {time.perf_counter()-t1:.2f}s")

with Session(engine) as s:
    total_obs = len(s.exec(select(Observation)).all())
    total_items = len(s.exec(select(Item)).all())
print(f"  DB now has {total_obs} observations, {total_items} items total")

at_scale = bench_estimate(20)
print(f"\nAT SCALE ({total_obs} obs, {total_items} items): "
     f"p50={at_scale[len(at_scale)//2]:.1f}ms  p95={at_scale[int(len(at_scale)*0.95)]:.1f}ms  "
     f"max={max(at_scale):.1f}ms")

slowdown = at_scale[len(at_scale)//2] / baseline[len(baseline)//2]
print(f"\nSlowdown factor (p50 at-scale / p50 baseline): {slowdown:.2f}x")
print(f"*** TEST 2 RESULT: {'FAIL - meaningful degradation' if slowdown > 3 else 'PASS - holds up at scale'} ***")

print()
print("=" * 70)
print("TEST 3: query plan verification — is this actually using indexes?")
print("=" * 70)

import sqlite3
raw = sqlite3.connect(db_path)

queries = [
    ("db_observation_stats-style join (category + tenant + status)",
     """SELECT o.* FROM observation o
        JOIN item i ON o.item_id = i.id
        JOIN category c ON i.category_id = c.id
        WHERE o.status = 'APPROVED' AND c.name = 'Lay & Weld' AND o.tenant_id IN (1, 2)"""),
    ("db_operator_lay_weld_rate-style join (2 category names + operator)",
     """SELECT o.* FROM observation o
        JOIN item i ON o.item_id = i.id
        JOIN category c ON i.category_id = c.id
        WHERE o.status = 'APPROVED' AND c.name IN ('Lay & Weld', 'Lay & Weld (arc)')
              AND o.operator = 'SPDC' AND o.tenant_id IN (1, 2)"""),
]
for label, sql in queries:
    plan = raw.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
    plan_str = " | ".join(str(p[-1]) for p in plan)
    uses_index = "USING INDEX" in plan_str.upper() or "SEARCH" in plan_str.upper()
    scans_table = "SCAN " in plan_str.upper() and "SCAN TABLE" in plan_str.upper() and "USING INDEX" not in plan_str.upper()
    print(f"\n{label}:")
    print(f"  {plan_str}")
    print(f"  uses index: {uses_index}  |  full table scan present: {scans_table}")

print()
print("=" * 70)
print("TEST 4: edge cases")
print("=" * 70)

# 4a. A brand new tenant with ZERO approved data for a category
with Session(engine) as s:
    empty_tenant = Tenant(name="Empty Co", slug="empty-co")
    s.add(empty_tenant); s.commit()
    empty_id = empty_tenant.id
    u = User(tenant_id=empty_id, email="est@empty.io", full_name="Empty Estimator",
             role=Role.ESTIMATOR, password_hash=hash_password("stress-password-1"))
    s.add(u); s.commit()

r = client.post("/api/v2/auth/login", json={"email": "est@empty.io", "password": "stress-password-1"})
empty_token = r.json()["access_token"]
r2 = client.post("/api/model/project", headers={"Authorization": f"Bearer {empty_token}"},
                 json={"operator": "SPDC", "dia": 6, "terrain": "Swamp"})
print(f"4a. Zero-private-data tenant estimate: HTTP {r2.status_code}", end="  ")
if r2.status_code == 200:
    lw = next(l for l in r2.json()["lines"] if l["description"].startswith("Lay & weld"))
    print(f"-> n_obs={lw['source']['n_obs']} (expect 9, reference-only, no crash)")
else:
    print("-> UNEXPECTED FAILURE:", r2.text[:200])

# 4b. Concurrent submit+approve happening WHILE estimates are being requested
est_h = {"Authorization": f"Bearer {empty_token}"}
r3 = client.post("/api/v2/auth/login", json={"email": "estimator@demo.io", "password": "changeme-estimator"})
demo_token = r3.json()["access_token"]
demo_h = {"Authorization": f"Bearer {demo_token}"}
r4 = client.post("/api/v2/auth/login", json={"email": "approver@demo.io", "password": "changeme-approver"})
apr_h = {"Authorization": f"Bearer {r4.json()['access_token']}"}

def hammer_estimates(n=15):
    results = []
    for _ in range(n):
        r = client.post("/api/model/project", headers=demo_h, json={"operator": "SPDC", "dia": 6, "terrain": "Swamp"})
        results.append(r.status_code)
    return results

def submit_and_approve():
    sub = client.post("/api/v2/observations", headers=demo_h, json={
        "category_path": "Pipeline > Construction > Lay & Weld (arc)",
        "canonical_name": "Lay & Weld 6\" Swamp", "unit": "m",
        "attributes": {"dia_in": 6, "terrain": "Swamp"},
        "source_type": "manual", "operator": "SPDC",
        "currency": "USD", "orig_rate": 42.0, "orig_year": 2024,
    })
    if sub.status_code != 200:
        return "submit_failed"
    obs_id = sub.json()["observation_id"]
    appr = client.post(f"/api/v2/observations/{obs_id}/review", headers=apr_h, json={"approve": True})
    return appr.status_code

with cf.ThreadPoolExecutor(max_workers=5) as ex:
    f1 = ex.submit(hammer_estimates, 15)
    f2 = ex.submit(submit_and_approve)
    estimate_codes = f1.result()
    approve_result = f2.result()

print(f"4b. 15 estimate requests concurrent with a submit+approve: "
     f"all 200? {all(c == 200 for c in estimate_codes)}  |  approve result: {approve_result}")
print("    (every read during a concurrent write must see a consistent state — no crashes, no partial data)")

print()
print("ALL STRESS TESTS COMPLETE")
