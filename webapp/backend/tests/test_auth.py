"""
Regression tests for the baseline auth/authorization findings from the
original security audit (C-1, IDOR, role enforcement).
"""
from .conftest import login, SEED_USERS


def test_unauthenticated_submit_is_rejected(app_client):
    r = app_client.post("/api/v2/observations", json={
        "category_path": "x", "canonical_name": "y",
        "orig_rate": 1, "orig_year": 2023,
    })
    assert r.status_code == 401


def test_wrong_password_is_rejected(app_client):
    r = app_client.post("/api/v2/auth/login",
                        json={"email": "estimator@demo.io", "password": "wrong"})
    assert r.status_code == 401


def test_malformed_token_is_rejected(app_client):
    r = app_client.get("/api/v2/auth/me",
                       headers={"Authorization": "Bearer garbage.not.a.jwt"})
    assert r.status_code == 401


def test_estimator_cannot_approve(app_client):
    est_h = login(app_client, *SEED_USERS["estimator"])
    sub = app_client.post("/api/v2/observations", headers=est_h, json={
        "category_path": "AuthTest > X", "canonical_name": "Item",
        "unit": "each", "currency": "USD", "orig_rate": 1.0, "orig_year": 2024,
    }).json()
    r = app_client.post(f"/api/v2/observations/{sub['observation_id']}/review",
                        headers=est_h, json={"approve": True})
    assert r.status_code == 403


def test_cross_tenant_approve_is_rejected_not_leaked(app_client):
    """An admin from a DIFFERENT tenant cannot approve another tenant's
    pending observation — must be a clean 404, not a silent success."""
    est_h = login(app_client, *SEED_USERS["estimator"])   # tenant 2
    adm_h = login(app_client, *SEED_USERS["admin"])        # tenant 1 (different tenant)

    sub = app_client.post("/api/v2/observations", headers=est_h, json={
        "category_path": "AuthTest > IDOR", "canonical_name": "IDOR Item",
        "unit": "each", "currency": "USD", "orig_rate": 1.0, "orig_year": 2024,
    }).json()
    r = app_client.post(f"/api/v2/observations/{sub['observation_id']}/review",
                        headers=adm_h, json={"approve": True})
    assert r.status_code == 404


def test_pending_submission_does_not_affect_benchmark_until_approved(app_client):
    est_h = login(app_client, *SEED_USERS["estimator"])
    app_client.post("/api/v2/observations", headers=est_h, json={
        "category_path": "AuthTest > Pending", "canonical_name": "Pending Item",
        "unit": "each", "currency": "USD", "orig_rate": 1.0, "orig_year": 2024,
    })
    bm = app_client.get("/api/v2/benchmarks", headers=est_h,
                        params={"q": "Pending Item"}).json()
    assert len(bm) == 0, "an unapproved submission must not appear as a live benchmark"
