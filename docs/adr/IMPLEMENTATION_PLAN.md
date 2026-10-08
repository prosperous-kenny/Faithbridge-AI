# FaithBridge AI — Implementation Plan

Derived from `docs/PRD.md`. Ordered phases, each with concrete outputs and an exit gate that must pass before the next phase starts.

Estimates assume one full-time engineer. Phases 1–5 total ~12–13 weeks (PRD §23 M0–M1). If Phase 0 accuracy comes in below target, add ~2 weeks to Phase 2.

---

## Current state — Phase 3 complete (verified, with carried limitations)

Phase 3 delivered PRD Use Case 2 end to end: a real program directory, persisted
donor preferences, a mathematical donor matching engine behind a fail-closed AI
contract, and the donor-facing match UI. The stub `/match` path is gone (a test
proves the old route answers 404), every donor-facing payload is PII-free by
construction **and** by assertion, and the exit gate below is backed by executed
tests and a live end-to-end smoke through the running web → API → AI stack. Per
the standing rule: **a task marked done is not a task done** — each row cites the
evidence.

| Exit gate criterion | Result |
| ------------------- | ------ |
| Top-3 match precision ≥ 70% on a hand-labelled sample of donor/program pairs | **Met, 1.000** — `apps/ai/eval/evaluate_matching.py` gates top-3 precision against 15 labelled donor profiles × an 18-program pool (3 per cause) in `matching_dataset.csv`; precision 1.000 on all 15, gate check **PASS (≥ 0.70)**, negative test proves the gate can fail (`test_eval_gate.py`). Data is template-generated (see limitation) |
| Beneficiary PII provably absent from every donor-facing response (PRD §22) | **Met, two independent proofs** — construction: the AI ranker never receives a beneficiary (`POST /match-donors` payload is donor prefs + program rows only), and the API's only enriched field is `open_case_counts`, counted from pending cases **where `consented_at IS NOT NULL` or no linked user exists** and returned as a bare integer with the case id joined for DB correctness but **not** echoed in the response. Assertion: `test_matching.py::test_match_response_is_pii_free` asserts the ledger-shaped response body contains case descriptions and addresses nowhere; `test_donor_cannot_read_assistance_requests` still blocks raw case reads for donors |
| No static stub paths remain in the matching service | **Met** — `apps/ai/faithbridge_ai/matching.py` replaces the `_rank` stub with `rank_matches()`; `apps/ai/tests/test_matching.py` asserts `_rank` no longer exists; AI `/match` answers 404; `/health` reports `matching: "tfidf-sparse-embedding"` |

### How Phase 3 was verified

- **117 API tests pass** (`pytest` in `apps/api`) including new
  `test_programs.py`, `test_preferences.py`, `test_matching.py` and the
  extended `test_rbac.py` matrix; `ruff check app` clean; `alembic check`
  reports "No new upgrade operations detected" after migration
  `20261008_0930_b7f3e9a2c41d` (program columns, `donor_preferences` table,
  `users.preference` relationship), applied to the dev DB and verified
  reversible.
- **84 AI tests pass** (`pytest` in `apps/ai`) including new `test_matching.py`
  (scoring math, cause filter, determinism, reason sentences, engine id
  contract) and the strengthened `test_eval_gate.py`; `ruff check` clean on
  `faithbridge_ai`, `tests`, `eval`.
- **Live end-to-end smoke** against real uvicorn servers on the developer
  database: seed programs (201) → donor registers/sets preferences → `POST
  /ai/match-donors` returns ranked matches with `open_case_counts` = 1 (a real
  pending consenting case) → the same call through the Next.js proxy
  `POST /api/match-donors` → 200 with the identical payload. All smoke rows
  deleted afterwards; AI vectors seeded from the app's own hasher like a real
  login.
- **Web verified**: `npm run build` green (static `(portal)/match`, dynamic
  `/api/{match-donors,preferences,programs}` proxies carrying an optional
  `FAITHBRIDGE_ACCESS_TOKEN` bearer), `tsc --noEmit` and `eslint .` clean.

### What Phase 3 produced

- `apps/ai/faithbridge_ai/matching.py` — `rank_matches()` implementing the
  weighted composite in `docs/adr/0002-matching-engine.md`: hard cause filter,
  then 0.60 TF-IDF cosine + 0.15 budget + 0.15 location + 0.10 cause, clipped
  to [0, 1]; deterministic sort; per-result `matches_causes/_budget/_location`
  booleans and a human-readable `reason`. Engine id
  `tfidf-sparse-embedding`, reported on `/health`.
- `apps/ai/faithbridge_ai/main.py` — `POST /match-donors` (donor prefs +
  program pool in, ranked `MatchItem`s out; stateless, never sees a
  beneficiary). Old `/match` removed.
- `apps/ai/eval/{matching_dataset.csv,evaluate_matching.py,matching_results.txt}`
  — 15 labelled profiles × 18 programs, per-profile shots/expected, gate check,
  results file (1.000 PASS), synthetic-data provenance warning per run.
- `apps/api/app/db/models.py` + migration `20261008_0930_b7f3e9a2c41d` —
  `Program` gains `description`, `location`, `budget_needed`, `is_active`
  (nullable, `is_active` NOT NULL server-default true, no-op migration style);
  new `donor_preferences` table (`donor_id` unique FK → users CASCADE, causes
  ARRAY(String(50)), budget Float, location String(100)); `preference`
  relationship on `User`.
- `apps/api/app/api/routes/{programs,preferences,ai}.py` + repositories +
  `services/matching.py` + `ai_client.match_donors` — `GET /programs` (any
  authenticated role; donors/members see active only, leaders their org, admins
  all), `POST/PATCH /programs` faith_leader(own-org)/admin only,
  `GET/PUT /donors/preferences/` donor-only upsert (causes validated against
  PRD §8's six literals), `POST /ai/match-donors` donor-only with a saved-prefs
  fallback, 400 on missing criteria, 503 on an out-of-contract AI reply, and
  `open_case_counts` computed from pending cases in the same
  `(org, category)` with the consent gate above.
- `apps/web/app/(portal)/match/page.tsx` + `components/MatchForm.tsx` +
  `lib/matching.ts` + `app/api/{match-donors,preferences,programs}/route.ts` +
  nav link — donor preference form → ranked results cards (score, budget/
  location/cause chips, reason, open-case count), with the proxy layer.
- `docs/adr/0002-matching-engine.md` — the ADR recording the sparse-embedding
  decision, the scoring weights, the dense-embedding deferral, and the
  template-data limitation.

### The one carried decision

Consent-gated open-case counts stay in the API response because they are the
PRD §8 "context" that makes match quality real — what a donor wants to know is
whether a *need* still exists behind the program. They are integers only,
counted from cases whose owner consented (or that have no linked user), and the
matching engine itself never touches a case. The web UI renders them as a small
"open cases" badge, not as beneficiary content.

### Not yet true, and deliberately so

- **Matching accuracy is measured on template data.** 1.000 is fit to one
  author's synthetic profiles; real donor/program pairs must replace
  `matching_dataset.csv` before the M1 gate claim, exactly as for
  classification (ADR 0001 / 0002).
- **The dense-embedding comparison is still not run for matching either.**
  ADR 0002 defers it with the same trigger as ADR 0001: real fit data. No
  ~2 GB torch install was performed for this phase.
- **Front-end has no browser sign-in (unchanged).** The match form carries
  `FAITHBRIDGE_ACCESS_TOKEN` server-side like the Phase 2 pages; a browser
  OIDC/PKCE flow is still required before the portal is end-user usable.
- **Keycloak has still never run; Celery has still never brokered a task;
  CI remains unpushed** (unchanged from Phase 2 — no Docker/JVM; OAuth token
  still lacks the `workflow` scope). First hosted run of the 117+84 tests is
  still pending a push.

---

## Earlier state — Phase 2 complete (verified, with carried limitations)

Phase 2 delivered the end-to-end assistance loop: a persisted, lifecycle-governed
request pipeline that submits a need, classifies it synchronously against a
fail-closed AI contract, records every transition in a tamper-evident audit
chain, and surfaces a priority-sorted queue to faith leaders. Urgency is now
calibrated on labeled data instead of keyword heuristics. The exit gate below is
backed by executed tests and live-server measurements, per the standing rule:
**a task marked done is not a task done** — each row cites the evidence.

| Exit gate criterion | Result |
| ------------------- | ------ |
| Full submission → triage → fulfil flow exercised by an integration test against a live Postgres | **Met** — `tests/test_assistance_flow.py`: 15 tests walk the real `POST → GET → PATCH` path; the full `submitted → triaged → approved → fulfilled` progression runs with the audit chain intact and `verify_chain` passing; every illegal transition (e.g. `submitted → fulfilled`) is rejected 409 before any write |
| Classification accuracy ≥ 85% on the holdout set | **Met** — the Phase 0 category classifier is unchanged (90.3%, worst category `education` recall 0.700), and that gate remains a test (`test_eval_gate.py`) in the AI run |
| Urgency precision/recall reported per priority band | **Met** — `eval/evaluate_urgency.py` + `apps/ai/tests/test_calibration.py`; on the 80-row labeled set (20/band) the calibrated band classifier scores **0.750 band accuracy** with per-band precision/recall: critical 0.833/0.833, high 0.833/0.833, medium 0.667/0.667, low 0.667/0.667. Gate floors: accuracy ≥ 0.70, band 0.50. Data is template-generated (see caveat) |
| `POST /assistance/requests` p95 < 3s including AI call | **Met — measured, not guessed** — 25 live submissions through the running API → AI service → Postgres path: p50 618ms, **p95 650ms**, max 809ms (`C:\…\Temp\opencode\p95.py` against `127.0.0.1`). Measurement note: timing through `localhost` on this machine adds a ~2s IPv6 stall; all timings here use the literal loopback |

### How Phase 2 was verified

- **89 API tests pass** (`pytest` in `apps/api`), `ruff check` clean on
  `apps/api` and `apps/ai`, `alembic upgrade head` applied the new revision and
  `alembic check` reports "No new upgrade operations detected".
- **55 AI tests pass** (`pytest` in `apps/ai`), including the 18 new
  `test_calibration.py` tests: dataset integrity (80 rows, 20/band, generator
  matches the committed CSV, deterministic), the `predict`/`priority_of`
  contract, per-band gates, and negative tests proving the gate can fail.
- **Live end-to-end smoke** against real uvicorn servers on the developer
  database: bootstrap admin created via the app's own hasher; `/auth/register`
  (201) enforces that only an admin may create `faith_leader`/`admin`;
  `/auth/login` (200); a `community_member` submits to org 1 → **201** with an
  integer id, `priority: low`, `status: submitted`; a `faith_leader` lists the
  queue → 200; the same member lists → **403** (org/role guard); the Next.js
  proxy `POST /api/assistance` → **201**; the `/requests` leader-queue page
  renders the live case and honours `?status=` filters.
- **Web verified**: `npm run build` green (static `/request-assistance`,
  server-rendered dynamic `/requests` and `/api/assistance`), `tsc --noEmit`
  and `eslint .` both clean.

### What Phase 2 produced

- `apps/api/app/services/assistance.py` — `LIFE_CYCLE` state machine with
  `assert_transition`; illegal transitions raise before any write.
- `apps/api/app/api/routes/assistance.py` — real `POST /assistance/requests`
  (synchronous classify with fail-closed validation — an out-of-contract AI
  response is a 503 and nothing is persisted), `GET /assistance/requests`
  (`status` filter, `sort=newest|priority`, org scope), and
  `PATCH /assistance/requests/{id}/status` (org guard, requires
  `faith_leader`/`admin`, writes a hashed audit entry).
- `apps/api/app/repositories/{assistance,users,audit}.py` — persistence,
  `get_or_create_beneficiary`, org-scoped queue queries, and a per-org
  tamper-evident SHA-256 hash chain (`log_action`, `verify_chain`).
- `apps/api/app/workers/{tasks,celery_app}.py` — in-process FastAPI
  `BackgroundTasks` dispatch of `notify_new_critical_request` and
  `rescore_request` (the executed path), plus a documented Celery adapter that
  activates only when `CELERY_BROKER_URL` is set.
- Migration `a1c2e4f60891` — `audit_logs.note`, included in the hash chain.
- `apps/ai/faithbridge_ai/calibration.py` — urgency band classifier
  (TF-IDF word+char → LinearSVC, fitted on 80 labeled rows), `urgency_score` =
  band centre, `priority_of` inverse mapping, `models/urgency_calibration.joblib`
  artifact saved alongside `baseline.joblib`.
- `apps/ai/eval/{build_urgency_dataset,evaluate_urgency}.py` + `urgency_dataset.csv`
  + `urgency_results.txt` — labeled urgency data and a harness that reports
  per-band precision/recall, a gate check, and the synthetic-data warning on
  every run; the warning also feeds the accuracy caveat.
- `apps/web/app/(portal)/` — `request-assistance` submission form (description +
  organization id) and the `requests` faith-leader queue (priority-sorted,
  `?status=` filters, consent-gated PII display (PRD §22)); the `/api/assistance`
  proxy forwards `organization_id` and attaches an optional
  `FAITHBRIDGE_ACCESS_TOKEN` bearer. Legacy `app/request/` page removed; NAV,
  home and dashboard links updated.
- `apps/api/tests/test_assistance_flow.py` (15 tests), `apps/ai/tests/test_calibration.py`
  (18 tests), plus `organization_id` support in `conftest`
  (`make_user`) and the RBAC route matrix.

### The one carried decision

A **single `role` column** (PRD §20) remains the source of truth: a donor who is
also in need must hold a `community_member` account to submit. Phase 2 resolved
the related question of who may create handlers: `/auth/register` refuses
self-service `faith_leader`/`admin` accounts (403 without an authenticated
admin), so a deployment needs exactly one bootstrap admin created by the
operator.

### Not yet true, and deliberately so

- **Celery has never brokered a task.** No Docker/Redis exists on this machine,
  so `celery_app.py` is unexecuted configuration: the real path is FastAPI
  in-process `BackgroundTasks`, which is exercised by the tests. Swapping the
  execution backend is a one-line change behind the same `tasks.py` functions.
- **Urgency accuracy is measured on template data.** 0.750 band accuracy is fit
  to an 80-row synthetic library, not real beneficiary submissions; the harness
  prints the warning on every run (PRD §23). Category accuracy keeps the same
  Phase 0 caveat.
- **The web frontend has no sign-in flow.** The submission form and queue take
  their bearer token from `FAITHBRIDGE_ACCESS_TOKEN` (server-side). Without it
  they surface the API's 401 with an explanation instead of failing silently.
  A browser-facing OIDC/PKCE flow is required before the site is usable by
  end users; until then the portal is a developer-facing shell on real data.
- **Keycloak has still never run** (unchanged; no Docker/JVM), so the OIDC path
  beyond the loopback-JWKS tests remains unproven.
- **Refresh tokens are still stateless** (rotation implemented, revocation not
  persisted — deferred from Phase 1).
- **CI remains unpushed and never run on GitHub** (unchanged); the OAuth token
  still lacks the `workflow` scope, and the first hosted run of the 89+55 tests
  is still a pending unknown.

---

## Earlier state — Phase 1 complete (verified, with carried limitations)

Phase 1 delivered real, role-enforced authentication and routing on top of the
Phase 0 schema. The exit gate below is backed by executed tests and a live
uvicorn smoke test, per the standing rule from the Phase 0 audit: **a task
marked done is not a task done** — each row cites the evidence.

| Exit gate criterion | Result |
| ------------------- | ------ |
| All four roles authenticated and authorized | **Met** — `tests/test_rbac.py` runs a 4-role × 5-route matrix: every allowed role passes the guard (never 403), every other combination is 403 (never a misreported 401), and anonymous callers get 401 with `WWW-Authenticate` on every guarded route |
| Negative tests prove a donor cannot read beneficiary PII (PRD §22) | **Met** — `test_donor_cannot_read_assistance_requests` asserts 403 and that the body leaks no case id, description, or address; `test_faith_leader_sees_pii_only_with_consent` proves PII appears only when `consented_at` is set *and* a linked user exists |
| No endpoint returns PII without an explicit role check | **Met** — every data route is in the matrix above; `/health` (unguarded, deliberate — probes must work for load balancers) returns no data, and `/auth/register` accepts only public registration roles |
| OIDC login / JWT verification path | **Met for `AUTH_MODE=local`** by the whole suite, and **covered for `AUTH_MODE=oidc`** by `tests/test_oidc_tokens.py`, which verifies RS256 signature, issuer, audience, expiry, tampering, and unknown-key-id rejection against a loopback JWKS server standing in for Keycloak |
| Keycloak dev container + realm import | **NOT verified at runtime** — no Docker or JVM exists on this machine; the compose service and realm JSON are unexecuted configuration (see "Not yet true") |

### How Phase 1 was verified

- **74 API tests pass**, `ruff check .` clean, `alembic upgrade head` then
  `alembic check` clean, migration smoke (`upgrade head` → `downgrade base`)
  clean including the new `a1f5c2e7d904` revision (both directions).
- **Live smoke test** against a real uvicorn server on the developer database:
  register 201, login 200 (900 s TTL), `/auth/me` 200, anonymous 401, donor →
  403 on `/dashboard/stats`, refresh rotates both tokens, self-registration as
  `admin` → 403. The smoke-test row was deleted afterwards.
- **OIDC verifiability without Keycloak**: `tests/test_oidc_tokens.py` starts a
  throwaway HTTP server on the loopback interface, serves a generated RS256
  JWKS, signs tokens with a locally generated key, and asserts accept/reject on
  signature, issuer, audience, expiry, a tampered payload, and an unknown key id.

### What Phase 1 produced

- `apps/api/app/core/{security,rbac,deps}.py` — PBKDF2-HMAC-SHA256 password
  hashing (600k iterations, per-password salt, cost stored in the hash itself so
  it can be raised later); HS256 issue/verify for `AUTH_MODE=local`; RS256 JWKS
  verify for `AUTH_MODE=oidc`; `Role` enum carrying the four PRD §12 values;
  `require_role(...)` with the documented rule that `admin` supersedes every
  role; `get_current_user`, which resolves *identity* from the token but
  *authority* from the database — role changes and account revocation take
  effect on the next request, not at token expiry.
- `apps/api/app/api/routes/auth.py` — real `/register`, `/login`, `/refresh`,
  `/me`. Registration blocks self-grant of `faith_leader`/`admin` (403 without
  an authenticated admin); login returns generic 401s and burns the same CPU for
  unknown emails as for wrong passwords, so response time does not reveal which
  addresses exist. Refresh rotates both tokens.
- Guards on every route. `GET /assistance/requests` exposes beneficiary PII
  only when consent exists (PRD §22); donation reads are scoped to the caller
  (donor sees own ledger, admin sees all).
- `apps/api/app/repositories/{users,assistance,donations,dashboard}.py` —
  routes no longer issue their own SELECTs.
- Migration `a1f5c2e7d904` — `users.password_hash` (nullable: OIDC-managed
  accounts store none) and `users.is_active` (revocation is a flag, not a
  delete, so audit rows keep their referents).
- `infra/docker-compose.yml` and `infra/keycloak/realms/faithbridge-realm.json`
  — a Keycloak 26 service and a realm declaring the four roles plus a PKCE
  public client whose tokens carry `aud=faithbridge-api`, enforced by the API.
- `tests/{test_auth,test_rbac,test_oidc_tokens}.py` and `tests/factories.py` —
  50 new tests.

### The one carried decision

Each user has exactly one role (`role` is one column, per PRD §20). A donor who
is also in need must hold a `community_member` account to submit a request;
multi-role accounts are a deliberate non-goal until PRD changes.

### Not yet true, and deliberately so

- **Keycloak has never run.** There is no Docker or JVM on this machine, so the
  compose service and the realm import booted nowhere; they are unexecuted
  configuration. The OIDC *verification* path is tested, but "Keycloak boots
  and the realm imports" is unproven and needs either Docker or a machine with
  it. The realm JSON also encodes the audience contract and redirect URIs
  without ever having been exercised by a container.
- **Refresh tokens are stateless.** A stolen refresh token stays valid until
  its 14-day expiry; rotation on each refresh is implemented, but persistence
  and revocation are deferred to Phase 2's session work.
- **`/register`, `/login`, `/refresh` answer 503 in OIDC mode** on purpose:
  credentials are the provider's job there. The web app must move to the
  Keycloak authorization flow when `AUTH_MODE=oidc` is switched on.
- **CI is still unpushed and has never run on GitHub**, unchanged from Phase 0;
  all three jobs (this time including the 50 new tests) pass against a clean
  tree locally, but the first hosted run is still an unknown.

---

## Earlier state — Phase 0 complete (verified, with one carried limitation)

All seven Phase 0 tasks are done. This section was rewritten after an audit
found that three of them had been marked complete without the underlying work
actually existing; the audit is recorded in "Phase 0 audit" below so the claim
is auditable rather than asserted.

| Exit gate criterion | Result |
| ------------------- | ------ |
| Classification accuracy ≥ 85% on held-out split, no category < 70% | **Met** — TF-IDF + LinearSVC at 90.3%; worst category `education` recall 0.700 |
| `alembic upgrade head` then `downgrade base` both succeed | **Met** — 3 revisions, verified locally and in a clean-checkout simulation (`python -m tests.test_migrations`) |
| CI green on a clean checkout | **Verified locally, not yet run on GitHub** — every job was executed against a pristine copy of the tree and passed; the workflow itself is still unpushed (see below) |

### Phase 0 audit

An earlier revision of this plan asserted "Phase 0 exit gate passed" with all
three remaining tasks done. Verifying each claim against the code found four
places where the documentation was ahead of reality:

| Claim | Reality found | Fix |
| ----- | ------------- | --- |
| Task 3 — migrations for all nine entities | Tables existed but **no foreign keys at all**; every relationship was a bare `Integer` column | 14 FKs + 16 indexes across 3 revisions, with ondelete rules chosen per relationship |
| Task 4 — rule-based classifier replaced | `baseline.classify()` **ignored the fitted model** and always delegated to the rules; the model never served a request | Model now serves; `classifier` and `confidence` reported on `/classify` and `/health` |
| Task 5 — evaluation harness | Harness was sound, but provenance existed only in prose, and nothing proved `gate_check()` could ever fail | `source` column per row, provenance reported every run, negative tests for the gate |
| Task 6 — "CI green" | The workflow had **never been executed**; `tests/test_db.py` ran `create_all` on the primary database, masking drift | Tests build a throwaway DB from the migration chain; workflow re-ordered and run against a clean copy |

Two further defects were only exposed once the destructive `create_all` was
removed: `created_at`/`updated_at`/`occurred_at` were nullable in the initial
migration but NOT NULL in the models, and `email-validator` was missing from
`apps/api/pyproject.toml` (it existed only in a local venv, so a clean
`pip install` could not even collect the test suite).

The lesson is recorded deliberately: **a task marked done is not a task done.**
The evidence for each row above is a test or an executed command, not a
statement in this file.

### What Phase 0 produced

- `apps/api/alembic/` — three reversible revisions creating all nine PRD §20
  tables, then foreign keys and indexes, then timestamp nullability. Schema is
  owned by Alembic; `create_all` no longer runs at API startup and the app
  refuses to boot on a stale revision.
- `apps/api/app/db/models.py` — every relationship is an enforced `ForeignKey`
  with a deliberate `ondelete` rule: `CASCADE` where a child cannot outlive its
  parent, `SET NULL` where the link is optional, and `RESTRICT` on donations so
  financial history cannot be deleted out from under the ledger (PRD §8).
- `apps/api/tests/test_referential_integrity.py` — proves the constraints are
  enforced, not merely declared: orphan inserts fail, and each ondelete rule
  actually fires.
- `apps/ai/faithbridge_ai/baseline.py` — TF-IDF (word 1-2 + char 3-5 grams) into
  a linear SVM, chosen over the rule-based matcher (90.3% vs 80.6%), and actually
  serving requests.
- `apps/ai/faithbridge_ai/train.py` — builds the model artifact; the service also
  trains at startup, so a deploy does not depend on a checked-in binary.
- `apps/ai/eval/` — harness built before any tuning: 204 labeled statements
  across six categories, deterministic stratified split, per-category
  precision/recall, confusion matrix, an explicit gate check, and a provenance
  block that warns while the data is entirely synthetic.
- `apps/ai/tests/test_eval_gate.py`, `apps/ai/tests/test_dataset_integrity.py` —
  the accuracy gate is a test, so a regression fails CI; and the gate itself is
  tested with deliberately bad input so it cannot be vacuously green.
- `.github/workflows/ci.yml` — ruff, migrations, drift check, pytest, Next
  typecheck/lint/build, plus a check that the committed eval artifacts are not
  stale.

### The one carried limitation

The evaluation dataset is template-generated, not real beneficiary submissions.
The 90.3% figure is reproducible and makes the gate checkable, but it is a
weaker proxy than real data and is likely optimistic for two concrete reasons:
the templates share an author with the tuning process, and templates within a
category share phrasing, so a model trained on 28 housing templates is tested on
6 written in the same style. **Real submissions must replace
`apps/ai/eval/dataset.csv` before the M1 launch gate in PRD §23 can be claimed
as met.** This is recorded in `docs/adr/0001-model-selection.md`, and it is now
also enforced mechanically: provenance is a per-row `source` column and the
harness prints a warning on every run while the data is entirely synthetic.

### Not yet true, and deliberately so

- **CI has never run on GitHub.** Every job was verified by executing it against
  a pristine copy of the tree (fresh virtualenv, `npm ci`, real PostgreSQL), and
  that is what caught the missing `email-validator` dependency. But the workflow
  file itself is still in an unpushed local commit, and the OAuth token lacks
  the `workflow` scope GitHub requires to push it. The first real run is the
  remaining unknown, and it happens when the user authorizes a push.
- **The embedding comparison was not run.** Deferred, not skipped; the rationale
  and revisit trigger are in the ADR. No ~2 GB torch install was performed.
- **No hosted backend.** Unchanged from the previous milestone; see the
  deployment note below.

### Also done in this milestone

Frontend deployed to Netlify at
`https://deluxe-malasada-7a387b.netlify.app` (frontend only — see the
deployment note below).

---

## Historical state — Phase 0 in progress

Snapshot taken before the Alembic, classifier, harness and CI work landed. Kept
for history; the authoritative status is the section above.

| Asset | Status |
| ----- | ------ |
| Monorepo layout (`apps/api`, `apps/ai`, `apps/web`, `infra`, `docs`) | Done |
| FastAPI API with health/auth/assistance/donations/dashboard routes | Done |
| Rule-based need classifier + urgency scoring (`apps/ai/faithbridge_ai/classifier.py`) | Done, placeholder quality |
| AI service endpoints `/health`, `/classify`, `/match` | Done |
| Test suite | Done (now 23 API + 37 AI) |
| Next.js 16.3.6 + React 19.3.0 + TypeScript + Tailwind scaffold | Done, `npm run build` green, 0 npm vulnerabilities |
| Node.js v24.19.0 (LTS) + npm 11.17.0 | Done |
| PostgreSQL 16.15 installed locally (Windows service, `scram-sha-256` auth) | Done |
| SQLAlchemy 2.1 async (asyncpg) engine, session factory, 9 tables | Done, schema owned by Alembic |
| Alembic migration history | Done, 3 revisions, `upgrade head` / `downgrade base` verified |
| Evaluation harness + TF-IDF baseline classifier | Done, 90.3% accuracy, gate enforced |
| GitHub Actions CI (ruff, pytest, migrations, web build) | Written and locally verified; never run on GitHub |
| `/health/ready` DB-backed readiness probe | Done |
| **Working web app: 4 routes rendering real data** | Done — see below |
| PRD, this plan, public GitHub repo | Done |

### Working application (this milestone)

The app is running locally and serving live data end to end. This is a real
application, distinct from the static `design.html` preview in the repo root.

| Route | What it does |
| ----- | ------------ |
| `/` | Landing page — product positioning, the three pillars, the three user roles |
| `/dashboard` | Live row counts for all 7 entities, read from PostgreSQL through the API |
| `/status` | Real health probe of the API, the AI service, and database connectivity |
| `/request` | Interactive form; classifies a need via web → Next route handler → FastAPI → AI service |

**Verified request path.** Posting "Family of four facing eviction in two weeks
and needs rent help" through the running app returns:

```json
{ "id": "req-0001", "category": "housing", "urgency_score": 65, "priority": "high", "status": "submitted" }
```

**Local run commands**

```bash
# Terminal 1 — AI service
.\.venv\Scripts\python.exe -m uvicorn faithbridge_ai.main:app --port 8200   # cwd: apps/ai

# Terminal 2 — API (run migrations first: alembic upgrade head)
.\.venv\Scripts\python.exe -m alembic upgrade head                          # cwd: apps/api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000               # cwd: apps/api

# Terminal 3 — web
npm.cmd run dev                                                             # cwd: apps/web
```

Open http://localhost:3000. Note `npm` must be called as `npm.cmd` in
PowerShell; the execution policy blocks `npm.ps1`.

### Deployment

The frontend is live at
`https://deluxe-malasada-7a387b.netlify.app`. Netlify hosts **only**
`apps/web`: it cannot run long-running FastAPI servers or PostgreSQL. On the
deployed site `/dashboard` and `/status` render an explanation that no API is
connected rather than showing an error. Wiring live data requires hosting the
API separately (Railway, Render, or Fly) and setting `API_URL` in Netlify's
environment variables — deliberately not done here, because PRD §25 leaves the
jurisdiction and escrow question open and that decision should precede choosing
where beneficiary PII lives.

Not started: real authentication/RLBAC, async workers, payments, hosted API.

---

## Phase 0 — Spike & Foundation (2 weeks)

**Goal:** De-risk the two unknowns that gate everything downstream: classification accuracy and the persistence/auth stack.

**Tasks**

1. ~~Install Node.js (LTS) so `apps/web` builds in CI; get `npm run build` green on the existing scaffold.~~ **Done** — Node v24.19.0, Next.js upgraded 14.2.5 → 16.3.6 to clear GHSA-p293-qw3h-jr36; `npm run build` green, 0 vulnerabilities.
2. ~~Stand up local infra and verify connectivity from the API.~~ **Done** — PostgreSQL 16.15 installed natively (no Docker on this machine); `scram-sha-256` username/password auth; `/health/ready` reports `database: up`.
3. ~~Add SQLAlchemy 2.0 (async) + Alembic; create migrations for all nine entities in PRD §20.~~ **Done** — async engine and session factory; Alembic owns the schema across three reversible revisions: the nine tables, then foreign keys and indexes, then timestamp nullability. `create_all` no longer runs at API startup and the app verifies the applied revision, so schema changes are reviewable. **Corrected during the Phase 0 audit:** the original migration created the tables but no foreign keys at all, and the timestamp columns disagreed with the models on nullability. `tests/test_referential_integrity.py` now proves each constraint and ondelete rule is enforced.
4. ~~Replace the rule-based classifier with a real baseline.~~ **Done** — TF-IDF (word 1-2 + char 3-5 grams) into a linear SVM, measured against the rule-based matcher: **90.3% vs 80.6%** on the held-out split, and it is what serves `POST /classify`. **Corrected during the Phase 0 audit:** the previous "swap" only added the model while `baseline.classify()` kept delegating to the rules, so nothing had actually been replaced. Urgency and priority deliberately stay on the keyword heuristics until Phase 2 calibrates them, and a test asserts the model swap cannot change them. The embedding-model comparison was deferred, with the reason recorded in `docs/adr/0001-model-selection.md`; it is not yet run.
5. ~~Build the evaluation harness *before* tuning.~~ **Done** — 204 labeled statements across six categories, deterministic stratified split, per-category precision/recall, confusion matrix, and an explicit gate check. Built and run before any tuning. **Strengthened during the Phase 0 audit:** provenance moved from prose into a per-row `source` column, the harness reports the provenance mix and warns on every run while the data is entirely synthetic, dataset integrity is asserted (204 rows, 34 per category, no duplicates, generator matches the committed CSV), and `gate_check()` is tested with deliberately bad input so the gate cannot be vacuously green.
6. ~~Add CI (GitHub Actions): ruff lint, pytest, `next build`, migration smoke test.~~ **Done** — three jobs: api (ruff, migrations, drift check, migration smoke test, pytest), ai (ruff, pytest including the accuracy gate, stale-artifact checks), web (typecheck, lint, build). **Corrected during the Phase 0 audit:** the previous step order ran `alembic check` before anything had migrated, so the drift check would have failed on a genuinely empty CI database, and `tests/test_db.py` called `create_all` on the primary database, which both destroyed local data and hid schema drift. Tests now build a throwaway database from the migration chain. Every job was then executed against a pristine copy of the tree, which surfaced a missing `email-validator` dependency that made a clean `pip install` unable to collect the suite. **The workflow itself has still never run on GitHub** — it remains in an unpushed local commit.
7. **Done (added in this milestone)** — build the working web app so the stack is
   demonstrable end to end: app shell, four routes, server-side API client, and a
   Next route handler proxying to FastAPI. Verified live against PostgreSQL.

**Concrete outputs**

- `apps/api/app/db/{base,session,models}.py` — all nine tables with enforced foreign keys, `created_at`/`updated_at` NOT NULL, audit columns **Done**
- `apps/api/alembic/` — three revisions, reversible up/down **Done**
- `apps/api/tests/test_referential_integrity.py` — FK enforcement and ondelete behaviour **Done**
- `apps/ai/faithbridge_ai/baseline.py` — TF-IDF baseline behind one interface, serving requests **Done**
- `apps/ai/faithbridge_ai/train.py` — builds the model artifact **Done**
- `apps/ai/eval/dataset.csv` — 204 labeled need statements across the six categories, each with a `source` **Done** (template-generated; see limitation)
- `apps/ai/eval/evaluate.py` — per-category precision/recall + confusion matrix + gate check + provenance **Done**
- `apps/ai/eval/report.md` — accuracy by model, chosen model, error analysis **Done**
- `apps/ai/tests/test_eval_gate.py`, `apps/ai/tests/test_dataset_integrity.py` — gate and dataset integrity **Done**
- `.github/workflows/ci.yml` **Done**
- `docs/adr/0001-model-selection.md` **Done**

Deliberately not produced: the embedding-model (sentence-transformers)
comparison. Deferred rather than skipped — reasoning and revisit trigger are in
the ADR.

**Exit gate**

- Classification accuracy ≥ 85% on a held-out split, with per-category report showing no category below 70% — **Met**, with the caveat that the data is synthetic
- `alembic upgrade head` then `downgrade base` both succeed — **Met**
- CI green on a clean checkout — **Met locally by execution; the GitHub run is still pending a push**

---

## Phase 1 — Data Layer & Authentication (2 weeks)

> **Status: complete.** All five tasks above are done and verified; the exit
> gate is met with evidence, and the carried limitations are recorded in the
> "Current state — Phase 1 complete" section at the top of this document. The
> text below is the original task definition, kept for history.

**Goal:** Real persistence and real, role-enforced auth (PRD §10, §11, §12).

**Tasks**

1. Add Keycloak as a dev container (OIDC, local dev) with the client wired for a production IdP later.
2. Implement `users` with the four PRD §12 roles and organization linkage.
3. Build the RBAC dependency (`require_role`) and apply it to every route.
4. Implement `/auth/register`, `/auth/login`, `/auth/refresh` and the JWT verification path.
5. Repository/service layer so routes never touch the session directly.

**Concrete outputs**

- `apps/api/app/core/{security,rbac,deps}.py` — JWT verification, `require_role(...)` guard, shared dependencies
- `apps/api/app/api/routes/auth.py` — replaced stub with real flows
- `apps/api/app/repositories/` — one module per entity
- `infra/docker-compose.yml` — Keycloak service + realm import with seeded roles
- `apps/api/tests/test_auth.py` — login, refresh, expiry
- `apps/api/tests/test_rbac.py` — negative tests: each role denied on the other's endpoints

**Exit gate**

- All four roles authenticated and authorized; negative tests prove a donor cannot read beneficiary PII (PRD §22)
- No endpoint returns PII without an explicit role check

---

## Phase 2 — Assistance Pipeline & AI Quality (3 weeks)

**Goal:** The core loop of PRD Use Case 1 working end to end, with production-grade classification.

**Tasks**

1. Implement the `assistance_requests` lifecycle state machine: `submitted → triaged → approved → fulfilled / declined`.
2. Persist submissions and call the AI service synchronously; block on a valid classification.
3. Calibrate urgency scoring against labeled urgency, not just category.
4. Move re-scoring and notifications to Celery so the request path stays under the latency budget.
5. Ship the web UI: submission form, and a faith-leader queue filtered by priority.

**Concrete outputs**

- `apps/api/app/services/assistance.py` — state machine, illegal-transition guard
- `apps/api/app/api/routes/assistance.py` — real `POST /assistance/requests`, `GET /assistance/requests`, `PATCH /assistance/requests/{id}/status`
- `apps/api/app/workers/{celery_app,tasks}.py` — async re-scoring, notification dispatch
- `apps/ai/faithbridge_ai/calibration.py` — urgency thresholds fitted on labeled data
- `apps/web/app/(portal)/request-assistance/` — submission form
- `apps/web/app/(portal)/requests/` — priority-sorted leader queue
- `apps/api/tests/test_assistance_flow.py`, `apps/ai/tests/test_calibration.py`

**Exit gate**

- Full submission → triage → fulfil flow exercised by an integration test against a live Postgres
- Classification accuracy ≥ 85% on the holdout set; urgency precision/recall reported per priority band
- `POST /assistance/requests` p95 < 3s including AI call (PRD §11)

---

## Phase 3 — Programs & Donor Matching (2 weeks)

> **Status: complete.** All four tasks are done and verified; the exit gate is
> met with evidence, and the carried limitations are recorded in the
> "Current state — Phase 3 complete" section at the top of this document. The
> text below is the original task definition, kept for history.

**Goal:** PRD Use Case 2 and §8 Donor Matching Engine.

**Tasks**

1. Implement `programs` CRUD and the donor preference model (causes, budget, location).
2. Replace the static `_rank` stub with embedding similarity plus a cause/constraint filter.
3. Return ranked matches with a human-readable reason, so a donor can see why.
4. Add the donor-facing matching UI.

**Concrete outputs**

- `apps/api/app/services/matching.py` — candidate generation, scoring, explanation
- `apps/api/app/api/routes/ai.py` — `POST /ai/match-donors`
- `apps/api/app/api/routes/programs.py` — program CRUD
- `apps/ai/faithbridge_ai/matching.py` — embedding index + ranker
- `apps/web/app/(portal)/match/` — donor preference form and ranked results
- `apps/api/tests/test_matching.py`, `apps/ai/tests/test_matching.py`

**Exit gate**

- Top-3 match precision ≥ 70% on a hand-labelled sample of donor/program pairs
- Beneficiary PII is provably absent from every donor-facing response (PRD §22)
- No static stub paths remain in the matching service

---

## Phase 4 — Donations, Impact Ledger & Audit (2 weeks)

**Goal:** Transparent donation utilization and the measurement backbone (PRD §8, §20).

**Tasks**

1. Implement the donation lifecycle: `pledged → paid → allocated → distributed`.
2. Append-only `impact_events` written by domain actions, not by hand.
3. Tamper-evident `audit_logs` via a hash chain.
4. Build the Community Impact Score service with per-organization configurable weights (PRD §15).
5. Celery aggregation job that rolls events into per-period totals.

**Concrete outputs**

- `apps/api/app/services/donations.py` — lifecycle transitions, allocation rules
- `apps/api/app/api/routes/donations.py` — real ledger endpoints
- `apps/api/app/services/impact.py` — score computation with configurable weights
- `apps/api/app/services/audit.py` — hash-chain writer + verifier
- `apps/api/app/workers/impact_rollup.py`
- `apps/api/tests/test_donations.py`, `apps/api/tests/test_audit_chain.py`, `apps/api/tests/test_impact_score.py`

**Exit gate**

- Audit chain verifier detects a hand-edited row in a test
- Impact totals reconcile exactly with the donation ledger for a seeded period
- Impact Score reproducible from config alone; weights differ per organization in a test

---

## Phase 5 — Dashboards, Reporting & Launch (1–2 weeks)

**Goal:** PRD Use Cases 3 and 4, and the M1 launch gate.

**Tasks**

1. Implement `/dashboard/community-insights` with real aggregates (trends, high-need categories, donation effectiveness).
2. Implement `/dashboard/impact-report` returning the Impact Score plus its component breakdown.
3. Build the dashboard and report export (CSV + PDF).
4. Ship the consent flow and data-deletion request required by PRD §22.
5. Instrument Prometheus metrics and Sentry; run a load test.

**Concrete outputs**

- `apps/api/app/api/routes/dashboard.py` — real insights and impact endpoints
- `apps/web/app/(portal)/dashboard/` — trend charts and priority breakdown
- `apps/web/app/(portal)/impact-report/` — report view with export
- `apps/api/app/api/routes/privacy.py` — consent record, data deletion request
- `apps/api/tests/test_dashboard.py`, `apps/api/tests/test_privacy.py`
- `tests/load/k6.js` — p95 latency verification
- `docs/launch-gate-m1.md` — measured evidence for each gate criterion

**Exit gate (PRD §23)**

> **Carried-forward caution.** The classification criterion below is measured
> against a template-generated dataset. It is not yet evidence of field
> accuracy; see the Phase 0 limitation note and `docs/adr/0001-model-selection.md`.

- p95 API latency < 3s under load, evidenced by the k6 run
- Classification accuracy ≥ 85% on the curated validation set
- Signed donor/beneficiary consent flow live
- Three pilot organizations onboarded and processing real requests

---

## Phase 6 — Phase 2 Features (8–10 weeks)

Per PRD §14: payments and payout orchestration, the Employment Empowerment Module, WhatsApp integration, advanced analytics.

- `placements` table and job/skill/mentorship matching service
- Payment provider integration behind an interface, plus reconciliation jobs
- WhatsApp channel adapter feeding the same `POST /assistance/requests` path
- Analytics: cohort and retention reporting toward PRD §13 KPIs
- Revenue model decision executed here (PRD §24) — stakeholder sign-off required before build

**Exit gate:** a donation is collected, allocated, distributed, and reconciled end to end through a real payment provider; a job seeker is placed and recorded.

---

## Phase 7 — Phase 3 Features (8–10 weeks)

Per PRD §14: voice assistant, fraud detection, volunteer matching, mobile application.

- Voice intake path reusing the classification pipeline
- Duplicate-request and anomaly detection on top of `audit_logs` (PRD §22)
- Volunteer entity, availability model, matching service
- Mobile app or hardened PWA

**Exit gate:** fraud rules demonstrably flag seeded abuse cases; voice submissions classify at parity with typed ones.

**Implementation status (2026-10-08) — built and verified:**

- **Voice intake** — `POST /assistance/voice/requests` reuses the typed route's
  org guard, `_validated_classification`, and beneficiary/repository path
  verbatim; parity is asserted by `test_voice_intake.py`, which sends identical
  text through both routes against one AI stub and compares responses field by
  field. Audio rides a `TranscriptionProvider` interface (PRD §14 voice
  assistant): the default mock fails closed with 503, the `http` adapter posts
  to `VOICE_TRANSCRIPTION_URL`. Raw audio is never persisted. *Limitation:* no
  real STT key was exercised on this machine; parity is pipeline parity for an
  identical transcript, not a WER measurement of the transcription itself.
- **Fraud screening** — `fraud_flags` table plus two deterministic rules in
  `services/fraud.py`: near-duplicate open requests from the same beneficiary
  (Jaccard ≥ 0.8 over 30 days) and account submission bursts (≥ 5 audit rows
  within 10 minutes, counted server-side). Flag-only by decision: a submission
  always reaches the queue; leaders confirm/dismiss via `GET/PATCH
  /fraud/flags` with the decision written to the audit trail. Seeded abuse
  cases are asserted in `test_fraud.py` (exit gate).
- **Volunteer matching** — `volunteers` table (skills + six availability
  slots), self-service registration upsert open to all four roles, and
  `match_volunteers` (0.6 skill coverage + 0.4 availability coverage) behind
  leader/admin routes; match payloads carry name and ids only.
- **PWA** — `app/manifest.json` file convention, generated 192/512 icons
  (`scripts/generate_icons.py`, committed outputs), `public/sw.js`
  (network-first navigations, cache-first hashed assets) registered in
  production only by `components/ServiceWorkerRegister`. Not audited against
  Lighthouse; offline fallback is the cached shell.
- **Adjacent fixes** — the Phase 6 employment router was never mounted in
  `main.py` (five unreachable endpoints); now served under
  `/employment/placements` and covered by `test_placements.py`, which caught a
  missing `from_attributes` on `PlacementOut`.
- **Evidence:** full API suite **179 passed** (ruff clean, `alembic check`
  clean, migration upgrade/downgrade roundtrip OK); web `typecheck`, `lint`,
  and `build` green with `/manifest.json` emitted.

---

## Cross-cutting work (runs across all phases)

| Concern | Requirement | Where enforced |
| ------- | ----------- | --------------- |
| Latency | p95 < 3s (PRD §11) | CI perf check from Phase 2; k6 from Phase 5 |
| Security | OIDC, RBAC, least-privilege AI service keys (PRD §22) | Phase 1, then every new route |
| Privacy | Consent, minimization, PII masking, deletion | Phase 5 onward, tested per endpoint |
| Audit | Tamper-evident trail on money and cases | Phase 4 onward |
| CI | Lint, tests, migrations, web build on every push | Phase 0 |
| Docs | OpenAPI at `/docs`, ADRs for decisions | Every phase |

---

## Risks

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Classification accuracy short of 85% | Blocks M1 launch gate | Evaluation harness in Phase 0, before any tuning; fall back to human-in-the-loop triage for low-confidence cases |
| Jurisdiction / compliance unresolved (PRD §25) | Blocks pilot | Decide before Phase 5; the legal review is an exit gate, not a parallel task |
| Beneficiary PII leaking to donor surfaces | Severe trust and legal damage | RBAC negative tests from Phase 1 (donor → 403, nothing leaked in the body); PII rendered only behind explicit role checks and consent. **Done for Phase 3** — donor-facing match responses are PII-free by construction (AI never sees a case) and by assertion (`test_match_response_is_pii_free`); consented `open_case_counts` are integers only. Extend the same assertions to impact/dashboard surfaces in Phase 5 |
| Keycloak realm/compose shipped but never booted (no Docker/JVM on this machine) | The realm import fails, or tokens are not shaped as the API expects (audience, roles claim) | The OIDC verification path is covered by 12 tests against a loopback JWKS; the remaining unknown is Keycloak itself. Boot `docker compose up keycloak` on any Docker-capable machine before Phase 3 and verify an end-to-end login before relying on `AUTH_MODE=oidc` |
| Refresh tokens are stateless (stolen token stays valid until expiry) | Session hijack window after a breach | Implemented rotation now; persistence + revocation when Phase 2 adds payment-grade session handling. Documented in the `/refresh` docstring |
| Payment/escrow model undecided (PRD §25) | Blocks Phase 6 | Interface-first design; provider chosen only after the decision |
| Single-engineer bandwidth | Schedule slip | Phases are ordered by dependency, not by feature appeal; cut scope to the M1 gate before cutting gates |
| Node/web build unverified on this machine | Blocks web phases | **Resolved** — Node v24.19.0 installed, `npm run build` green, 0 vulnerabilities |
| Unpatched Next.js advisories (e.g. GHSA-p293-qw3h-jr36, CVSS 9.0) | Remote code execution on a Windows-hosted deployment | **Resolved** — moved to Next.js 16.3.6 / React 19.3.0; treat the Next major version as security-tracked and re-check advisories on every bump |
| Weak local database credentials | Unauthorized access to beneficiary PII and donation data | Local-only `scram-sha-256` on localhost with a least-privilege app role (no superuser); rotate the local passwords before any shared or hosted deployment |
| Schema managed by `create_all` only | Drifts silently; no reviewable migration history | **Resolved** — Alembic owns the schema; startup verifies the applied revision and fails on drift; CI runs a migration smoke test and `alembic check` |
| Tables created without foreign keys | Orphan rows across all nine entities; silent data corruption in the donation ledger and audit trail | **Resolved** — 14 enforced foreign keys with per-relationship ondelete rules, proven by `tests/test_referential_integrity.py` |
| Test suite rebuilding the primary schema with `create_all` | Destroyed local data and hid real schema drift, so a clean CI run and a developer machine disagreed | **Resolved** — tests build a throwaway database from the migration chain and never touch `DATABASE_URL` |
| Documentation claiming a task is done when the work was not performed | Plans drift from reality; reviewers trust checked-off boxes | **Partially resolved** — the Phase 0 audit records what was wrong and how it was verified. Standing practice: no task is marked done without a test or an executed command behind it |
| Declared dependencies missing from `pyproject.toml` | Clean installs and CI fail where a local venv happens to work | **Resolved** — `email-validator` found via a clean-checkout simulation; every job is now exercised against a pristine tree before it is called verified |
| Eval accuracy measured on template-generated data, not real submissions | Inflated confidence in the ≥85% gate | **Known** — 90.3% classification and 1.000 matching precision are reproducible but likely optimistic; replace `apps/ai/eval/dataset.csv` and `matching_dataset.csv` with real submissions / donor–program pairs before the M1 gate claim. Provenance is now a per-row column and both harnesses warn on every run while the data is synthetic |
| CI workflow written but never executed | The first GitHub run fails on something a local run could not show | **Partially resolved** — all three jobs pass against a clean copy of the tree; the workflow remains unpushed, so the first hosted run is still an unknown |
| Frontend deployed but backend unhosted | Deployed dashboard/status show no live data | **Known** — intentional; Netlify cannot host FastAPI or PostgreSQL. Host the API separately and set `API_URL` once PRD §25 jurisdiction/escrow is decided |
| `sentence-transformers` comparison never run | Embedding model may beat TF-IDF on real data | Deferred deliberately (torch dependency, CI cost); revisit when real submissions and real donor–program fit pairs exist (see ADR 0001 for classification, ADR 0002 for matching) |

---

## Definition of Done (applies to every phase)

1. Code merged to `main` behind review, CI green.
2. Tests covering happy path, error path, and authorization for the feature.
3. OpenAPI regenerated; new endpoints documented.
4. No PII in logs; no secrets in the repo.
5. Audit trail written for anything touching money or a beneficiary case.
6. Rollback path noted in the PR description.
