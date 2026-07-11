"""
Write services — every mutation is transactional, tenant-scoped, audited.

The C-1 fix in behaviour: `submit_observation` only ever creates a PENDING
row. It cannot change a benchmark. Promotion to APPROVED happens in
`approve_observation`, which requires an approver principal and rebuilds the
affected cell atomically. The C-2 fix: it all runs inside one DB transaction,
so concurrent writers can't lose updates, duplicate IDs, or corrupt state.
"""
import statistics as st
from typing import Optional
from sqlmodel import Session, select

from .models import (
    Observation, Item, Benchmark, Category, AuditLog,
    ObsStatus, SourceType, DataTier, User, Role,
)
from .escalation import normalise


def _audit(session, *, tenant_id, user_id, action, entity_type, entity_id, detail=None):
    session.add(AuditLog(tenant_id=tenant_id, user_id=user_id, action=action,
                         entity_type=entity_type, entity_id=str(entity_id),
                         detail=detail or {}))


from sqlalchemy.exc import IntegrityError


def _get_or_create_category(session, category_path: str, escalation_index_key) -> Category:
    """Category is GLOBAL shared taxonomy — no tenant filter, ever. Concurrency-
    safe: if two tenants race to create the same brand-new category path, the
    UniqueConstraint on `path` rejects the loser's INSERT inside a SAVEPOINT,
    and we simply re-fetch the winner's row instead of erroring."""
    cat = session.exec(select(Category).where(Category.path == category_path)).first()
    if cat:
        return cat
    cat = Category(name=category_path.split(">")[-1].strip(), path=category_path,
                   kind="class", escalation_index_key=escalation_index_key)
    try:
        with session.begin_nested():
            session.add(cat)
            session.flush()
    except IntegrityError:
        cat = session.exec(select(Category).where(Category.path == category_path)).first()
        if not cat:
            raise
    return cat


def _get_or_create_item(session, tenant_id: int, category_id: int, canonical_name: str,
                        unit: str, attributes: dict, escalation_index_key,
                        cat_escalation_index_key) -> Item:
    """Item is TENANT-PRIVATE — every lookup and every insert is scoped to
    tenant_id. This is the fix for the cross-tenant collision: two tenants
    submitting an identically-named item under the same category ALWAYS get
    two distinct Item rows, so their observations and benchmarks can never
    blend. The UniqueConstraint(tenant_id, category_id, canonical_name) plus
    the SAVEPOINT retry below also closes the concurrent-first-submission
    duplicate-row race (two requests from the SAME tenant, same new item,
    at the same time)."""
    item = session.exec(
        select(Item).where(Item.tenant_id == tenant_id, Item.category_id == category_id,
                           Item.canonical_name == canonical_name)
    ).first()
    if item:
        return item
    item = Item(tenant_id=tenant_id, category_id=category_id, canonical_name=canonical_name,
               unit=unit or "each", attributes=attributes or {},
               escalation_index_key=escalation_index_key or cat_escalation_index_key)
    try:
        with session.begin_nested():
            session.add(item)
            session.flush()
    except IntegrityError:
        item = session.exec(
            select(Item).where(Item.tenant_id == tenant_id, Item.category_id == category_id,
                               Item.canonical_name == canonical_name)
        ).first()
        if not item:
            raise
    return item


def _resolve_item(session, tenant_id, category_path, canonical_name, unit,
                  attributes, escalation_index_key) -> Item:
    """Find-or-create the item for a submission. Category is shared taxonomy
    (never tenant-filtered); Item is tenant-private (always tenant-filtered).
    Entity-resolution proper (fuzzy alias matching across near-duplicate
    names) is the separate MDM subsystem — this is the exact-match base."""
    cat = _get_or_create_category(session, category_path, escalation_index_key)
    item = _get_or_create_item(session, tenant_id, cat.id, canonical_name, unit,
                               attributes, escalation_index_key, cat.escalation_index_key)
    return item, cat


def submit_observation(session: Session, *, user: User, category_path: str,
                       canonical_name: str, unit: str, attributes: dict,
                       source_type: str, vendor: Optional[str], operator: Optional[str],
                       currency: str, orig_rate: float, orig_year: int,
                       qty: Optional[float] = None, notes: str = "",
                       escalation_index_key: Optional[str] = None) -> dict:
    """ESTIMATOR+ only. Creates a PENDING observation — never touches a live
    benchmark. Validates at the trust boundary (audit H-1)."""
    # ── validation (H-1) ──
    if not (0 < orig_rate < 1e9):
        raise ValueError("orig_rate out of range")
    if not (2000 <= orig_year <= 2100):
        raise ValueError("orig_year out of range")
    cur = (currency or "USD").upper()
    if cur not in ("USD", "NGN"):
        raise ValueError("currency must be USD or NGN")
    try:
        stype = SourceType(source_type)
    except ValueError:
        stype = SourceType.MANUAL
    for f in (canonical_name, category_path):
        if not f or len(f) > 300:
            raise ValueError("name/category required, max 300 chars")

    item, cat = _resolve_item(session, user.tenant_id, category_path, canonical_name,
                              unit, attributes, escalation_index_key)
    idx_key = item.escalation_index_key or cat.escalation_index_key or "US_PPI_FG"
    norm, prov = normalise(session, orig_rate=orig_rate, currency=cur,
                           year=orig_year, index_key=idx_key)

    obs = Observation(
        tenant_id=user.tenant_id, item_id=item.id, source_type=stype,
        vendor=vendor, operator=operator, currency=cur, orig_rate=orig_rate,
        orig_year=orig_year, qty=qty, spec_snapshot=attributes or {},
        normalised_base=norm, norm_method=prov["method"],
        status=ObsStatus.PENDING, submitted_by=user.id, notes=(notes or None)[:2000] if notes else None,
    )
    session.add(obs); session.flush()
    _audit(session, tenant_id=user.tenant_id, user_id=user.id,
           action="observation.submit", entity_type="observation", entity_id=obs.id,
           detail={"item": canonical_name, "normalised": norm, "status": "pending"})
    session.commit()
    return {"observation_id": obs.id, "status": obs.status.value,
            "normalised_base": norm, "normalisation": prov, "item_id": item.id,
            "message": "Submitted for review — pending approval before it affects benchmarks."}


def approve_observation(session: Session, *, user: User, observation_id: int,
                        approve: bool = True) -> dict:
    """APPROVER+ only. Promotes/rejects a pending observation and rebuilds the
    affected benchmark cell — all in one transaction (C-2).

    Uses an atomic conditional UPDATE (WHERE status='pending') rather than a
    read-check-write, so concurrent approve calls on the same observation
    cannot both succeed — only the first commits; the rest see 0 rows
    affected and are rejected. This closes a race where N concurrent
    approvers could each pass a status check before any of them committed,
    each re-running the benchmark rebuild and duplicating the audit trail.
    """
    from sqlalchemy import update as sa_update

    obs = session.get(Observation, observation_id)
    if not obs or obs.tenant_id != user.tenant_id:
        raise ValueError("Observation not found in your tenant")

    new_status = ObsStatus.APPROVED if approve else ObsStatus.REJECTED
    result = session.exec(
        sa_update(Observation)
        .where(Observation.id == observation_id, Observation.status == ObsStatus.PENDING)
        .values(status=new_status, approved_by=user.id)
    )
    if result.rowcount == 0:
        # Either it never existed (already excluded above) or someone else
        # already resolved it in a concurrent transaction — reject cleanly.
        session.rollback()
        raise ValueError(f"Observation already {obs.status.value}")

    if approve:
        rebuild_benchmark_for_item(session, obs.item_id)
    _audit(session, tenant_id=user.tenant_id, user_id=user.id,
           action=f"observation.{'approve' if approve else 'reject'}",
           entity_type="observation", entity_id=observation_id)
    session.commit()
    return {"observation_id": observation_id, "status": new_status.value}


def rebuild_benchmark_for_item(session: Session, item_id: int):
    """Recompute one benchmark cell from APPROVED observations only."""
    item = session.get(Item, item_id)
    obs = session.exec(
        select(Observation).where(Observation.item_id == item_id,
                                  Observation.status == ObsStatus.APPROVED)
    ).all()
    rates = [o.normalised_base for o in obs if o.normalised_base is not None]
    operators = sorted({o.operator for o in obs if o.operator})
    years = sorted({o.orig_year for o in obs if o.orig_year})
    n = len(rates)
    conf = "HIGH" if n >= 3 else "MEDIUM" if n == 2 else "LOW" if n == 1 else "NONE"
    bm = session.exec(select(Benchmark).where(Benchmark.item_id == item_id)).first()
    if not bm:
        bm = Benchmark(item_id=item_id, tenant_id=item.tenant_id)
        session.add(bm)
    bm.low = round(min(rates), 2) if rates else None
    bm.high = round(max(rates), 2) if rates else None
    bm.median = round(st.median(rates), 2) if rates else None
    bm.n_obs = n
    bm.confidence = conf
    bm.operators = operators
    bm.year_range = f"{min(years)}\u2013{max(years)}" if years else ""
    session.flush()
    return bm
