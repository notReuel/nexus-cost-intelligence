"""
Migrate the JSON knowledge base → the tenant-scoped DB.

Ports all 440 vetted observations into the shared NEPL reference tenant as
APPROVED (they're already-vetted historical data), rebuilds items +
benchmarks, seeds escalation indices, and creates an admin + a demo customer
tenant. Idempotent-ish: refuses to double-load if observations already exist.
"""
import json
from pathlib import Path
from datetime import date
from sqlmodel import Session, select

from .db import engine, init_db, run_alembic_upgrade, session_scope
from .models import (
    Tenant, User, Category, Item, Observation, Benchmark,
    Role, ObsStatus, SourceType, DataTier,
)
from .escalation import seed_escalation_indices, normalise
from .auth import hash_password

_ENGINE_DIR = Path(__file__).parent.parent / "engine"

_SOURCE_MAP = {
    "tender": SourceType.TENDER, "afe": SourceType.AFE, "beme": SourceType.AFE,
    "po": SourceType.PO, "invoice": SourceType.INVOICE, "quote": SourceType.QUOTE,
}


def _dia_of(spec):
    d = (spec or {}).get("dia")
    try:
        return int(float(str(d).strip().rstrip('"').rstrip("\u2033")))
    except (TypeError, ValueError):
        return None


def run_migration(reset: bool = False):
    if reset:
        from sqlmodel import SQLModel
        from sqlalchemy import text
        SQLModel.metadata.drop_all(engine)
        # drop_all() only knows about our own model tables — Alembic's own
        # bookkeeping table isn't part of that metadata, so it survives a
        # reset untouched. Left alone, Alembic sees "already at head" on
        # the next upgrade and skips recreating everything we just dropped.
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()  # drop any pooled connections holding a stale
                          # cached view of the schema before recreating it
    run_alembic_upgrade()  # schema via versioned migrations, not create_all()
    engine.dispose()  # and again — Alembic's DDL runs on its OWN separate
                      # engine/connection, so the pooled `engine` used by
                      # session_scope() below must be forced to reconnect
                      # fresh rather than reuse a pre-migration connection.

    with session_scope() as s:
        seed_escalation_indices(s)

        existing = s.exec(select(Observation)).first()
        if existing:
            print("Observations already present — skipping load. Use reset=True to rebuild.")
            return _summary(s)

        # ── Tenants ──────────────────────────────────────────────────────
        ref = Tenant(name="NEPL Reference Library", slug="nepl-ref",
                     base_currency="USD", is_reference=True)
        demo = Tenant(name="Demo Operator Co", slug="demo-op", base_currency="USD")
        s.add(ref); s.add(demo); s.flush()

        # ── Users (admin on ref, estimator+approver on demo) ─────────────
        s.add(User(tenant_id=ref.id, email="admin@nepl.io", full_name="Platform Admin",
                   role=Role.ADMIN, password_hash=hash_password("changeme-admin")))
        s.add(User(tenant_id=demo.id, email="estimator@demo.io", full_name="Demo Estimator",
                   role=Role.ESTIMATOR, password_hash=hash_password("changeme-estimator")))
        s.add(User(tenant_id=demo.id, email="approver@demo.io", full_name="Demo Approver",
                   role=Role.APPROVER, password_hash=hash_password("changeme-approver")))
        s.flush()

        # ── Load JSON observations ───────────────────────────────────────
        raw = json.load(open(_ENGINE_DIR / "raw_observations.json"))["observations"]

        cat_cache: dict = {}
        item_cache: dict = {}

        def get_category(category_name, sub_category):
            path = f"Pipeline > {category_name} > {sub_category}"
            if path in cat_cache:
                return cat_cache[path]
            c = Category(name=sub_category, path=path, kind="class",
                         escalation_index_key="US_PPI_FG",
                         default_data_tier=DataTier.FIRST_PARTY)
            s.add(c); s.flush()
            cat_cache[path] = c
            return c

        def get_item(cat, sub_category, dia, terrain, unit):
            key = (cat.id, sub_category, dia, terrain)
            if key in item_cache:
                return item_cache[key]
            name = f"{sub_category} {dia or ''}\" {terrain}".strip()
            it = Item(tenant_id=ref.id, category_id=cat.id, canonical_name=name,
                      unit=unit or "each",
                      attributes={"dia_in": dia, "terrain": terrain},
                      data_tier=DataTier.FIRST_PARTY, escalation_index_key="US_PPI_FG")
            s.add(it); s.flush()
            item_cache[key] = it
            return it

        loaded, factor_ok = 0, 0
        for o in raw:
            spec = o.get("spec") or {}
            dia = _dia_of(spec)
            terrain = spec.get("terrain")
            cat = get_category(o.get("category") or "Construction",
                               o.get("sub_category") or "Unclassified")
            item = get_item(cat, o.get("sub_category") or "Unclassified", dia, terrain, o.get("unit"))

            norm, _prov = normalise(
                s, orig_rate=float(o["orig_rate"]),
                currency=o.get("orig_currency", "USD"), year=int(o.get("year", 2024)),
                index_key="US_PPI_FG",
            )
            # integrity check: new engine reproduces the stored usd_2024
            if o.get("usd_2024") is not None and abs(norm - o["usd_2024"]) <= max(0.02, 0.005 * o["usd_2024"]):
                factor_ok += 1

            st = _SOURCE_MAP.get(str(o.get("source", "")).lower(), SourceType.TENDER)
            s.add(Observation(
                tenant_id=ref.id, item_id=item.id, source_type=st,
                source_ref=o.get("source_doc") or o.get("source_record_id") or "",
                vendor=o.get("vendor"), operator=o.get("operator"),
                currency=o.get("orig_currency", "USD"), orig_rate=float(o["orig_rate"]),
                orig_year=int(o.get("year", 2024)),
                qty=None, spec_snapshot=spec, normalised_base=norm,
                norm_method=o.get("norm_method", ""), confidence_flag=o.get("flag", "OK"),
                status=ObsStatus.APPROVED,   # seed data is pre-vetted
                notes=o.get("notes"),
            ))
            loaded += 1

        s.flush()
        print(f"Loaded {loaded} observations; {factor_ok} reproduced stored factor within tolerance.")

        # ── Build benchmarks from APPROVED observations ─────────────────
        rebuild_all_benchmarks(s)
        return _summary(s)


def rebuild_all_benchmarks(session: Session):
    import statistics as st
    items = session.exec(select(Item)).all()
    for it in items:
        obs = session.exec(
            select(Observation).where(
                Observation.item_id == it.id,
                Observation.status == ObsStatus.APPROVED,
            )
        ).all()
        rates = [o.normalised_base for o in obs if o.normalised_base is not None]
        operators = sorted({o.operator for o in obs if o.operator})
        years = sorted({o.orig_year for o in obs if o.orig_year})
        n = len(rates)
        conf = "HIGH" if n >= 3 else "MEDIUM" if n == 2 else "LOW" if n == 1 else "NONE"
        bm = session.exec(select(Benchmark).where(Benchmark.item_id == it.id)).first()
        if not bm:
            bm = Benchmark(item_id=it.id, tenant_id=it.tenant_id)
            session.add(bm)
        bm.low = round(min(rates), 2) if rates else None
        bm.high = round(max(rates), 2) if rates else None
        bm.median = round(st.median(rates), 2) if rates else None
        bm.n_obs = n
        bm.confidence = conf
        bm.operators = operators
        bm.year_range = f"{min(years)}\u2013{max(years)}" if years else ""
    session.flush()


def _summary(session: Session):
    return {
        "tenants": len(session.exec(select(Tenant)).all()),
        "users": len(session.exec(select(User)).all()),
        "categories": len(session.exec(select(Category)).all()),
        "items": len(session.exec(select(Item)).all()),
        "observations": len(session.exec(select(Observation)).all()),
        "benchmarks": len(session.exec(select(Benchmark)).all()),
    }


if __name__ == "__main__":
    import sys
    summary = run_migration(reset="--reset" in sys.argv)
    print("Migration summary:", summary)
