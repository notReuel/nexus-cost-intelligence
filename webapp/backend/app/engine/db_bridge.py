"""
Bridge between the legacy calibrated estimating engine and the tenant-scoped
Postgres core (Phase 1/2 of the "connect the two data pools" build).

This module replaces project_modeller.py's JSON-file lookups
(observation_stats, _operator_lay_weld_rate) with real queries against the
Observation/Item/Category tables — filtered to APPROVED status only (the
governance invariant: unreviewed data must never affect an estimate) and
scoped to the caller's tenant plus the shared reference library.

Public vs authenticated access:
  - No token  -> tenant_ids = [reference_tenant_id] only
  - Logged in -> tenant_ids = [caller_tenant_id, reference_tenant_id]
This is the same blending rule already used by GET /api/v2/benchmarks —
kept consistent rather than inventing a second policy.
"""
from typing import Optional, List
import statistics as _st
from sqlmodel import Session, select

from app.core.models import Observation, Item, Category, Tenant, ObsStatus


def resolve_tenant_scope(session: Session, caller_tenant_id: Optional[int]) -> List[int]:
    """The exact tenant_id list a query should be scoped to."""
    ref = session.exec(select(Tenant).where(Tenant.is_reference == True)).first()  # noqa: E712
    ids = [ref.id] if ref else []
    if caller_tenant_id is not None and caller_tenant_id not in ids:
        ids.append(caller_tenant_id)
    return ids


def _confidence(n: int) -> str:
    if n >= 3: return 'HIGH'
    if n == 2: return 'MEDIUM'
    if n == 1: return 'LOW'
    return 'NONE'


def db_observation_stats(session: Session, tenant_ids: List[int], sub_category,
                         dia: Optional[float] = None, terrain: Optional[str] = None,
                         operator_filter: Optional[list] = None, dia_tolerance: float = 2) -> dict:
    """DB-backed replacement for the legacy observation_stats(). Same return
    shape as before, so callers in project_modeller.py don't need to change
    how they consume it — only where the data comes from."""
    if isinstance(sub_category, str):
        sub_category = [sub_category]

    stmt = (
        select(Observation, Item)
        .join(Item, Observation.item_id == Item.id)
        .join(Category, Item.category_id == Category.id)
        .where(Observation.status == ObsStatus.APPROVED, Category.name.in_(sub_category))
    )
    if tenant_ids:
        stmt = stmt.where(Observation.tenant_id.in_(tenant_ids))
    rows = session.exec(stmt).all()

    def _matches_terrain(item: Item) -> bool:
        if not terrain:
            return True
        t = (item.attributes or {}).get('terrain')
        return t in (terrain, None, 'Land+Swamp')

    def _matches_dia(item: Item) -> float | None:
        d = (item.attributes or {}).get('dia_in')
        try:
            return float(d) if d is not None else None
        except (TypeError, ValueError):
            return None

    pool = [(o, it) for o, it in rows if _matches_terrain(it)]
    if dia is not None:
        near = [(o, it) for o, it in pool if _matches_dia(it) is not None
                and abs(_matches_dia(it) - dia) <= dia_tolerance]
        if near:
            pool = near

    op_all = pool
    if operator_filter:
        op_specific = [(o, it) for o, it in pool if o.operator in operator_filter]
        if op_specific:
            pool = op_specific

    rates = [o.normalised_base for o, _ in pool if o.normalised_base is not None]
    operators = sorted(set(o.operator for o, _ in op_all if o.operator))
    years = sorted(set(o.orig_year for o, _ in pool if o.orig_year))
    n = len(pool)
    return {
        'sub_category': sub_category[0] if len(sub_category) == 1 else ' / '.join(sub_category),
        'n_obs': n,
        'operators': operators,
        'operator_used': sorted(set(o.operator for o, _ in pool if o.operator)),
        'years': years,
        'year_range': (f"{min(years)}\u2013{max(years)}" if years else '\u2014'),
        'confidence': _confidence(n),
        'median': round(_st.median(rates), 2) if rates else None,
        'low': round(min(rates), 2) if rates else None,
        'high': round(max(rates), 2) if rates else None,
    }


def db_operator_lay_weld_rate(session: Session, tenant_ids: List[int], operator_filter,
                              dia: float, terrain: str):
    """DB-backed replacement for the legacy _operator_lay_weld_rate(). Same
    return shape: (low, mid, high, source_stat, used_operator_specific)."""
    lw_names = ['Lay & Weld', 'Lay & Weld (arc)']
    stmt = (
        select(Observation, Item)
        .join(Item, Observation.item_id == Item.id)
        .join(Category, Item.category_id == Category.id)
        .where(Observation.status == ObsStatus.APPROVED, Category.name.in_(lw_names))
    )
    if tenant_ids:
        stmt = stmt.where(Observation.tenant_id.in_(tenant_ids))
    rows = session.exec(stmt).all()

    def _dia_of(item: Item):
        d = (item.attributes or {}).get('dia_in')
        try:
            return float(d) if d is not None else None
        except (TypeError, ValueError):
            return None

    pool = [(o, it) for o, it in rows if (it.attributes or {}).get('terrain') == terrain]
    near = [(o, it) for o, it in pool if _dia_of(it) is not None and abs(_dia_of(it) - dia) <= 2]
    if near:
        pool = near

    used_specific = False
    if operator_filter:
        op_pool = [(o, it) for o, it in pool if o.operator in operator_filter]
        if op_pool:
            pool = op_pool
            used_specific = True

    rates = sorted(o.normalised_base for o, _ in pool if o.normalised_base is not None)
    if not rates:
        return None
    mid = _st.median(rates)
    low, high = rates[0], rates[-1]
    years = sorted(set(o.orig_year for o, _ in pool if o.orig_year))
    stat = {
        'sub_category': 'Lay & Weld',
        'n_obs': len(pool),
        'operators': sorted(set(o.operator for o, _ in pool if o.operator)),
        'operator_used': sorted(set(o.operator for o, _ in pool if o.operator)),
        'years': years,
        'year_range': f"{min(years)}\u2013{max(years)}" if years else '\u2014',
        'confidence': _confidence(len(pool)),
        'median': round(mid, 2), 'low': round(low, 2), 'high': round(high, 2),
    }
    return low, mid, high, stat, used_specific
