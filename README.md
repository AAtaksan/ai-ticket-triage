# 🎫 AI Support Ticket Triage System

An **asynchronous** backend that ingests support tickets, uses an LLM to classify
them by **category** and **urgency**, and serves agents a clean, prioritized queue —
with caching, rate limiting, retries, live WebSocket updates, and an audit log.

> **Stack:** FastAPI · PostgreSQL · Redis · ARQ worker · Claude/OpenAI · Docker Compose · pytest

---

## The idea in one picture (the pizza restaurant 🍕)

The API is a **waiter**: it takes your ticket and instantly says *"Got it, ticket #42!"*
(~50 ms). It does **not** make you wait while the AI thinks. A **cook** (the background
worker) picks the ticket off the **order rail** (Redis queue) and does the slow AI work.
When it's done, someone **shouts "#42 ready!"** (WebSocket) and the dashboard updates.

```
              POST /tickets
  CLIENT  ───────────────────▶  FASTAPI ("waiter")
     ▲                          • auth (JWT) • rate limit
     │  202 Accepted (~50ms)    • saves ticket → Postgres
     │                          • pushes job  → Redis queue
     │                                 │
     │  ⑧ WebSocket "done!"            ▼
     │                          REDIS (queue + cache + pubsub)
     │                                 │  worker pulls job
     │                                 ▼
     │                          WORKER ("cook") ──▶ LLM (Claude/OpenAI)
     └───────────  saves result ◀──────┘   retries w/ backoff, caches result
                    to Postgres
```

**Why asynchronous?** AI calls take 2–5 s. Doing them inside the request means users
stare at a spinner and the API falls over under load. With a queue, the API answers in
~50 ms and the worker processes at its own pace — 500 tickets arriving at once just
queue up instead of crashing anything.

---

## Features

| Feature | Where | Why it matters |
|---|---|---|
| **Async triage via queue** | `POST /tickets` → ARQ → worker | Fast API, load-resilient |
| **LLM classification** | `app/services/llm.py` | category + urgency + summary + draft reply in one call |
| **Pluggable providers** | anthropic / openai / **groq** / **mock** | Swap LLMs via one env var. `groq` = free + fast; `mock` = run/test with **no API key** |
| **Content-hash caching** | `app/services/triage_service.py` | Identical tickets reuse the answer — free & instant |
| **Retries + backoff** | worker | Survives transient LLM failures; marks `failed` gracefully |
| **Per-user rate limiting** | `app/core/rate_limit.py` | Returns `429`; protects the kitchen |
| **Live updates** | `GET /ws/tickets` + Redis pub/sub | Dashboard updates with no polling |
| **Audit log** | `ai_events` table | Debugging + token/cost/latency tracking |
| **Agent overrides (UI)** | dashboard + `PATCH /tickets/{id}` | Agents override category/urgency, reprocess, or close a ticket from the dashboard |
| **Idempotent processing** | worker overwrites AI fields | Re-processing is safe |
| **Migrations** | Alembic | Versioned schema |
| **Tests** | pytest (SQLite, no infra needed) | Critical paths covered |
| **Dashboard** | `static/index.html` | Visual, prioritized, color-coded queue |

---

## Quick start (Docker — the easy way)

```bash
cp .env.example .env          # defaults use LLM_PROVIDER=mock (no key, no cost)
docker compose up --build     # starts postgres + redis + api + worker
```

- API docs:      http://localhost:8000/docs
- Dashboard:     http://localhost:8000/
- Health:        http://localhost:8000/health

Load demo data (in a second terminal):

```bash
docker compose exec api python -m scripts.seed
# then log into the dashboard as agent@demo.com / password123
```

### Use a real LLM
Edit `.env`:
```
LLM_PROVIDER=anthropic          # or openai
ANTHROPIC_API_KEY=sk-ant-...
```
Then `docker compose up --build` again. Triage uses a cheap, fast model
(Claude Haiku / GPT-4o-mini) — ~$0.001 per ticket.

---

## Running locally without Docker

You need Python 3.11, a Postgres, and a Redis reachable from your machine.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # point DATABASE_URL / REDIS_URL at your services
alembic upgrade head            # create tables
uvicorn app.main:app --reload   # terminal 1: the API
arq app.workers.worker.WorkerSettings   # terminal 2: the worker
```

---

## Try it end to end (curl)

```bash
# 1. register + login
curl -s -X POST localhost:8000/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"password123"}'

TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"password123"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. submit a ticket → 202 instantly
curl -s -X POST localhost:8000/tickets \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"subject":"Charged twice!","body":"Two $29 charges this month."}'

# 3. a few seconds later, fetch it → triaged with category + urgency
curl -s localhost:8000/tickets -H "authorization: Bearer $TOKEN"
```

---

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | – | Create an account |
| POST | `/auth/login` | – | Get a JWT |
| POST | `/tickets` | user | Submit a ticket → **202**, AI runs in background |
| GET | `/tickets` | user | List w/ `?status=&category=&sort=-urgency_score&page=&size=` |
| GET | `/tickets/{id}` | user | One ticket (customers: own only) |
| PATCH | `/tickets/{id}` | **agent** | Override AI / change status |
| POST | `/tickets/{id}/reprocess` | **agent** | Re-run triage |
| GET | `/stats` | user | Category counts, avg urgency, cache hit rate, latency, tokens |
| GET | `/health` | – | `{"api","db","redis"}` |
| WS | `/ws/tickets` | – | Live "ticket done" events |

Full interactive docs auto-generated at **`/docs`**.

---

## Data model

- **users** — `id, email, hashed_password, role(customer|agent), created_at`
- **tickets** — `id, user_id, subject, body, status(new→processing→triaged/failed),
  category, urgency_score(1–10), ai_summary, suggested_reply, content_hash, timestamps`
- **ai_events** — `id, ticket_id, event_type(classified|cache_hit|retry|failed),
  model, tokens_used, latency_ms, raw_response(JSONB), created_at`

Indexes on `status`, `urgency_score DESC`, `user_id`, `content_hash` for fast
dashboard queries.

---

## Testing

```bash
pip install -r requirements.txt
pytest
```

Tests run against **in-memory SQLite** and the **mock** LLM provider — no Postgres,
Redis, or API key required. They cover auth, ticket CRUD, auth-scoping (customers
can't see each other's tickets), pagination, the AI-output parser (malformed JSON,
urgency clamping, bad categories), and content-hash normalization.

---

## Load testing

```bash
pip install locust
locust -f locustfile.py --host http://localhost:8000
# open http://localhost:8089
```
Record your real numbers (e.g. *"sustained ~200 req/s on ticket creation, p95 85 ms"*)
for the resume — **real numbers you can defend beat impressive numbers you can't.**

---

## Design decisions & trade-offs (interview cheat-sheet)

- **Why a queue?** AI is slow (2–5 s). The queue decouples fast intake from slow
  processing; the API stays at ~50 ms and absorbs spikes.
- **Why Redis for both queue + cache?** One dependency is simpler to operate at this
  scale. If the queue needed stronger delivery guarantees later, I'd move it to
  RabbitMQ/SQS — and I can explain exactly when that trade-off flips.
- **Worker crashes mid-job?** The job stays in Redis and ARQ re-delivers; the ticket
  was already saved in Postgres before queuing, so nothing is lost.
- **LLM provider down?** Retry 3× with exponential backoff, then mark `failed` and keep
  the ticket visible — graceful degradation, not data loss. Agents can `/reprocess`.
- **Same ticket processed twice?** Processing is **idempotent** — it overwrites the AI
  fields, so the end state is identical. No duplicates.
- **Bad AI output?** The worker validates JSON against a Pydantic schema (and clamps
  urgency to 1–10). Invalid output triggers a retry instead of corrupting the DB.
- **Scaling to 1M tickets/day?** API is stateless (scale horizontally behind a LB); run
  more worker processes on the same queue; add Postgres read replicas; the cache
  absorbs duplicate content.

---

## Project layout

```
app/
  core/        config, db engine, security (JWT+bcrypt), redis, logging, rate limit
  models/      SQLAlchemy models (User, Ticket, AIEvent) + enums
  schemas/     Pydantic request/response + the TriageResult AI contract
  services/    llm providers, triage pipeline, parser, hashing, queue, deps
  routers/     auth, tickets, stats, health, websocket
  workers/     ARQ worker settings + job
  main.py      FastAPI app + lifespan (starts the pub/sub → WS relay)
alembic/       migrations (0001_initial creates all tables)
tests/         pytest suite (SQLite + mock LLM)
static/        single-page dashboard
scripts/       seed.py demo data
docker/        entrypoint (waits for DB, migrates, starts API)
```

---

## Deploy it online (free)

Want a public URL real users can hit? See **[DEPLOY.md](DEPLOY.md)** - a step-by-step
guide using Render (API + worker), Neon (Postgres), Upstash (Redis), and Groq (LLM),
all on free tiers.

## Roadmap / stretch goals

- Semantic duplicate detection (embeddings) for *similar* — not just identical — tickets
- Admin cost dashboard charting daily token spend from `ai_events`
- Email ingestion webhook so tickets arrive from a real mailbox

---

*Built following a 4-week plan. `LLM_PROVIDER=mock` means you can clone, `docker compose up`,
and see the whole thing work in under 5 minutes — no API key required.*
