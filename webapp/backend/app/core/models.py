"""
NEPL NEXUS — core data model (Enterprise Cost Intelligence Platform).

Design principle (per both technical + business review):
    Separate the ENGINE (software: normalise, match, aggregate, score) from
    the KNOWLEDGE (data: observations, taxonomies, escalation indices,
    confidence models, supplier outcomes). The engine is code; the knowledge
    lives here, in tenant-scoped tables — never hardcoded.

This schema is category-agnostic. A 6" swamp lay & weld rate and a stainless
tablespoon PO line are the SAME row shape in `Observation`; only the JSON
`attributes` / `spec_snapshot` and the `Category` differ. One engine, many
modules.

Security foundation (closes audit C-1 / C-2):
  • Every domain row carries `tenant_id` → no cross-tenant access.
  • Observations enter as status=PENDING (review queue) → no unauthenticated
    or unreviewed write ever reaches a live benchmark.
  • SQLite/Postgres transactions + unique constraints → atomic, race-free
    writes (replaces the non-atomic JSON read-modify-write).
"""
from __future__ import annotations
from datetime import datetime, date
from enum import Enum
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON, UniqueConstraint, Index


# ─── Enumerations ────────────────────────────────────────────────────────
class Role(str, Enum):
    VIEWER = "viewer"        # read benchmarks only
    ESTIMATOR = "estimator"  # + model projects, submit observations
    APPROVER = "approver"    # + approve/reject submitted observations
    ADMIN = "admin"          # + manage users, categories, indices


class ObsStatus(str, Enum):
    PENDING = "pending"      # in the review queue — does NOT affect benchmarks
    APPROVED = "approved"    # counts toward the live benchmark
    REJECTED = "rejected"


class SourceType(str, Enum):
    TENDER = "tender"        # operator schedule of rates / tender eval
    PO = "po"                # historical purchase order (first-party)
    INVOICE = "invoice"
    QUOTE = "quote"          # vendor quotation
    AFE = "afe"              # authorisation for expenditure / BEME
    MANUAL = "manual"        # hand-entered


class DataTier(int, Enum):
    FIRST_PARTY = 1          # operator tender / customer's own PO  → HIGH trust
    VENDOR = 2               # vendor quote / market catalogue      → MEDIUM
    PUBLIC = 3               # scraped / public reference            → LOW


# ─── Tenancy & identity ──────────────────────────────────────────────────
class Tenant(SQLModel, table=True):
    __tablename__ = "tenant"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(index=True, unique=True)
    base_currency: str = Field(default="USD")
    is_reference: bool = Field(default=False)   # the shared NEPL benchmark library
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_email_per_tenant"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    email: str = Field(index=True)
    full_name: str = ""
    role: Role = Field(default=Role.VIEWER)
    password_hash: str = ""          # scrypt: salt$hash (never plaintext)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Escalation registry (KNOWLEDGE, not code) ───────────────────────────
class EscalationIndex(SQLModel, table=True):
    """Per-category inflation series. The engine picks the index by KEY from
    the category ontology — adding a new index is a DATA change, never code.
    `series` = {"2017": 199.91, ... "2024": 257.70}."""
    __tablename__ = "escalation_index"
    key: str = Field(primary_key=True)          # e.g. US_PPI_FG, STEEL, IT_HARDWARE, FUEL
    name: str
    description: str = ""
    source: str = ""                            # e.g. "US BLS WPUFD49207"
    ref_year: int = Field(default=2024)
    series: dict = Field(default_factory=dict, sa_column=Column(JSON))


# ─── Taxonomy ────────────────────────────────────────────────────────────
class Category(SQLModel, table=True):
    """Shared taxonomy — NOT tenant-scoped. A category is a classification
    label ("Pipeline > Construction > Lay & Weld", "Catering > Cutlery >
    Spoons") and carries no rates, vendors, or dollar amounts. There is
    exactly one global taxonomy, reused by every tenant — this is
    deliberate: sharing a classification scheme leaks nothing, and forcing
    every tenant to recreate an identical taxonomy tree would be pure waste.
    The tenant boundary belongs on Item and below, where real data lives."""
    __tablename__ = "category"
    __table_args__ = (UniqueConstraint("path", name="uq_category_path"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="category.id")
    name: str
    path: str = Field(index=True)               # "Pipeline > Construction > Lay & Weld"
    kind: str = ""                              # discipline / family / class
    escalation_index_key: Optional[str] = Field(default=None, foreign_key="escalation_index.key")
    default_data_tier: DataTier = Field(default=DataTier.FIRST_PARTY)


# ─── Item: the canonical benchmark line (any category) ───────────────────
class Item(SQLModel, table=True):
    """The tenant-private benchmark line. This is where the actual price
    data lives (via Observation) — so unlike Category, tenant_id here is
    NON-NULLABLE and enforced by a real DB constraint, not just app-level
    filtering. Two tenants can share a Category ("Lay & Weld") but will
    always get their OWN Item row and their OWN Benchmark — no cross-tenant
    blending is possible even if both submit an identically-named item."""
    __tablename__ = "item"
    __table_args__ = (
        UniqueConstraint("tenant_id", "category_id", "canonical_name", name="uq_item_tenant_cat_name"),
        Index("ix_item_tenant_cat", "tenant_id", "category_id"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    category_id: int = Field(foreign_key="category.id", index=True)
    canonical_name: str = Field(index=True)
    unit: str = "each"
    # Domain-specific spec bag — {"dia_in":6,"terrain":"Swamp"} OR {"material":"SS 18/10"}.
    # This JSON is why the table never forks per category.
    attributes: dict = Field(default_factory=dict, sa_column=Column(JSON))
    data_tier: DataTier = Field(default=DataTier.FIRST_PARTY)
    # Optional per-item override; else inherit category's escalation index.
    escalation_index_key: Optional[str] = Field(default=None, foreign_key="escalation_index.key")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Observation: one real price point (tender rate OR PO line) ──────────
class Observation(SQLModel, table=True):
    __tablename__ = "observation"
    __table_args__ = (
        Index("ix_obs_item_status", "item_id", "status"),
        Index("ix_obs_tenant_status", "tenant_id", "status"),
        # No standalone tenant_id/item_id/status indexes — both compound
        # indexes above already serve single-column lookups on their
        # leftmost column, so a separate single-column index would be pure
        # duplication (extra disk, slower writes, zero read benefit).
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id")
    item_id: int = Field(foreign_key="item.id")
    source_type: SourceType = Field(default=SourceType.MANUAL)
    source_ref: str = ""                        # doc name / PO number
    vendor: Optional[str] = None
    operator: Optional[str] = None
    currency: str = "USD"
    orig_rate: float = 0.0
    orig_year: int = 2024
    orig_date: Optional[date] = None
    qty: Optional[float] = None
    # spec as it was AT purchase — keeps the benchmark auditable if item specs drift.
    spec_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON))
    normalised_base: Optional[float] = None     # value in tenant base currency, ref-year real
    norm_method: str = ""
    confidence_flag: str = "OK"
    # Review queue — the C-1 fix: PENDING until an approver promotes it.
    status: ObsStatus = Field(default=ObsStatus.PENDING)
    submitted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    approved_by: Optional[int] = Field(default=None, foreign_key="user.id")
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Entity resolution / MDM (a subsystem, not a step) ───────────────────
class ItemAlias(SQLModel, table=True):
    """Collapses many raw descriptions onto one canonical Item.
    'tblspn 18/10', 'spoon, table, S/S', 'CUTLERY-TABLE-001' → one item.
    Low-score matches stay unconfirmed until a human confirms them."""
    __tablename__ = "item_alias"
    __table_args__ = (Index("ix_alias_tenant_norm", "tenant_id", "normalised_text"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    item_id: int = Field(foreign_key="item.id", index=True)
    raw_text: str
    normalised_text: str = Field(index=True)
    match_score: float = 1.0
    confirmed: bool = False
    confirmed_by: Optional[int] = Field(default=None, foreign_key="user.id")


# ─── Benchmark: materialised aggregate over APPROVED observations ────────
class Benchmark(SQLModel, table=True):
    """Mirrors Item's ownership exactly — a benchmark is always computed
    from one tenant's own approved observations for one tenant's own item.
    tenant_id is denormalised here (redundant with item.tenant_id) purely
    so benchmark reads don't need a join to enforce the tenant boundary."""
    __tablename__ = "benchmark"
    __table_args__ = (UniqueConstraint("item_id", name="uq_benchmark_item"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    item_id: int = Field(foreign_key="item.id", index=True)
    low: Optional[float] = None
    median: Optional[float] = None
    high: Optional[float] = None
    n_obs: int = 0
    confidence: str = "NONE"
    operators: list = Field(default_factory=list, sa_column=Column(JSON))
    year_range: str = ""
    computed_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Learning loop landing table (dormant — Phase 4+) ───────────────────
class ProcurementOutcome(SQLModel, table=True):
    """Where supplier-performance intelligence will land. Not wired into
    benchmarking yet — exists now so the learning loop needs no future
    migration. After an award closes: who won, final price, actual cost,
    schedule + overrun, quality."""
    __tablename__ = "procurement_outcome"
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    item_id: Optional[int] = Field(default=None, foreign_key="item.id")
    vendor: Optional[str] = None
    project_ref: str = ""
    awarded_price: Optional[float] = None
    final_actual_cost: Optional[float] = None
    schedule_delay_pct: Optional[float] = None
    cost_overrun_pct: Optional[float] = None
    quality_score: Optional[float] = None
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Audit trail (traceability — every mutation logged) ──────────────────
class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_tenant_time", "tenant_id", "created_at"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    action: str = ""                            # e.g. observation.submit, observation.approve
    entity_type: str = ""
    entity_id: Optional[str] = None
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
