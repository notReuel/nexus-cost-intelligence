"""
Regression tests for concurrency races found across two review passes:
  1. Concurrent first-submission of a brand-new item must NOT fragment into
     duplicate Item rows (the UniqueConstraint + SAVEPOINT-retry fix).
  2. Concurrent approval of the same observation must serialize to exactly
     one winner (the atomic conditional UPDATE fix).
Uses real threads against the shared TestClient/engine — this exercises the
actual DB-level transaction isolation, which is what these fixes protect.
"""
import concurrent.futures as cf
from .conftest import login, SEED_USERS


def test_concurrent_new_item_submission_does_not_fragment(app_client):
    """20 threads submit an identical brand-new item at once. All must
    succeed, and all must resolve to exactly ONE item_id."""
    headers = login(app_client, *SEED_USERS["estimator"])

    def submit(i):
        r = app_client.post("/api/v2/observations", headers=headers, json={
            "category_path": "ConcurrencyTest > Race > NewWidget",
            "canonical_name": "Never Seen Before Widget",
            "unit": "each", "currency": "USD",
            "orig_rate": 1.0 + i * 0.001, "orig_year": 2024,
        })
        return r.json()

    with cf.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(submit, range(20)))

    item_ids = {r.get("item_id") for r in results if "item_id" in r}
    obs_ids = [r.get("observation_id") for r in results if "observation_id" in r]

    assert len(obs_ids) == 20, "all 20 concurrent submissions should succeed"
    assert len(item_ids) == 1, (
        f"REGRESSION: {len(item_ids)} distinct items created from one concurrent "
        "first-submission race — the unique constraint / retry logic is not holding."
    )


def test_concurrent_approval_of_same_observation_has_exactly_one_winner(app_client):
    """10 threads race to approve the SAME observation. Exactly one must
    succeed (200); the rest must be cleanly rejected (404), not silently
    duplicate the approval or corrupt the audit trail."""
    est_h = login(app_client, *SEED_USERS["estimator"])
    apr_h = login(app_client, *SEED_USERS["approver"])

    sub = app_client.post("/api/v2/observations", headers=est_h, json={
        "category_path": "ConcurrencyTest > Race > ApproveMe",
        "canonical_name": "Race Test Item",
        "unit": "each", "currency": "USD", "orig_rate": 5.0, "orig_year": 2024,
    }).json()
    obs_id = sub["observation_id"]

    def approve(_):
        r = app_client.post(f"/api/v2/observations/{obs_id}/review",
                            headers=apr_h, json={"approve": True})
        return r.status_code

    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(approve, range(10)))

    succeeded = sum(1 for r in results if r == 200)
    rejected = sum(1 for r in results if r == 404)

    assert succeeded == 1, (
        f"REGRESSION: {succeeded} concurrent approvals succeeded, expected exactly 1 — "
        "the atomic conditional UPDATE is not serializing the race."
    )
    assert rejected == 9, f"expected 9 clean rejections, got {rejected}"
