"""
Regression test for Phase 1/2: the estimating tools (Project Model / Budget)
must actually be connected to the live, governed data — not the frozen JSON
snapshot. This is the test that proves the platform's core promise
("submit real evidence, get better estimates") actually holds end to end.
"""
from sqlmodel import Session, select
from .conftest import login, SEED_USERS
from app.core.db import engine
from app.core.models import User


def test_anonymous_estimate_sees_only_reference_library(app_client):
    """Logged-out access must still work (public tools), and must reflect
    only the shared reference library — never require a login to function."""
    r = app_client.post("/api/model/project", json={
        "operator": "SPDC", "dia": 6, "terrain": "Swamp",
    })
    assert r.status_code == 200
    lw = next(l for l in r.json()["lines"] if l["description"].startswith("Lay & weld"))
    assert lw["rate_mid"] == 26.684
    assert lw["source"]["n_obs"] == 9


def test_approved_observation_changes_the_estimate(app_client):
    """The actual proof the loop is closed: submit a new observation as an
    estimator, approve it, and confirm the SAME project estimate — called
    again, logged in as that tenant — now reflects the new data. This is
    the test that would have failed before Phase 1/2: previously, approving
    new data had zero effect on what Project Model produced."""
    est_h = login(app_client, *SEED_USERS["estimator"])
    apr_h = login(app_client, *SEED_USERS["approver"])

    # Baseline: logged-in estimate BEFORE adding anything new.
    r_before = app_client.post("/api/model/project", headers=est_h, json={
        "operator": "SPDC", "dia": 6, "terrain": "Swamp",
    })
    lw_before = next(l for l in r_before.json()["lines"] if l["description"].startswith("Lay & weld"))
    n_before = lw_before["source"]["n_obs"]

    # Submit a new SPDC lay & weld observation, tenant-private.
    sub = app_client.post("/api/v2/observations", headers=est_h, json={
        "category_path": "Pipeline > Construction > Lay & Weld (arc)",
        "canonical_name": "Lay & Weld 6\" Swamp",
        "unit": "m", "attributes": {"dia_in": 6, "terrain": "Swamp"},
        "source_type": "manual", "operator": "SPDC",
        "currency": "USD", "orig_rate": 50.00, "orig_year": 2024,
    })
    assert sub.status_code == 200, sub.text
    obs_id = sub.json()["observation_id"]

    # Confirm it has NOT changed the estimate yet — it's still PENDING.
    r_pending = app_client.post("/api/model/project", headers=est_h, json={
        "operator": "SPDC", "dia": 6, "terrain": "Swamp",
    })
    lw_pending = next(l for l in r_pending.json()["lines"] if l["description"].startswith("Lay & weld"))
    assert lw_pending["source"]["n_obs"] == n_before, (
        "REGRESSION: a PENDING (unapproved) observation affected the estimate — "
        "this would violate the governance invariant."
    )

    # Approve it.
    appr = app_client.post(f"/api/v2/observations/{obs_id}/review", headers=apr_h, json={"approve": True})
    assert appr.status_code == 200

    # THE PROOF: the same estimate, called again, must now reflect it.
    r_after = app_client.post("/api/model/project", headers=est_h, json={
        "operator": "SPDC", "dia": 6, "terrain": "Swamp",
    })
    lw_after = next(l for l in r_after.json()["lines"] if l["description"].startswith("Lay & weld"))
    assert lw_after["source"]["n_obs"] == n_before + 1, (
        "REGRESSION: approving a new observation did not change the estimate — "
        "the estimating tools are still disconnected from live data."
    )

    # And an ANONYMOUS caller must NOT see this tenant-private observation.
    r_anon = app_client.post("/api/model/project", json={
        "operator": "SPDC", "dia": 6, "terrain": "Swamp",
    })
    lw_anon = next(l for l in r_anon.json()["lines"] if l["description"].startswith("Lay & weld"))
    assert lw_anon["source"]["n_obs"] == n_before, (
        "REGRESSION: an anonymous caller saw another tenant's private observation."
    )


def test_invalid_token_is_rejected_not_silently_downgraded(app_client):
    """A present-but-invalid token on the public estimating endpoints must
    still be rejected (401) — 'no auth' and 'bad auth' are different things,
    and a tampered token must never silently fall back to anonymous access."""
    r = app_client.post("/api/model/project",
                        headers={"Authorization": "Bearer garbage.not.a.jwt"},
                        json={"operator": "SPDC", "dia": 6, "terrain": "Swamp"})
    assert r.status_code == 401
