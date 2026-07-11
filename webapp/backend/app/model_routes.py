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
the PENDING → APPROVED review queue. The frontend's Data Entry page was
migrated to that flow first; this removal was verified safe only after
confirming zero remaining frontend references to the legacy endpoints.
"""
from fastapi import HTTPException

from app.engine.project_modeller import ProjectScope, model_project


def register_model_routes(app):

    @app.post('/api/model/project')
    def model_project_endpoint(scope: ProjectScope):
        """13-input project scope → catalogue-backed BOQ + rolling estimate."""
        try:
            return model_project(scope).model_dump()
        except Exception as e:
            raise HTTPException(500, f"Modeller failed: {type(e).__name__}: {e}")

    # Alias — the Line-item Budget page consumes the same modelled scope.
    @app.post('/api/model/generate-budget')
    def generate_budget_endpoint(scope: ProjectScope):
        try:
            return model_project(scope).model_dump()
        except Exception as e:
            raise HTTPException(500, f"Budget generation failed: {type(e).__name__}: {e}")
