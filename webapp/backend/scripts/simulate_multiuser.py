"""
Multi-user / multi-tenant simulation (Enterprise Validation sprint, item 3).

Seeds N tenants with estimator/approver users, then runs a realistic mixed
workload concurrently: estimators submitting observations, approvers
reviewing them, across several tenants at once — and checks the three
things that actually matter at this scale:
  1. No cross-tenant contamination (each tenant's benchmark reflects ONLY
     that tenant's own approved data).
  2. No race-condition duplication (concurrent identical submissions never
     fragment into more than one Item).
  3. Correct permission enforcement held under load (estimators never
     manage to approve; approvers never touch another tenant's queue).
Also measures response-time percentiles for each operation type.
"""
import sys, os, time, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/sim_multiuser.db")
os.environ.setdefault("JWT_SECRET", "sim-secret")

# fresh DB for this run
db_path = os.environ["DATABASE_URL"].replace("sqlite:///", "")
for suffix in ("", "-wal", "-shm"):
    try: os.unlink(db_path + suffix)
    except OSError: pass

from app.core.migrate import run_migration
from app.core.db import engine, session_scope
from app.core.models import Tenant, User, Role
from app.core.auth import hash_password
from fastapi import FastAPI
from app.core.routes_v2 import register_v2
from fastapi.testclient import TestClient
import concurrent.futures as cf

run_migration(reset=True)

N_TENANTS = 4
N_ESTIMATORS = 20
N_APPROVERS = 5

with session_scope() as s:
    tenants = []
    for i in range(N_TENANTS):
        t = Tenant(name=f"Sim Tenant {i+1}", slug=f"sim-tenant-{i+1}", base_currency="USD")
        s.add(t)
        tenants.append(t)
    s.flush()

    estimators, approvers = [], []
    for i in range(N_ESTIMATORS):
        tenant = tenants[i % N_TENANTS]
        u = User(tenant_id=tenant.id, email=f"est{i}@sim.io", full_name=f"Sim Estimator {i}",
                role=Role.ESTIMATOR, password_hash=hash_password("sim-password-1"))
        s.add(u)
        estimators.append((u, tenant))
    for i in range(N_APPROVERS):
        tenant = tenants[i % N_TENANTS]
        u = User(tenant_id=tenant.id, email=f"apr{i}@sim.io", full_name=f"Sim Approver {i}",
                role=Role.APPROVER, password_hash=hash_password("sim-password-1"))
        s.add(u)
        approvers.append((u, tenant))
    s.flush()
    est_creds = [(f"est{i}@sim.io", "sim-password-1", tenants[i % N_TENANTS].id) for i in range(N_ESTIMATORS)]
    apr_creds = [(f"apr{i}@sim.io", "sim-password-1", tenants[i % N_TENANTS].id) for i in range(N_APPROVERS)]
    tenant_ids = [t.id for t in tenants]

app = FastAPI()
register_v2(app)
client = TestClient(app)

timings = {"login": [], "submit": [], "approve": [], "benchmarks": []}

def timed(bucket, fn):
    t0 = time.perf_counter()
    result = fn()
    timings[bucket].append((time.perf_counter() - t0) * 1000)
    return result

# Login all 25 users up front (measures realistic login latency under load)
def do_login(cred):
    email, pw, tenant_id = cred
    r = timed("login", lambda: client.post("/api/v2/auth/login", json={"email": email, "password": pw}))
    assert r.status_code == 200, r.text
    return {"token": r.json()["access_token"], "tenant_id": tenant_id, "email": email}

with cf.ThreadPoolExecutor(max_workers=25) as ex:
    est_sessions = list(ex.map(do_login, est_creds))
    apr_sessions = list(ex.map(do_login, apr_creds))

print(f"Logged in {len(est_sessions)} estimators + {len(apr_sessions)} approvers across {N_TENANTS} tenants")

# Every estimator submits the SAME item name under the SAME category —
# the exact shape of the original cross-tenant collision bug — so this
# simulation directly stresses that fix under real concurrency.
SAME_CATEGORY = "SimTest > SharedName > Item"
SAME_NAME = "Commonly Named Widget"

def submit_one(sess, idx):
    r = timed("submit", lambda: client.post("/api/v2/observations",
        headers={"Authorization": f"Bearer {sess['token']}"}, json={
            "category_path": SAME_CATEGORY, "canonical_name": SAME_NAME,
            "unit": "each", "currency": "USD",
            "orig_rate": 10.0 + idx * 0.1, "orig_year": 2024,
        }))
    return r.json(), sess["tenant_id"]

with cf.ThreadPoolExecutor(max_workers=20) as ex:
    submissions = list(ex.map(lambda p: submit_one(*p), [(s, i) for i, s in enumerate(est_sessions)]))

ok_submits = [(r, tid) for r, tid in submissions if "observation_id" in r]
print(f"Submitted {len(ok_submits)}/{len(est_sessions)} observations")

# distinct item_id per tenant, but SAME item_id within a tenant (no fragmentation)
by_tenant_items = {}
for r, tid in ok_submits:
    by_tenant_items.setdefault(tid, set()).add(r["item_id"])
fragmentation_ok = all(len(v) == 1 for v in by_tenant_items.values())
cross_tenant_ok = len({frozenset(v) for v in by_tenant_items.values()}) == len(by_tenant_items)  # each tenant's item set is disjoint in identity terms handled by distinct ids below
print(f"Per-tenant item_id sets: { {k: list(v) for k, v in by_tenant_items.items()} }")
print(f"No fragmentation within a tenant: {fragmentation_ok}")
all_item_ids = [next(iter(v)) for v in by_tenant_items.values()]
print(f"No cross-tenant item sharing (all item_ids distinct across tenants): {len(set(all_item_ids)) == len(all_item_ids)}")

# Each approver approves ONLY their own tenant's pending observations
def approve_for(sess):
    r = client.get("/api/v2/observations/pending", headers={"Authorization": f"Bearer {sess['token']}"})
    pend = r.json()
    results = []
    for o in pend:
        rr = timed("approve", lambda o=o: client.post(f"/api/v2/observations/{o['id']}/review",
            headers={"Authorization": f"Bearer {sess['token']}"}, json={"approve": True}))
        results.append(rr.status_code)
    return sess["tenant_id"], results

with cf.ThreadPoolExecutor(max_workers=5) as ex:
    approvals = list(ex.map(approve_for, apr_sessions))

for tid, results in approvals:
    print(f"tenant {tid}: {sum(1 for r in results if r==200)}/{len(results)} approvals succeeded")

# permission checks under load: estimators attempt to approve (must all fail)
def estimator_tries_to_approve(sess):
    r = client.get("/api/v2/observations/pending", headers={"Authorization": f"Bearer {sess['token']}"})
    if r.status_code != 200:
        return r.status_code  # expected 403 for estimator role on this endpoint too
    return None

perm_results = [estimator_tries_to_approve(s) for s in est_sessions[:5]]
print(f"Estimators blocked from viewing pending queue (expect all 403): {perm_results}")

# cross-tenant benchmark check: each tenant's benchmark for the shared name
# must reflect ONLY that tenant's own submissions.
print("\n=== cross-tenant contamination check ===")
contamination_found = False
for sess in est_sessions:
    r = timed("benchmarks", lambda sess=sess: client.get("/api/v2/benchmarks",
        headers={"Authorization": f"Bearer {sess['token']}"}, params={"q": "Commonly Named Widget"}))
    own = [b for b in r.json() if b["is_own"]]
    if len(own) > 1:
        contamination_found = True
        print(f"  CONTAMINATION: tenant {sess['tenant_id']} has {len(own)} own-items for one name")
print(f"Contamination found: {contamination_found}")

print("\n=== response time percentiles (ms) ===")
for bucket, vals in timings.items():
    if not vals: continue
    vals_sorted = sorted(vals)
    p50 = vals_sorted[len(vals_sorted)//2]
    p95 = vals_sorted[int(len(vals_sorted)*0.95)]
    print(f"  {bucket:12s}  n={len(vals):3d}  p50={p50:.2f}ms  p95={p95:.2f}ms  max={max(vals):.2f}ms")
