"""
Data integrity stress test at scale (Enterprise Validation sprint, item 4).

Bulk-loads 100,000+ observations across thousands of items and multiple
tenants directly at the DB layer (the realistic path for historical PO/
tender ingestion — nobody submits 100k rows through 100k individual API
calls), then verifies:
  - benchmark correctness (spot-checked against manual computation)
  - confidence-tier calculation correctness
  - query performance at scale (measured, with EXPLAIN QUERY PLAN)
  - index usage (not a full table scan)
  - no duplicate items (unique constraint honoured under bulk load)
  - no benchmark corruption
"""
import sys, os, time, random, statistics as st, resource
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/stress_test.db")
os.environ.setdefault("JWT_SECRET", "stress-secret")

db_path = os.environ["DATABASE_URL"].replace("sqlite:///", "")
for suffix in ("", "-wal", "-shm"):
    try: os.unlink(db_path + suffix)
    except OSError: pass

from app.core.migrate import run_migration
from app.core.db import engine, session_scope
from app.core.models import Tenant, Category, Item, Observation, Benchmark, ObsStatus, SourceType, DataTier
from sqlmodel import Session, select
from sqlalchemy import text
from app.core.service import rebuild_benchmark_for_item

run_migration(reset=True)

random.seed(42)
N_TENANTS = 5
N_CATEGORIES = 20
N_ITEMS_PER_TENANT_CATEGORY = 20   # -> 5 * 20 * 20 = 2000 items
N_OBS_TARGET = 120_000

print(f"Target: {N_TENANTS} tenants x {N_CATEGORIES} categories x {N_ITEMS_PER_TENANT_CATEGORY} items/cell "
      f"= {N_TENANTS * N_CATEGORIES * N_ITEMS_PER_TENANT_CATEGORY} items, ~{N_OBS_TARGET} observations")

t0 = time.perf_counter()
with session_scope() as s:
    tenants = [Tenant(name=f"Stress Tenant {i}", slug=f"stress-{i}", base_currency="USD") for i in range(N_TENANTS)]
    for t in tenants: s.add(t)
    s.flush()

    categories = []
    for c in range(N_CATEGORIES):
        cat = Category(name=f"Cat{c}", path=f"Stress > Group{c//5} > Cat{c}", kind="class")
        s.add(cat)
        categories.append(cat)
    s.flush()

    items = []
    for tenant in tenants:
        for cat in categories:
            for i in range(N_ITEMS_PER_TENANT_CATEGORY):
                it = Item(tenant_id=tenant.id, category_id=cat.id,
                          canonical_name=f"Item-{cat.id}-{i}", unit="each",
                          attributes={"idx": i}, data_tier=DataTier.FIRST_PARTY)
                s.add(it)
                items.append(it)
    s.flush()
    # extract plain values NOW, while the session is still open — avoids
    # DetachedInstanceError once session_scope() closes this session below.
    item_records = [(it.id, it.tenant_id) for it in items]
    category_records = [(c.id,) for c in categories]
    tenant_records = [(t.id,) for t in tenants]
    print(f"Created {len(tenant_records)} tenants, {len(category_records)} categories, {len(item_records)} items "
          f"in {time.perf_counter()-t0:.2f}s")

# Bulk-insert observations via raw executemany (the realistic bulk-ingest path)
t1 = time.perf_counter()
item_ids = [rec[0] for rec in item_records]
item_tenant = {iid: tid for iid, tid in item_records}
category_ids = [rec[0] for rec in category_records]
tenant_ids = [rec[0] for rec in tenant_records]

rows = []
obs_per_item = N_OBS_TARGET // len(item_ids)
for item_id in item_ids:
    n = random.randint(max(1, obs_per_item - 3), obs_per_item + 3)
    base_rate = round(random.uniform(5, 500), 2)
    tenant_id = item_tenant[item_id]
    for _ in range(n):
        rate = round(base_rate * random.uniform(0.85, 1.15), 4)
        rows.append(dict(tenant_id=tenant_id, item_id=item_id, source_type=SourceType.PO.name,
                         source_ref="", vendor="BulkVendor", operator=None, currency="USD",
                         orig_rate=rate, orig_year=2024, qty=None, spec_snapshot="{}",
                         normalised_base=rate, norm_method="bulk-load", confidence_flag="OK",
                         status=ObsStatus.APPROVED.name, submitted_by=None, approved_by=None,
                         notes=None, created_at="2024-01-01 00:00:00"))

print(f"Generated {len(rows)} observation rows in {time.perf_counter()-t1:.2f}s, inserting...")
t2 = time.perf_counter()
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
insert_time = time.perf_counter() - t2
print(f"Bulk-inserted {len(rows)} observations in {insert_time:.2f}s "
      f"({len(rows)/insert_time:.0f} rows/sec)")

# Rebuild all benchmarks — measure this explicitly, it's the O(n) recompute
# flagged as a scalability risk in the earlier Staff Engineer review.
t3 = time.perf_counter()
with session_scope() as s:
    for item_id in item_ids:
        rebuild_benchmark_for_item(s, item_id)
rebuild_time = time.perf_counter() - t3
print(f"Rebuilt {len(item_ids)} benchmarks (from {len(rows)} observations total) "
      f"in {rebuild_time:.2f}s ({len(item_ids)/rebuild_time:.1f} items/sec)")

# ── Verification ──────────────────────────────────────────────────
with Session(engine) as s:
    total_obs = s.exec(text("SELECT COUNT(*) FROM observation")).first()[0]
    total_items = s.exec(text("SELECT COUNT(*) FROM item")).first()[0]
    total_bm = s.exec(text("SELECT COUNT(*) FROM benchmark")).first()[0]
    print(f"\nFinal counts: {total_obs} observations, {total_items} items, {total_bm} benchmarks")

    # No duplicate items (unique constraint honoured under bulk load)
    dup = s.exec(text("""
        SELECT tenant_id, category_id, canonical_name, COUNT(*) c
        FROM item GROUP BY tenant_id, category_id, canonical_name HAVING c > 1
    """)).all()
    print(f"Duplicate items found: {len(dup)} (expect 0)")

    # Spot-check benchmark correctness for 5 random items
    print("\n=== spot-check: benchmark math vs manual computation ===")
    sample_items = random.sample(item_ids, 5)
    for iid in sample_items:
        bm = s.exec(select(Benchmark).where(Benchmark.item_id == iid)).first()
        obs = s.exec(select(Observation).where(Observation.item_id == iid,
                                               Observation.status == ObsStatus.APPROVED)).all()
        rates = sorted(o.normalised_base for o in obs)
        manual_median = st.median(rates)
        manual_low, manual_high = min(rates), max(rates)
        manual_conf = "HIGH" if len(rates) >= 3 else "MEDIUM" if len(rates) == 2 else "LOW"
        ok = (abs(bm.median - manual_median) < 0.01 and abs(bm.low - manual_low) < 0.01
              and abs(bm.high - manual_high) < 0.01 and bm.confidence == manual_conf
              and bm.n_obs == len(rates))
        print(f"  item {iid}: n={len(rates)} db_median={bm.median} manual={manual_median:.2f} "
              f"conf={bm.confidence}/{manual_conf}  MATCH={ok}")

    # Query performance + index usage at this scale
    print("\n=== query performance at scale ===")
    import sqlite3
    raw = sqlite3.connect(db_path)

    def timed_query(label, sql, params=()):
        t = time.perf_counter()
        rows = raw.execute(sql, params).fetchall()
        dt = (time.perf_counter() - t) * 1000
        print(f"  {label}: {dt:.2f}ms ({len(rows)} rows)")
        return dt

    timed_query("benchmarks list (single tenant, paginated 50)",
               "SELECT i.id, i.canonical_name, b.median FROM item i JOIN benchmark b ON b.item_id=i.id "
               "WHERE i.tenant_id = ? LIMIT 50", (tenant_ids[0],))
    timed_query("benchmarks search by name (ilike-equivalent)",
               "SELECT i.id FROM item i WHERE i.tenant_id = ? AND i.canonical_name LIKE ?",
               (tenant_ids[0], "%Item-%1%"))
    timed_query("observation lookup by item+status (the review-queue pattern)",
               "SELECT COUNT(*) FROM observation WHERE item_id = ? AND status = ?",
               (item_ids[0], "APPROVED"))

    print("\n=== EXPLAIN QUERY PLAN — confirming index usage, not table scans ===")
    for label, sql, params in [
        ("benchmarks by tenant", "SELECT * FROM item WHERE tenant_id = ?", (tenant_ids[0],)),
        ("item by tenant+category+name (the uniqueness check)",
         "SELECT * FROM item WHERE tenant_id=? AND category_id=? AND canonical_name=?",
         (tenant_ids[0], category_ids[0], "Item-1-1")),
        ("observation by item+status", "SELECT * FROM observation WHERE item_id=? AND status=?",
         (item_ids[0], "APPROVED")),
    ]:
        plan = raw.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
        plan_str = " | ".join(str(p[-1]) for p in plan)
        uses_index = "USING INDEX" in plan_str.upper() or "USING COVERING INDEX" in plan_str.upper() or "SEARCH" in plan_str.upper()
        print(f"  {label}:\n    {plan_str}\n    uses index: {uses_index}")

print(f"\nTotal wall time: {time.perf_counter()-t0:.2f}s")
peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB->MB on Linux
cpu_time = resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime
print(f"Peak RSS memory: {peak_rss_mb:.1f} MB")
print(f"Total CPU time (user+sys): {cpu_time:.2f}s")
