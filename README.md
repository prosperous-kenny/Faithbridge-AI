# FaithBridge AI

AI-powered social impact platform that helps faith-based organizations identify community needs, prioritize assistance, match donors with beneficiaries, and measure real-world impact.

Full product requirements: [`docs/PRD.md`](docs/PRD.md)

## Repository layout

```
apps/
  web/   Next.js web application (frontend)
  api/   FastAPI backend (beneficiaries, donations, dashboards)
  ai/    FastAPI AI service (need classification, urgency scoring, donor matching)
infra/
  docker-compose.yml   Local PostgreSQL + Redis
docs/
  PRD.md               Product requirements document
```

## Quickstart (Python services)

Prerequisites: Python >= 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e "./apps/api[dev]" -e "./apps/ai[dev]"
```

### Run the AI service

```bash
uvicorn faithbridge_ai.main:app --reload --port 8200
```

Health check: <http://localhost:8200/health>

Post `{ "text": "I lost my job and cannot afford rent this month." }` to `/classify` to see category, urgency score, and priority.

### Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive docs: <http://localhost:8000/docs>

### Run the tests

```bash
python -m pytest apps/api/tests apps/ai/tests
```

## Web application

The Next.js app in `apps/web` requires Node.js >= 18. Once available:

```bash
cd apps/web
npm install
npm run dev
```

## Local infrastructure

```bash
docker compose -f infra/docker-compose.yml up -d
```

## Services overview

| Service | Port | Purpose |
| ------- | ---- | ------- |
| API | 8000 | Core domain API (auth, assistance, donations, dashboard) |
| AI | 8200 | Classification, urgency scoring, donor matching |
| Web | 3000 | User-facing web application |
| Postgres | 5432 | Primary datastore |
| Redis | 6379 | Cache / async job broker |

## Status

Initial version (v0.1) — skeleton with PRD, working Python services, and web scaffold. See `docs/PRD.md` §23 for the roadmap.