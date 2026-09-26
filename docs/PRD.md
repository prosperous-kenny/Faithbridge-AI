# FaithBridge AI
### Transforming Faith-Based Giving into Measurable Community Impact

---

# 1. Executive Summary

FaithBridge AI is an AI-powered social impact platform designed to help faith-based organizations identify community needs, prioritize assistance, connect donors with beneficiaries, and measure the impact of charitable initiatives.

The platform empowers churches, mosques, ministries, charities, and community organizations to make data-driven decisions that maximize the effectiveness of donations and outreach programs.

FaithBridge AI combines artificial intelligence, community data, and faith-driven compassion to create sustainable social impact and stronger communities.

---

# 2. Problem Statement

Faith organizations frequently serve as the first point of support for vulnerable members of society. However, many organizations face challenges such as:

- Limited visibility into real community needs.
- Manual and inefficient aid allocation.
- Lack of transparency in donation utilization.
- Difficulty measuring the impact of charitable activities.
- Limited resources and increasing demand for assistance.
- Inability to predict emerging community challenges.

As a result, resources may not reach the people who need them most, and donors often do not see the direct impact of their contributions.

---

# 3. Vision

To become the leading AI-powered platform that enables faith communities to deliver charitable support more efficiently, transparently, and sustainably.

---

# 4. Mission

Empower faith-based organizations with intelligent tools that transform charitable giving into measurable and life-changing community impact.

---

# 5. Objectives

## Primary Objectives

- Improve identification of community needs.
- Increase efficiency of aid distribution.
- Enhance transparency and accountability.
- Provide measurable social impact metrics.
- Strengthen donor trust and engagement.

## Secondary Objectives

- Support employment and self-sufficiency initiatives.
- Reduce dependency through empowerment programs.
- Improve community resilience.
- Enable data-driven ministry decisions.

---

# 6. Target Users

## Community Members

Individuals seeking assistance such as:

- Food support
- School fees
- Medical assistance
- Housing support
- Employment support

## Donors

Individuals who wish to:

- Make donations
- Sponsor causes
- Support vulnerable families
- Track their impact

## Faith Leaders

Church leaders, pastors, ministry leaders, and administrators who need:

- Community insights
- Donation tracking
- Impact reporting
- Outreach planning

## Charity Organizations

Faith-based NGOs and community support organizations.

---

# 7. Key Use Cases

## Use Case 1: Request Assistance

A community member submits:

> I lost my job and cannot afford rent this month.

The platform captures the request, classifies the need, calculates urgency, and assigns priority.

## Use Case 2: Donate to a Cause

A donor indicates budget, preferred causes, and location. FaithBridge AI recommends beneficiaries and programs that match donor preferences.

## Use Case 3: Community Analysis

Faith leaders view assistance trends, high-need communities, emerging challenges, and donation effectiveness.

## Use Case 4: Impact Reporting

The system automatically generates reports showing families assisted, meals provided, students supported, and job seekers assisted.

---

# 8. Core Features

## Community Needs Submission

- Web Application
- Mobile Application
- WhatsApp
- SMS
- Voice Assistant

## AI Need Classification

Categories:
- Food Assistance
- Education Support
- Medical Assistance
- Employment Support
- Housing Support
- Emergency Relief

## Urgency Scoring Engine

Priority Levels:
- Critical
- High
- Medium
- Low

## Donor Matching Engine

AI matches beneficiaries and programs to donors.

## Employment Empowerment Module

- Job recommendations
- Skills assessment
- Mentorship matching
- Training recommendations

## Community Insights Dashboard

Analytics, donation trends, assistance statistics, and program performance.

## Impact Measurement System

Tracks:
- Families Assisted
- Meals Provided
- School Fees Sponsored
- Medical Cases Supported
- Employment Placements
- Donations Distributed

---

# 9. AI Capabilities

- Natural Language Processing
- Intelligent Classification
- Recommendation Engine
- Impact Forecasting

---

# 10. Functional Requirements

- User Authentication
- Beneficiary Management
- Donation Management
- Reporting and Analytics

---

# 11. Non-Functional Requirements

- Secure Authentication
- Role-Based Access Control
- Response Time < 3 Seconds
- High Availability
- Mobile Accessibility

---

# 12. User Roles

- Community Member
- Donor
- Faith Leader
- System Administrator

---

# 13. Success Metrics

## North Star Metric

- **Families Assisted (cumulative)** — number of households reached through funded assistance.

## Supporting Metrics and KPIs

| Metric | Definition | Initial Target (12 months) |
| ------ | ---------- | -------------------------- |
| Families Assisted | Households that received funded assistance | 1,000 |
| Donations Distributed | Value of funds/materials delivered to beneficiaries | $250,000 |
| Employment Placements | Job seekers placed via the Empowerment Module | 150 |
| Educational Sponsorships | Students with school fees fully covered | 200 |
| Active Users | Monthly active users across all roles | 5,000 |
| Donor Retention | Donors active in consecutive quarters | 40% |
| Average Response Time | API p95 under normal load | < 3 s |
| Donation Distribution Time | Average time from donation to payout | < 7 days |

---

# 14. MVP Scope

## Included (MVP)

- User Registration
- Assistance Submission
- AI Classification
- Donor Matching
- Dashboard
- Impact Reporting

## Phase 2

- Payment/pledge processing and payout orchestration
- Employment Empowerment Module (jobs + mentoring)
- WhatsApp Integration
- Advanced Analytics

## Phase 3

- Voice Assistant
- Fraud Detection
- Volunteer Matching
- Mobile Application

---

# 15. AI Community Impact Score

Community Impact Score evaluates:

- Families Supported
- Education Outcomes
- Employment Success
- Food Security
- Healthcare Support

Example:

> Community Impact Score: 82/100

Formula (MVP baseline, weights configurable per organization):

```
Impact Score = 0.25 * Families Supported
            + 0.20 * Education Outcomes
            + 0.20 * Employment Success
            + 0.20 * Food Security
            + 0.15 * Healthcare Support
```

---

# 16. Expected Outcomes

- Greater transparency
- Better resource allocation
- Faster assistance delivery
- Stronger faith-based outreach
- Sustainable community development

---

# 17. Elevator Pitch

FaithBridge AI is an intelligent social impact platform that empowers faith-based organizations to identify community needs, prioritize assistance, match donors with beneficiaries, and measure real-world impact. By combining artificial intelligence with faith-driven compassion, the platform helps communities maximize every donation and create sustainable change.

---

# 18. Proposed Technology Stack

| Layer          | Technology                                          | Rationale                                        |
| -------------- | --------------------------------------------------- | ------------------------------------------------ |
| Frontend       | Next.js 16 (React 19, TypeScript, Tailwind CSS)     | SSR + fast UX, one deployable for web/mobile-web |
| Backend API    | Python 3.12 + FastAPI + SQLAlchemy 2 (asyncpg)       | Typed, async, auto-generated OpenAPI docs        |
| AI Service     | Python + scikit-learn / sentence-transformers       | Classification + embeddings + matching           |
| Database       | PostgreSQL 16 (local dev: installed, username/password auth) | Relational integrity for donations/beneficiaries |
| Cache/Queues   | Redis (cache), Celery (async jobs)                 | Urgency scoring + notifications                  |
| Object Storage | S3-compatible storage                               | Uploads (documents, receipts)                    |
| Auth           | Auth0 or Keycloak (+ JWT)                           | OIDC, role-based access control                  |
| Infra          | Local PostgreSQL 16 (dev) → ECS/Fly.io (prod)       | Portable to any cloud provider                   |
| Monitoring     | Grafana + Prometheus + Sentry                       | Observability                                    |

**Verified local development baseline (as of the initial wiring milestone)**

| Component      | Version / State                                                |
| -------------- | -------------------------------------------------------------- |
| Node.js        | v24.19.0 (LTS), npm 11.17.0                                     |
| Next.js        | 16.3.6 with React 19.3.0 — 0 known npm vulnerabilities          |
| PostgreSQL     | 16.15, Windows service `postgresql-x64-16`, localhost:5432     |
| Database auth  | `scram-sha-256` username/password on localhost                 |
| Python         | 3.14.7 in `.venv`; 12 tests passing (API + AI services)        |
| Frontend build | `npm run build` succeeds; dev server returns HTTP 200           |

Note: Next.js 14 was originally specified, but the 14.x line carries unpatched
advisories (including GHSA-p293-qw3h-jr36, CVSS 9.0). The stack moved to
Next.js 16 to keep the vulnerability count at zero. `infra/docker-compose.yml`
is retained for teams that prefer containerized Postgres; local development
currently uses the natively installed service.

Language/framework versions are baseline recommendations and may be adjusted during implementation spikes.

---

# 19. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                            Client                            │
│   Web App (Next.js)   ·   Mobile (PWA/React Native)   ·   API │
└───────────────────────────────┬─────────────────────────────┘
                                │ HTTPS / JWT
┌───────────────────────────────▼─────────────────────────────┐
│                      API Gateway / Auth (OIDC)               │
└───────────────────────────────┬─────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼────────┐     ┌────────▼────────┐     ┌────────▼────────┐
│  Core API       │     │  AI Service     │     │  Worker (Celery)│
│  FastAPI        │     │  Classification  │     │  - Urgency jobs │
│  - Beneficiaries│     │  - Matching      │     │  - Reports      │
│  - Donations    │     │  - Forecasting   │     │  - Notifications│
│  - Programs     │     └─────────────────┘     └─────────────────┘
└────────┬────────┘
         │
┌────────▼───────────────────────────────────────┐
│       PostgreSQL · Redis · Object Storage      │
│              (SQL, cache, files)               │
└────────────────────────────────────────────────┘
```

# 20. Data Model (v0)

Core entities, with key relations for MVP:

- **users** — auth identity, role (community_member / donor / faith_leader / admin), org id.
- **organizations** — churches, mosques, ministries, NGOs.
- **beneficiaries** — assisted individuals/families; PII link to users where consent exists.
- **assistance_requests** — submitted needs; holds `category`, `urgency_score`, `priority`, `status`.
- **programs** — outreach initiatives (e.g., food bank, school fees).
- **donations** — pledges and payments; amount, donor id, program/beneficiary target, payout status.
- **placements** — employment/mentorship outcomes record.
- **impact_events** — time-series feed that powers dashboards and the Impact Score.
- **audit_logs** — immutable trail for donations and case management.

Every table includes `created_at` / `updated_at`; donations and assistance_requests include audit columns for transparent reporting.

---

# 21. API Outline (v0)

| Method | Path                                  | Purpose                              |
| ------ | ------------------------------------- | ------------------------------------ |
| POST   | `/auth/register`, `/auth/login`       | Authentication (OIDC-backed)         |
| POST   | `/assistance/requests`                | Submit a need (free text → classify) |
| GET    | `/assistance/requests`                | List/filter requests by priority     |
| PATCH  | `/assistance/requests/{id}/status`    | Update lifecycle (approved/fulfilled)|
| POST   | `/ai/classify`                        | AI classification + urgency score    |
| POST   | `/ai/match-donors`                    | Return ranked donor matches          |
| GET    | `/donations`                          | Donation ledger/impact per donor     |
| GET    | `/dashboard/community-insights`       | Aggregated analytics                 |
| GET    | `/dashboard/impact-report`            | Impact Score + report data           |

Full OpenAPI spec is generated automatically by FastAPI at `/docs`.

---

# 22. Privacy, Security & Compliance

Sensitive data handled: beneficiary PII, financial need details, medical information, donation records.

- **Encryption** — AES-256 at rest; TLS 1.2+ in transit.
- **AuthN/AuthZ** — OIDC login; role-based access control; least-privilege API keys for the AI service.
- **Data minimization** — collect only fields necessary for the request; beneficiaries may edit or request deletion.
- **Consent** — explicit consent captured before PII is shared with donors or partner organizations.
- **Donor visibility** — PII of beneficiaries is never exposed to donor-facing endpoints.
- **Immutable audit trail** — donations and case handling logged; tamper-evident.
- **Compliance** — align with local data-protection law (e.g., GDPR or regional equivalents); legal review before any beneficiary data leaves an organization's jurisdiction.
- **Fraud controls (Phase 3)** — duplicate-request detection on top of audit data.

---

# 23. Roadmap (Sequenced)

| Milestone | Scope | Est. Duration |
| --------- | ----- | ------------- |
| M0 — Spike | Validate stack, AI classification accuracy on sample data | 2 weeks |
| M1 — MVP | Auth, assistance submission, AI classification, donor matching, dashboard, impact reporting | 10–12 weeks |
| M2 — Phase 2 | Payments/payouts, employment module, WhatsApp integration, advanced analytics | 8–10 weeks |
| M3 — Phase 3 | Voice assistant, fraud detection, volunteer matching, mobile app | 8–10 weeks |
| M4 — Scale | Multi-org tenancy, impact forecasting at scale, public reports | Ongoing |

Launch gate M1 must meet: p95 API < 3 s, classification accuracy ≥ 85% on the curated validation set, and a signed donor/beneficiary consent flow live.

---

# 24. Funding & Revenue Model (v0 hypothesis)

Not monetized at MVP — the platform is a lower-friction layer for faith organizations.

Candidate models to validate in pilot:
- **SaaS subscription** for organizations (per-month tiered by org size).
- **Platform fee** on facilitating donations/payouts (transparent, disclosed to donors).
- **Sponsored/institutional partnerships** (foundations supporting operating costs).
- **Freemium** core tools with paid analytics/automation tiers.

Decision required from stakeholders before M2. Until then, costs are assumed covered by grant or sponsor funding.

---

# 25. Open Questions

- Who owns beneficiary data long-term — the organization or FaithBridge?
- Should donations be held by FaithBridge or a licensed third party (trust/escrow)?
- Which jurisdiction's data-protection law governs the pilot deployment?
- Is English-only acceptable for MVP, or is multilingual (e.g., Swahili, French) required from day one?

---

# 26. Notes
- I have chosen the tool node.js because next.js that I am using is a react server framework that needs a node runtime
- I have chosen Next.js as a framework because it transforms React from a frontend UI library into a full-stack, production-ready framework. While plain React leaves architecture decisions—like routing, data fetching, and build optimizations—up to the developer, Next.js provides these critical features out of the box
- I have chosen Docker primarily to eliminate the "it works on my machine" problem by bundling an application and all of its dependencies into a single, isolated container. This ensures that the application runs exactly the same way on my laptop, a continuous integration (CI) server, and the production environment or any other person's laptop.
- I told the AI to make changes to the design.htlmml document by making the font of the design more clearer and it did that by adding Google fonts CDN
- We have done phase 0 where by in Phase 0 we've been clearing the two unknowns that gate everything downstream, and we've now retired both of them plus built a working app you can click through. On the toolchain side we installed Node 24.19.0 and discovered the scaffold's Next.js 14.2.5 carried a critical unpatched remote-code-execution advisory that patching within 14.x couldn't fix, so we upgraded to Next.js 16.3.6 with React 19.3.0, which brought npm audit to zero vulnerabilities and a green build. On the data side, because Docker isn't available on your machine, we installed PostgreSQL 16.15 natively as a Windows service using the username/password authentication you asked for, created a dedicated least-privilege faithbridge role and database so the app never runs as superuser, and wired it up through SQLAlchemy's async engine with all nine entities from PRD section 20 created, plus a readiness probe that runs a real query. While seeding test data we found and fixed a genuine bug: columns like donations.currency had Python-side defaults but no database-level defaults, so any insert outside the ORM would crash — that would have bitten us in every future seed script and migration. We also caught a security mistake of our own, where an early version put the database password directly into a tracked source file that was about to be pushed to your public repository; that credential now lives only in a gitignored .env. Finally we built the actual application, separate from our static design preview, with four working routes — a landing page, a dashboard showing live row counts read from PostgreSQL, a status page that health-checks every service, and a request form that classifies a need through the full path from browser to AI service, verified returning housing/65/high — all four pages returning HTTP 200 with 12 of 12 tests passing, committed and pushed.
- The next phase is Phase 1, Data Layer & Authentication, and its purpose is to replace the placeholder auth stub with real, role-enforced security: wiring up an identity provider for local development, giving users the four roles from the PRD (community member, donor, faith leader, admin) tied to their organization, building a require_role guard that every route must pass, implementing actual login, refresh, and JWT verification, and adding a repository layer so route code never touches the database session directly. It passes only when negative tests prove a donor cannot read beneficiary personal data and no endpoint returns PII without an explicit role check. But we don't start it yet, because three items remain in Phase 0: Alembic migrations so the database schema has reviewable history instead of drifting silently, a real classifier plus its evaluation harness to measure whether we can actually hit that 85% accuracy gate, and CI so nothing is unverified on push. Of those, the evaluation harness matters most, because if a real model only reaches something like 62% on genuine need statements, that's a finding that changes the product design — and it's far cheaper to discover now than after building authentication around a classifier that doesn't work. One practical snag: Phase 1 assumes Docker for Keycloak, but Docker isn't installed on this machine and Keycloak has no native Windows build, so we'll need to decide between a lightweight Python JWT service or installing Docker Desktop before we get there.



# Appendix A: Glossary

- **FaithBridge AI** — the platform described in this document.
- **Beneficiary** — an individual or family receiving assistance.
- **Urgency Score** — model output (0–100) mapped to Critical/High/Medium/Low.
- **Community Impact Score** — 0–100 composite metric of impact dimensions (§15).