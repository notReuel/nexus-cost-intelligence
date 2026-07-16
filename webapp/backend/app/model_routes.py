"""
v5 route registration — Project Modeller, Line-item Budget.

Registered on BOTH the combined server (serve.py) and the Railway app
(main.py) so the API contract is identical wherever the backend runs.
Must be registered BEFORE any SPA catch-all route.

NOTE: the legacy `/api/observations/add` (unauthenticated write) and
`/api/observations/summary` routes that used to live here have been
REMOVED (Enterprise Validation sprint, item 2). Observation submission and
review now go exclusively through the secured `/api/v2/*` routes in
`app/core/routes_v2.py` — authenticated, tenant-scoped, and gated behind
the PENDING → APPROVED review queue.

Phase 1/2 (connect the estimating tools to live data): these routes stay
public — no login required — but now optionally accept a bearer token. No
token -> the estimate is built from the shared reference library only
(the same thing a logged-out visitor always saw). A valid token -> the
caller's own tenant's approved data is blended in, same rule already used
by GET /api/v2/benchmarks. An invalid/expired token is still rejected —
"no auth" and "bad auth" are different things.
"""
from fastapi import HTTPException, Depends
from sqlmodel import Session
from typing import Optional

from app.engine.project_modeller import ProjectScope, model_project
from app.core.db import get_session
from app.core.auth import optional_current_user
from app.core.models import User


def register_model_routes(app):

    @app.post('/api/model/project')
    def model_project_endpoint(scope: ProjectScope,
                               session: Session = Depends(get_session),
                               user: Optional[User] = Depends(optional_current_user)):
        """13-input project scope → catalogue-backed BOQ + rolling estimate.
        Public; richer if a valid token is supplied (Phase 1/2)."""
        try:
            tenant_id = user.tenant_id if user else None
            return model_project(scope, session=session, caller_tenant_id=tenant_id).model_dump()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Modeller failed: {type(e).__name__}: {e}")

    # Alias — the Line-item Budget page consumes the same modelled scope.
    @app.post('/api/model/generate-budget')
    def generate_budget_endpoint(scope: ProjectScope,
                                 session: Session = Depends(get_session),
                                 user: Optional[User] = Depends(optional_current_user)):
        try:
            tenant_id = user.tenant_id if user else None
            return model_project(scope, session=session, caller_tenant_id=tenant_id).model_dump()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Budget generation failed: {type(e).__name__}: {e}")
