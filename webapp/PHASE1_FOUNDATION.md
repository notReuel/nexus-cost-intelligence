# NEPL NEXUS — Phase 1 Foundation (Cost Intelligence Platform core)

The migration from JSON-files-as-database to a tenant-scoped relational core.
One build that (a) makes "engine vs knowledge" literal, (b) gives every module
the same spine, and (c) closes audit findings C-1 and C-2.

## What was built (`app/core/`)

- `models.py` — the category-agnostic schema. A 6" swamp lay & weld rate and a
  stainless tablespoon PO line are the SAME row in `observation`; only the JSON
  `attributes`/`spec_snapshot` and `category` differ. Tables: tenant, user,
  escalation_index, category, item, observation, item_alias, benchmark,
  procurement_outcome (dormant learning loop), audit_log.
- `db.py` — SQLite (WAL + busy_timeout) for pilot; same code runs on Postgres
  via `DATABASE_URL`. Transactions replace the non-atomic JSON writes (C-2).
- `auth.py` — scrypt password hashing (stdlib, no fragile native deps), JWT
  sessions, `require_role()` and `tenant_scope()` guards (C-1).
- `escalation.py` — the per-category index registry as DATA, not an if-ladder.
  `normalise()` picks the index by category key. Seeded: US_PPI_FG (reproduces
  the 440-obs factors exactly), CBN FX, plus STEEL / IT_HARDWARE / FUEL to prove
  multi-category escalation.
- `service.py` — transactional submit→queue and approve→rebuild, with input
  validation (H-1) and audit logging.
- `routes_v2.py` — `/api/v2/*`: login, tenant-scoped benchmark reads, role-gated
  submit, approver review queue.
- `migrate.py` — ports all 440 JSON observations into the reference tenant as
  APPROVED, rebuilds items + benchmarks. Runs automatically on startup if the DB
  is empty (self-seeds on Railway's ephemeral FS).

## Verified (all passing) — including a second, adversarial verification pass

Data integrity:
- 440 observations migrated → 212 items, 212 benchmarks.
- Anchors reproduce exactly: SPDC 2017 → $26.68/m, Seplat 2023 NGN → $20.26/m.
- Multi-index proof: $1,000 laptop (2021) → $952 on IT index (correctly
  deflationary) vs $1,166 if wrongly escalated on oil PPI.
- Legacy `estimate_pipeline` calibration untouched: default = $870,175.
- **Found on recheck, not a bug:** 60 of 440 original JSON observations (all
  ARAHAS/NNPC OML11, 2025, USD) had `usd_2024 = orig_rate` — i.e. no PPI
  de-escalation applied — while the other 37 ARAHAS 2025 rows correctly had
  the 0.9798 factor. This was a **pre-existing inconsistency in the original
  dataset**, not introduced by this migration. The new engine applies the
  documented factor uniformly to all 97, which shifts those 60 values by
  ~2%. SPDC and Seplat benchmarks are entirely unaffected (only ARAHAS had
  2025 data). Net effect: the migration *fixes* a latent data inconsistency
  rather than introducing one — but it does mean 60 values changed, and that
  should be disclosed, not glossed over.

Security (C-1 / C-2):
- Unauthenticated submit → 401. Wrong password → 401. Malformed/garbage
  token → 401. Missing token → 401.
- Estimator can submit but CANNOT approve → 403.
- IDOR/cross-tenant check: an admin from a *different* tenant cannot approve
  another tenant's observation → 404 (not a silent no-op, not a data leak).
- Tenant isolation confirmed on reads: a user cannot see another tenant's
  private items in `/api/v2/benchmarks`.
- A pending submission does NOT affect any benchmark until an approver
  promotes it.
- 20 concurrent submits (threaded) → all succeed, all IDs unique.
- **60 concurrent submits across 4 real uvicorn WORKER PROCESSES** (not just
  threads in one process) → all succeed, all IDs unique, once `JWT_SECRET`
  is fixed (see finding below). This is the harder, more realistic test and
  it passes.
- SQL-injection-shaped query string handled safely (parameterized queries).

### Two real issues found on this recheck, both now fixed

1. **JWT_SECRET random-per-process default breaks auth under >1 worker.**
   With `uvicorn --workers 4` and no `JWT_SECRET` env var, each worker process
   generated its own random secret, so a token issued by whichever worker
   handled `/login` was rejected by the other three — 51 of 60 requests
   failed with "Invalid or expired token" in testing, purely as a function of
   which worker the load balancer picked. This is **worse than the original
   note said** ("tokens don't survive restart") — it breaks auth *within a
   single running deployment*, no restart required, the moment more than one
   worker process exists. Fixed: the code now logs a loud warning if
   `JWT_SECRET` isn't set, naming the exact failure mode. **`JWT_SECRET` must
   be set explicitly before running with more than one worker/instance.**
   Confirmed fixed: 60/60 concurrent requests across 4 real worker processes
   succeed with a fixed secret.

2. **Double-approval race on `/api/v2/observations/{id}/review`.** The
   original `approve_observation` did read-check-then-write (load the row,
   check `status == PENDING`, then set `APPROVED`), which is not atomic. 10
   concurrent approve calls on the same observation resulted in 5 "successes"
   instead of 1 — the observation's final state was still correct
   (`APPROVED`, correct `approved_by`) and the benchmark rebuild is
   idempotent so no benchmark corruption occurred, but the audit log recorded
   5 duplicate `observation.approve` entries for one logical action, which
   undermines the traceability the audit log exists for. **Fixed**: replaced
   with an atomic conditional `UPDATE ... WHERE status = 'pending'`; only the
   first caller's update affects a row, all others get 0 rows affected and
   are cleanly rejected. Re-tested after the fix.

Both were caught only because this response was explicitly re-verified with
adversarial, multi-process tests rather than re-trusting the original
single-process test run — worth keeping this level of scrutiny for anything
security-relevant going forward.


## Seed credentials (change before any real pilot)
- `admin@nepl.io` / `changeme-admin` (reference tenant, admin)
- `estimator@demo.io` / `changeme-estimator` (demo tenant, estimator)
- `approver@demo.io` / `changeme-approver` (demo tenant, approver)

## Deploy notes
- New deps in `requirements.txt`: `sqlmodel`, `PyJWT` (ranges, not hard pins —
  avoids the resolver conflicts that hard pins caused). Without these Railway
  fails at import, same class as the earlier openpyxl miss.
- Set `JWT_SECRET` and `DATABASE_URL` (Postgres) env vars for production. Default
  JWT secret is per-boot random (fine for demo, tokens don't survive restart).
- For durable data, point `DATABASE_URL` at a managed Postgres — SQLite on
  Railway is ephemeral (re-seeds each cold start from the JSON).

## NOT done this phase — the honest next steps
1. **Frontend still uses the legacy unauthenticated `/api/observations/add`.**
   The secure replacement (`/api/v2/observations` + review queue) is built and
   tested, but the Data Entry page hasn't been migrated to log in + submit to the
   queue. Until it is, the legacy write path remains open — so **disable
   `/api/observations/add` the moment the UI moves to v2**, to fully close C-1 in
   the live product. (Backend foundation is done; UI wiring is the next build.)
2. Login screen + token storage + role-aware nav in the frontend.
3. Entity-resolution / MDM subsystem (fuzzy `item_alias` matching + human
   confirmation) — the genuinely hard part of general-procurement expansion.
4. Bulk PO/CSV ingestion for internal procurement (builds on `boq_parser`).
5. The remaining audit quick-wins (bid-comparison size limit, error hygiene,
   CORS fail-closed, a11y label association, nested-tbody fix).
6. Wire the learning-loop `procurement_outcome` table into scoring (Phase 4+).

---

## Sprint 2 — tenant-scoping fixes, Alembic, automated tests

Following an adversarial Staff Engineer review, two critical, live-reproduced
bugs were found in Phase 1's tenant model, and the review's full sprint
recommendation was executed to close them permanently.

### The bugs (both found and fixed this sprint)

1. **Cross-tenant item/category collision.** `_resolve_item`'s lookups had
   no `tenant_id` filter at all — two different tenants submitting an
   identically-named item under an identical category resolved to the SAME
   `Item` row, and after each approved their own submission independently
   (no auth bypass needed), one tenant's benchmark silently blended with
   the other's data. Reproduced live: two tenants both got `item_id=213`;
   tenant A's benchmark median jumped from an expected $2.50 to $500.75.
2. **Shared reference library was invisible to every other tenant.** The
   read query checked `Item.tenant_id IS NULL` for "shared," but the
   migration seeded all 212 reference items with a real tenant id — the
   `IS NULL` branch never matched anything. Reproduced live: the demo
   tenant's benchmark search for "Lay & Weld" returned 0 results.

### The fix — a real design decision, not a patch

**Category is shared global taxonomy** ("Pipeline > Construction > Lay &
Weld") — it carries no rates, vendors, or dollar amounts, so sharing it
leaks nothing, and forcing every tenant to recreate an identical taxonomy
tree would be pure waste. `Category.tenant_id` was removed entirely;
`UniqueConstraint(path)` makes it a single global dictionary.

**Item (and Benchmark) are strictly tenant-private** — this is where real
data lives. `Item.tenant_id` is now non-nullable and enforced by
`UniqueConstraint(tenant_id, category_id, canonical_name)`. Two tenants can
share a Category but will always get their own Item and Benchmark rows.
`Benchmark.tenant_id` was likewise made non-nullable to match.

**Shared-library visibility** now uses `Tenant.is_reference` (which existed
on the model but was previously unused) instead of a `NULL` sentinel that
nothing matched. `/api/v2/benchmarks` returns a tenant's own items plus any
reference-tenant's items, each labelled `is_own: true/false` so the UI can
distinguish them.

### Concurrency: the same fix pattern closes a related race

The find-or-create pattern in `_resolve_item` was also vulnerable to a
plain duplicate-row race (two concurrent submissions of a genuinely new
item, same tenant, could both miss the SELECT and both INSERT). Fixed with
`session.begin_nested()` (a SAVEPOINT) around each insert attempt — a
concurrent loser's `IntegrityError` is caught and the row is re-fetched
instead of erroring. Verified: 20 concurrent submissions of a brand-new
item all succeed and converge on exactly one `item_id`.

### Alembic — schema is now versioned, not `create_all()`-only

`app/core/migrations/` holds a real Alembic environment, wired to
`app.core.db.DATABASE_URL` and `SQLModel.metadata` (autogenerate actually
sees our models). The initial migration (`40aa6983cc54`) captures the
corrected schema, including both new unique constraints. App startup now
calls `run_alembic_upgrade()` (`alembic upgrade head` via the Python API),
not `create_all()` — future schema changes ship as a new migration file,
not a silent no-op against an already-existing table.
`app/core/db.py::init_db()` still exists as an explicit dev/test-only
escape hatch, clearly documented as such.

One non-obvious fix required along the way: resetting the DB for tests via
`drop_all()` doesn't touch Alembic's own `alembic_version` bookkeeping
table (it isn't part of `SQLModel.metadata`) — left alone, Alembic sees
"already at head" on the next upgrade and skips recreating the tables that
were just dropped. `run_migration(reset=True)` now explicitly drops
`alembic_version` too, and disposes the pooled engine's connections after
schema changes so they don't serve a stale cached view of the schema.

### Automated tests — 13 tests, all passing, permanent regression guardrails

`tests/` (pytest + FastAPI TestClient, isolated temp SQLite DB per test):
- `test_multitenancy.py` (4) — the exact cross-tenant collision repro, the
  benchmark-contamination-after-approval check, the shared-library
  visibility check, and full-count pagination.
- `test_concurrency.py` (2) — the duplicate-row race (20 concurrent new-item
  submissions → 1 item) and the double-approval race (10 concurrent
  approvals of one observation → exactly 1 winner, 9 clean 404s).
- `test_auth.py` (6) — unauthenticated/malformed-token/wrong-password
  rejection, role enforcement, cross-tenant IDOR on approve, and the
  pending-does-not-affect-benchmark invariant.
- `test_calibration.py` (1) — the $870,175 EGWA-2 anchor, now a real test
  instead of a manually re-run assertion.

Run with `pytest tests/ -v` from `webapp/backend` (requires
`requirements-dev.txt`).

### Also fixed this sprint (smaller review findings)
- `/api/v2/observations/pending` now paginated (`limit`/`offset`), was
  unbounded.
- `requirements.txt` now includes `alembic` (a genuine runtime dependency,
  not dev-only, since the app calls it at startup).

### Still explicitly NOT done — deferred, not forgotten
- **Legacy endpoint removal** (`POST /api/observations/add`, unauthenticated)
  — deliberately deferred until the frontend is migrated to `/api/v2/*`.
  Removing it first would break the only working write path the product
  currently has; removing it without migrating first was flagged in review
  as the wrong order of operations. This is now the single largest
  remaining gap between "the backend is secure" and "the product is secure."
- CORS wildcard (`serve.py`), rate limiting, and the duplicated
  PPI/escalation constants (legacy `normalizer_fx.py` vs `core/escalation.py`)
  — all still open, tracked from the prior review, not addressed this
  sprint (scope was tenant-scoping + Alembic + tests per the agreed plan).

---

## Sprint 3 — Tier 1 pilot blockers closed: CORS lockdown + rate limiting

Following the Enterprise Validation sprint's recommendation ("Ready for
pilot" pending these two items), both Tier 1 blockers are now closed.

### CORS lockdown

- `serve.py`: `allow_origins=["*"]` replaced with an `ALLOWED_ORIGINS` env var
  (comma-separated), defaulting to localhost-only dev origins with a loud
  startup warning if unset — never silently wide open.
- `app/main.py`: fixed a worse-than-wildcard bug — the previous config
  combined `ALLOWED_ORIGINS` (defaulting to `"*"`) with `allow_credentials=
  True`. Starlette's CORS middleware resolves that combination by reflecting
  back whatever `Origin` header the request sent, effectively allowing any
  origin *with* credentials attached — strictly worse than a plain wildcard.
  Fixed to the same env-driven allow-list, and `allow_credentials` set to
  `False` throughout (the API uses Bearer tokens in the `Authorization`
  header, not cookies, so credentialed CORS was never actually needed).
- Verified live against a real server: an unlisted origin (`evil.com`)
  receives no `Access-Control-Allow-Origin` header; an explicitly allowed
  origin does.

### Rate limiting

- Added via `slowapi`, keyed on client address. `POST /api/v2/auth/login`
  capped at `RATE_LIMIT_LOGIN` (default `10/minute`) — the classic
  brute-force target. `POST /api/v2/observations` and
  `POST /api/v2/observations/{id}/review` capped at `RATE_LIMIT_WRITE`
  (default `60/minute`). Both configurable via env var without a code
  change. Reads (`/benchmarks`, `/observations/pending`) are intentionally
  left unlimited — protected by auth + tenant scoping, not rate limiting.
- The limiter is a module-level object (`slowapi`'s `@limiter.limit(...)`
  decorators bind to a specific `Limiter` instance at import time, so it
  can't be recreated fresh per request the way the DB session is) — the
  test fixture explicitly calls `limiter.reset()` between tests to prevent
  hit-counters leaking across the suite, the same reasoning previously
  applied to the DB wipe-and-reseed pattern.
- Verified against a **real running server**, not just `TestClient`: 10
  rapid logins succeed, the 11th returns `429` with a clean, non-leaking
  body (`{"error":"Rate limit exceeded: 10 per 1 minute"}`); reads and the
  legacy compute-only endpoints are correctly unaffected.
- Two new permanent regression tests confirm the limiter actually enforces
  the configured cap (not just that the decorator is present) and that it
  scopes per-client rather than sharing one global counter.

### Test suite: 18 passing (16 → 18, both new tests are rate-limiting)

### Still open (unchanged, tracked, not in this sprint's scope)
- Duplicated PPI/escalation constants between the legacy engine and
  `core/escalation.py`.
- `escalation_index_key` validation gap (raises a raw 500 on a bad key
  instead of a clean 422) — low severity, rollback is clean, no data or
  security impact.
- The enum `.value` vs `.name` bulk-insert gotcha found during the data
  integrity stress test — needs a documented safe-insert helper before any
  bulk historical-PO ingestion feature is built.
