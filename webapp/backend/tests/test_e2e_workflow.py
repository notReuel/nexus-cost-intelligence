"""
End-to-end workflow validation (Enterprise Validation sprint, item 1).

Walks the full lifecycle — Login → Submit → Pending → Approver Review →
Approval → Benchmark Rebuild → Benchmark Visible → Audit Log Recorded —
using ONLY /api/v2/* routes, and asserts each stage explicitly rather than
just checking the final state, so a regression at any single stage fails
at that stage, not just at the end.
"""
from sqlmodel import select
from .conftest import login, SEED_USERS
from app.core.models import AuditLog, Observation, ObsStatus, Benchmark, Item
from app.core.db import engine
from sqlmodel import Session


def test_full_lifecycle_via_v2_only(app_client):
    # ── Stage 1: Login ──────────────────────────────────────────────
    est_email, est_pw = SEED_USERS["estimator"]
    r = app_client.post("/api/v2/auth/login", json={"email": est_email, "password": est_pw})
    assert r.status_code == 200, "Stage 1 (Login) failed"
    est_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    apr_email, apr_pw = SEED_USERS["approver"]
    r = app_client.post("/api/v2/auth/login", json={"email": apr_email, "password": apr_pw})
    assert r.status_code == 200
    apr_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ── Stage 2: Submit Observation ─────────────────────────────────
    r = app_client.post("/api/v2/observations", headers=est_h, json={
        "category_path": "E2ETest > Workflow > Widget",
        "canonical_name": "E2E Workflow Widget",
        "unit": "each", "currency": "USD",
        "orig_rate": 42.50, "orig_year": 2024,
        "vendor": "E2E-Vendor", "operator": "SPDC",
    })
    assert r.status_code == 200, "Stage 2 (Submit) failed"
    sub = r.json()
    obs_id = sub["observation_id"]
    assert sub["status"] == "pending", "Stage 2: submission did not land as pending"

    # ── Stage 3: Pending Review (visible in the approver's queue) ───
    r = app_client.get("/api/v2/observations/pending", headers=apr_h)
    assert r.status_code == 200, "Stage 3 (Pending Review) failed"
    pending_ids = [o["id"] for o in r.json()]
    assert obs_id in pending_ids, "Stage 3: submitted observation not visible in review queue"

    # Also verify directly against the DB that the benchmark does NOT exist yet.
    with Session(engine) as s:
        item_id = sub["item_id"]
        bm_before = s.exec(select(Benchmark).where(Benchmark.item_id == item_id)).first()
        assert bm_before is None, "Stage 3: a benchmark must not exist before approval"

    # ── Stage 4: Approver Review + Stage 5: Approval ────────────────
    r = app_client.post(f"/api/v2/observations/{obs_id}/review", headers=apr_h, json={"approve": True})
    assert r.status_code == 200, "Stage 4/5 (Approver Review / Approval) failed"
    assert r.json()["status"] == "approved"

    # Confirm the observation's DB row actually flipped to APPROVED with the right approver.
    with Session(engine) as s:
        obs_row = s.get(Observation, obs_id)
        assert obs_row.status == ObsStatus.APPROVED, "Stage 5: observation not marked approved in DB"
        assert obs_row.approved_by is not None, "Stage 5: approved_by not recorded"

    # ── Stage 6: Benchmark Rebuild ───────────────────────────────────
    with Session(engine) as s:
        bm = s.exec(select(Benchmark).where(Benchmark.item_id == item_id)).first()
        assert bm is not None, "Stage 6 (Benchmark Rebuild) failed — no benchmark row created"
        assert bm.median == 42.50, f"Stage 6: benchmark median is {bm.median}, expected 42.50"
        assert bm.n_obs == 1
        assert bm.confidence == "LOW"  # n=1

    # ── Stage 7: Benchmark Visible (via the API, not just the DB) ───
    r = app_client.get("/api/v2/benchmarks", headers=est_h, params={"q": "E2E Workflow Widget"})
    assert r.status_code == 200, "Stage 7 (Benchmark Visible) failed"
    results = r.json()
    assert len(results) == 1, "Stage 7: benchmark not visible via the API"
    assert results[0]["median"] == 42.50
    assert results[0]["is_own"] is True

    # ── Stage 8: Audit Log Recorded ──────────────────────────────────
    with Session(engine) as s:
        logs = s.exec(
            select(AuditLog).where(AuditLog.entity_type == "observation",
                                   AuditLog.entity_id == str(obs_id))
        ).all()
        actions = sorted(l.action for l in logs)
        assert actions == ["observation.approve", "observation.submit"], (
            f"Stage 8 (Audit Log) failed — expected submit+approve entries, got {actions}"
        )
        submit_log = next(l for l in logs if l.action == "observation.submit")
        assert submit_log.user_id is not None, "Stage 8: audit log missing submitter user_id"
        approve_log = next(l for l in logs if l.action == "observation.approve")
        assert approve_log.user_id is not None, "Stage 8: audit log missing approver user_id"

    # ── Confirm every stage used ONLY /api/v2/* — no legacy route touched ──
    # (This is structural: the test file itself never calls any non-/v2/ path.
    # Cross-checked against api.js in the frontend migration — zero references.)
