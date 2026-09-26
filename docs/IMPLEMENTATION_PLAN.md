# FaithBridge AI — Implementation Plan

Derived from `docs/PRD.md`. Ordered phases, each with concrete outputs and an exit gate that must pass before the next phase starts.

Estimates assume one full-time engineer. Phases 1–5 total ~12–13 weeks (PRD §23 M0–M1). If Phase 0 accuracy comes in below target, add ~2 weeks to Phase 2.

---

## Current state (start of Phase 0)

Already built and verified:

| Asset | Status |
| ----- | ------ |
| Monorepo layout (`apps/api`, `apps/ai`, `apps/web`, `infra`, `docs`) | Done |
| FastAPI API with health/auth/assistance/donations/dashboard route stubs | Done |
| Rule-based need classifier + urgency scoring (`apps/ai/faithbridge_ai/classifier.py`) | Done, placeholder quality |
| AI service endpoints `/health`, `/classify`, `/match` | Done |
| Test suite (8 tests passing) | Done |
| Next.js 14 + TypeScript + Tailwind scaffold | Scaffolded only, no Node installed |
| PostgreSQL + Redis via `infra/docker-compose.yml` | Compose file only, not wired to app |
| PRD, this plan, public GitHub repo | Done |

Not started: persistence, real authentication, ML models, async workers, dashboards, payments.

---

## Phase 0 — Spike & Foundation (2 weeks)

**Goal:** De-risk the two unknowns that gate everything downstream: classification accuracy and the persistence/auth stack.

**Tasks**

1. Install Node.js (LTS) so `apps/web` builds in CI; get `npm run build` green on the existing scaffold.
2. Stand up local infra (`docker compose -f infra/docker-compose.yml up -d`) and verify connectivity from the API.
3. Add SQLAlchemy 2.0 (async) + Alembic; create migrations for all nine entities in PRD §20.
4. Replace the rule-based classifier with a real baseline: TF-IDF + linear model, then evaluate against an embedding model (sentence-transformers) and pick the winner.
5. Build the evaluation harness *before* tuning, so accuracy claims are measurable.
6. Add CI (GitHub Actions): ruff lint, pytest, `next build`, migration smoke test.

**Concrete outputs**

- `apps/api/app/db/{base,session,models}.py` — all nine tables, FKs, `created_at`/`updated_at`, audit columns
- `apps/api/alembic/` — initial migration, reversible up/down
- `apps/ai/faithbridge_ai/models/` — baseline + embedding classifier behind one interface
- `apps/ai/eval/dataset.csv` — 200 labeled real-world need statements across the six categories
- `apps/ai/eval/evaluate.py` — per-category precision/recall + confusion matrix
- `apps/ai/eval/report.md` — accuracy by model, chosen model, error analysis
- `.github/workflows/ci.yml`
- `docs/adr/0001-model-selection.md`

**Exit gate**

- Classification accuracy ≥ 85% on a held-out split, with per-category report showing no category below 70%
- `alembic upgrade head` then `downgrade base` both succeed
- CI green on a clean checkout

---

## Phase 1 — Data Layer & Authentication (2 weeks)

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
| Beneficiary PII leaking to donor surfaces | Severe trust and legal damage | RBAC negative tests from Phase 1, plus an explicit PII-absence test on every donor-facing response in Phases 3 and 5 |
| Payment/escrow model undecided (PRD §25) | Blocks Phase 6 | Interface-first design; provider chosen only after the decision |
| Single-engineer bandwidth | Schedule slip | Phases are ordered by dependency, not by feature appeal; cut scope to the M1 gate before cutting gates |
| Node/web build unverified on this machine | Blocks web phases | Install Node LTS first thing in Phase 0 |

---

## Definition of Done (applies to every phase)

1. Code merged to `main` behind review, CI green.
2. Tests covering happy path, error path, and authorization for the feature.
3. OpenAPI regenerated; new endpoints documented.
4. No PII in logs; no secrets in the repo.
5. Audit trail written for anything touching money or a beneficiary case.
6. Rollback path noted in the PR description.
