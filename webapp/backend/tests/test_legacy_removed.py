"""
Regression test: the legacy unauthenticated write path must stay removed.
If this ever starts passing with a 200/307, someone re-added the route.
"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.core.routes_v2 import register_v2
from app.model_routes import register_model_routes


def test_legacy_observations_add_route_does_not_exist():
    app = FastAPI()
    register_model_routes(app)
    register_v2(app)
    with TestClient(app) as client:
        r = client.post("/api/observations/add", data={})
        assert r.status_code == 404, (
            "REGRESSION: /api/observations/add exists again — this is the "
            "unauthenticated legacy write path that was deliberately removed."
        )


def test_legacy_observations_summary_route_does_not_exist():
    app = FastAPI()
    register_model_routes(app)
    register_v2(app)
    with TestClient(app) as client:
        r = client.get("/api/observations/summary")
        assert r.status_code == 404
