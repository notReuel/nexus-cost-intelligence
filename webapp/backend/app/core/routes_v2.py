"""
Secured API (v2) — auth + tenancy + review queue.

Contrast with the legacy /api/observations/add (unauthenticated, direct write
to shared JSON — audit C-1/C-2). Everything here requires a token, is scoped
to the caller's tenant, and routes writes through the PENDING review queue.
"""
from typing import Optional
import os
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel import Session, select
from sqlalchemy import or_
from slowapi import Limiter
from slowapi.util import get_remote_address

from .db import get_session
from .models import (User, Item, Benchmark, Observation, Category, Tenant, ObsStatus, Role)
from .auth import (current_user, require_role, verify_password, issue_token)
from . import service

# Rate limits — configurable via env so production can tune without a code
# change. Defaults: login is the classic brute-force target and gets the
# strictest cap; writes get a generous-but-real cap; reads are unlimited
# (protected instead by auth + tenant scoping, not rate limiting).
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
RATE_LIMIT_WRITE = os.getenv("RATE_LIMIT_WRITE", "60/minute")

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/v2")


# ─── Auth ────────────────────────────────────────────────────────────────
class LoginBody(BaseModel):
    email: str
    password: str

@router.post("/auth/login")
@limiter.limit(RATE_LIMIT_LOGIN)
def login(request: Request, body: LoginBody, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email)).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return {"access_token": issue_token(user), "token_type": "bearer",
            "role": user.role.value, "tenant_id": user.tenant_id, "name": user.full_name}

@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "role": user.role.value,
            "tenant_id": user.tenant_id, "name": user.full_name}


# ─── Benchmarks (tenant-scoped read: own + shared reference) ─────────────
@router.get("/benchmarks")
def list_benchmarks(q: Optional[str] = None, confidence: Optional[str] = None,
                    limit: int = 50, offset: int = 0,
                    user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    # tenant scope: own items OR any reference-library tenant's items.
    # (Item.tenant_id is non-nullable now — "shared" is expressed via
    # Tenant.is_reference, not a NULL sentinel that nothing ever matched.)
    ref_tenant_ids = select(Tenant.id).where(Tenant.is_reference == True)  # noqa: E712
    stmt = select(Item, Benchmark).join(Benchmark, Benchmark.item_id == Item.id)
    stmt = stmt.where(or_(Item.tenant_id == user.tenant_id, Item.tenant_id.in_(ref_tenant_ids)))
    if q:
        stmt = stmt.where(Item.canonical_name.ilike(f"%{q}%"))
    if confidence:
        stmt = stmt.where(Benchmark.confidence == confidence.upper())
    rows = session.exec(stmt.offset(offset).limit(min(limit, 200))).all()
    return [{
        "item_id": it.id, "name": it.canonical_name, "unit": it.unit,
        "attributes": it.attributes, "data_tier": int(it.data_tier),
        "low": bm.low, "median": bm.median, "high": bm.high,
        "n_obs": bm.n_obs, "confidence": bm.confidence,
        "operators": bm.operators, "year_range": bm.year_range,
        "is_own": it.tenant_id == user.tenant_id,
    } for it, bm in rows]


# ─── Submit observation → review queue (ESTIMATOR+) ─────────────────────
class SubmitBody(BaseModel):
    category_path: str
    canonical_name: str
    unit: str = "each"
    attributes: dict = Field(default_factory=dict)
    source_type: str = "manual"
    vendor: Optional[str] = None
    operator: Optional[str] = None
    currency: str = "USD"
    orig_rate: float
    orig_year: int
    qty: Optional[float] = None
    notes: str = ""
    escalation_index_key: Optional[str] = None

@router.post("/observations")
@limiter.limit(RATE_LIMIT_WRITE)
def submit(request: Request, body: SubmitBody,
           user: User = Depends(require_role(Role.ESTIMATOR)),
           session: Session = Depends(get_session)):
    try:
        return service.submit_observation(session, user=user, **body.model_dump())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ─── Review queue (APPROVER+) ────────────────────────────────────────────
@router.get("/observations/pending")
def pending(limit: int = 50, offset: int = 0,
            user: User = Depends(require_role(Role.APPROVER)),
            session: Session = Depends(get_session)):
    obs = session.exec(
        select(Observation).where(Observation.tenant_id == user.tenant_id,
                                  Observation.status == ObsStatus.PENDING)
        .offset(offset).limit(min(limit, 200))
    ).all()
    return [{"id": o.id, "item_id": o.item_id, "operator": o.operator,
             "vendor": o.vendor, "currency": o.currency, "orig_rate": o.orig_rate,
             "orig_year": o.orig_year, "normalised_base": o.normalised_base,
             "submitted_by": o.submitted_by} for o in obs]

class ApproveBody(BaseModel):
    approve: bool = True

@router.post("/observations/{obs_id}/review")
@limiter.limit(RATE_LIMIT_WRITE)
def review(request: Request, obs_id: int, body: ApproveBody,
           user: User = Depends(require_role(Role.APPROVER)),
           session: Session = Depends(get_session)):
    try:
        return service.approve_observation(session, user=user,
                                           observation_id=obs_id, approve=body.approve)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


def register_v2(app):
    app.state.limiter = limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(router)
