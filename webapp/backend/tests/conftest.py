"""
Shared pytest fixtures — an isolated, disposable DB per test, seeded fresh
each time. Nothing here touches the real dev/prod nexus.db.

Design note: app.core.models is imported exactly ONCE per test session
(session-scoped DB setup). Re-importing SQLModel/SQLAlchemy model modules
mid-process breaks the declarative class registry, so isolation between
tests is achieved by wiping and re-migrating the SAME temp SQLite file
between tests, not by reloading Python modules.
"""
import os
import sys
import tempfile
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ["JWT_SECRET"] = "pytest-fixed-secret"

from app.core.migrate import run_migration  # noqa: E402
from app.core.db import engine  # noqa: E402
from app.core import models as m  # noqa: E402


@pytest.fixture()
def app_client():
    """Wipe + re-migrate + re-seed the shared temp DB, then hand back a
    fresh TestClient. Each test starts from the identical clean state."""
    run_migration(reset=True)

    from fastapi import FastAPI
    from app.core.routes_v2 import register_v2, limiter
    # The rate limiter is a module-level singleton (its decorators are bound
    # at import time), so its hit-counters persist across tests unless reset
    # here — same reasoning as the DB wipe above, applied to a different
    # piece of shared state.
    limiter.reset()

    app = FastAPI()
    register_v2(app)

    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        yield client


def login(client, email, password):
    r = client.post("/api/v2/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


SEED_USERS = {
    "estimator": ("estimator@demo.io", "changeme-estimator"),   # tenant_id=2 (demo-op)
    "approver":  ("approver@demo.io", "changeme-approver"),     # tenant_id=2 (demo-op)
    "admin":     ("admin@nepl.io", "changeme-admin"),           # tenant_id=1 (nepl-ref)
}


def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_TMP_DB.name)
    except OSError:
        pass
