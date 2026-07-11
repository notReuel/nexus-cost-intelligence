"""
Regression tests for the two critical cross-tenant bugs found in the Staff
Engineer review:
  1. Item/Category resolution leaked across tenants (write path).
  2. The shared reference library was invisible to every other tenant
     (read path, due to a tenant_id IS NULL check that nothing matched).
These are permanent guardrails — if either regresses, these must fail.
"""
from .conftest import login, SEED_USERS


def _submit(client, headers, category_path, canonical_name, rate, vendor):
    r = client.post("/api/v2/observations", headers=headers, json={
        "category_path": category_path, "canonical_name": canonical_name,
        "unit": "each", "currency": "USD", "orig_rate": rate, "orig_year": 2024,
        "vendor": vendor,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_cross_tenant_submissions_never_share_an_item(app_client):
    """Two different tenants submitting an identically-named item under an
    identical category must resolve to TWO DISTINCT items, never one."""
    est_h = login(app_client, *SEED_USERS["estimator"])   # tenant 2 (demo-op)
    adm_h = login(app_client, *SEED_USERS["admin"])        # tenant 1 (nepl-ref)

    same_cat, same_name = "RegressionTest > Widgets > Bolt", "M10 Hex Bolt"
    r1 = _submit(app_client, est_h, same_cat, same_name, 2.50, "TenantA-Vendor")
    r2 = _submit(app_client, adm_h, same_cat, same_name, 999.00, "TenantB-Vendor")

    assert r1["item_id"] != r2["item_id"], (
        "REGRESSION: two different tenants resolved to the same item_id — "
        "this is the exact cross-tenant collision from the Staff Engineer review."
    )


def test_approved_cross_tenant_data_does_not_blend_benchmarks(app_client):
    """After each tenant approves their own submission, tenant A's benchmark
    must reflect ONLY tenant A's data — no contamination from tenant B."""
    est_h = login(app_client, *SEED_USERS["estimator"])
    adm_h = login(app_client, *SEED_USERS["admin"])
    apr_h = login(app_client, *SEED_USERS["approver"])   # same tenant as estimator

    same_cat, same_name = "RegressionTest > Widgets > Bracket", "L-Bracket Steel"
    r1 = _submit(app_client, est_h, same_cat, same_name, 3.00, "TenantA-Vendor")
    r2 = _submit(app_client, adm_h, same_cat, same_name, 500.00, "TenantB-Vendor")

    a1 = app_client.post(f"/api/v2/observations/{r1['observation_id']}/review",
                         headers=apr_h, json={"approve": True})
    a2 = app_client.post(f"/api/v2/observations/{r2['observation_id']}/review",
                         headers=adm_h, json={"approve": True})
    assert a1.status_code == 200 and a2.status_code == 200

    bm = app_client.get("/api/v2/benchmarks", headers=est_h,
                        params={"q": "L-Bracket Steel"}).json()
    own = [b for b in bm if b["is_own"]]
    assert len(own) == 1, "expected exactly one own-tenant benchmark entry"
    assert own[0]["median"] == 3.00, (
        f"REGRESSION: tenant A's benchmark median is {own[0]['median']}, expected 3.00 — "
        "cross-tenant data has blended into it."
    )
    assert own[0]["n_obs"] == 1, "tenant A's item should have exactly 1 observation, not 2"


def test_shared_reference_library_is_visible_to_other_tenants(app_client):
    """The 440-observation reference dataset (seeded under the reference
    tenant) must be visible — read-only — to every other tenant. This was
    completely broken before the fix (0 results for any non-reference tenant)."""
    est_h = login(app_client, *SEED_USERS["estimator"])   # tenant 2, NOT the reference tenant

    bm = app_client.get("/api/v2/benchmarks", headers=est_h,
                        params={"q": "Lay & Weld"}).json()
    assert len(bm) > 0, (
        "REGRESSION: the demo tenant cannot see any reference-library benchmarks — "
        "this is the exact 'invisible product' bug from the Staff Engineer review."
    )
    assert all(b["is_own"] is False for b in bm), (
        "reference-library items should be labelled is_own=False for a non-reference tenant"
    )

    spdc_6in = next((b for b in bm if "6" in b["name"] and "Swamp" in b["name"]), None)
    assert spdc_6in is not None, "expected to find the SPDC 6-inch swamp lay&weld benchmark"
    assert spdc_6in["confidence"] == "HIGH"


def test_reference_library_full_count_reachable_via_pagination(app_client):
    """All 212 migrated reference benchmarks must be reachable (paginated),
    not silently truncated."""
    est_h = login(app_client, *SEED_USERS["estimator"])
    page1 = app_client.get("/api/v2/benchmarks", headers=est_h,
                           params={"limit": 200, "offset": 0}).json()
    page2 = app_client.get("/api/v2/benchmarks", headers=est_h,
                           params={"limit": 200, "offset": 200}).json()
    assert len(page1) + len(page2) == 212
