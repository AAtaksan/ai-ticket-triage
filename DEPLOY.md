# Deploying AI Ticket Triage (free tier)

Goal: turn `localhost` into a public URL anyone can use. Free stack:

- **Render** - runs the API + worker (Docker)
- **Neon** - free cloud Postgres
- **Upstash** - free cloud Redis
- **Groq** - free LLM (you already have a key)

Estimated time: ~20 minutes.

---

## Step 0 - Put your code on GitHub

Render deploys from a Git repo.

```bash
cd ai-ticket-triage
git init
git add .
git commit -m "AI ticket triage system"
```
Create a new empty repo on github.com, then:
```bash
git remote add origin https://github.com/YOUR_USERNAME/ai-ticket-triage.git
git branch -M main
git push -u origin main
```
> Your `.env` is git-ignored, so your secret keys are NOT uploaded. Good.

---

## Step 1 - Free Postgres on Neon

1. Go to https://neon.tech -> sign up (free) -> create a project.
2. Copy the **connection string** (looks like `postgresql://user:pass@ep-xxx.neon.tech/dbname`).
3. Keep it handy - you'll paste it as `DATABASE_URL`.

Our app auto-converts this to the async driver, so paste it exactly as given.

---

## Step 2 - Free Redis on Upstash

1. Go to https://upstash.com -> sign up (free) -> create a Redis database.
2. Copy the **`redis://...` connection URL** (use the one with the password in it).
3. Keep it handy - you'll paste it as `REDIS_URL`.

---

## Step 3 - Deploy on Render (Blueprint)

The repo already contains `render.yaml`, which defines the API + worker.

1. Go to https://render.com -> sign up (free) -> **New + -> Blueprint**.
2. Connect your GitHub and pick the `ai-ticket-triage` repo.
3. Render reads `render.yaml` and shows the services. Click **Apply**.
4. When prompted, fill in the environment variables it marks as "sync: false":
   - `DATABASE_URL` = your Neon string (Step 1)
   - `REDIS_URL`    = your Upstash URL (Step 2)
   - `LLM_PROVIDER` = `groq`
   - `GROQ_API_KEY` = your Groq key
   - (`JWT_SECRET` is auto-generated - leave it)

> Note: `render.yaml` provisions a Render Postgres too. If you prefer Neon,
> delete the `databases:` block from `render.yaml` before applying, and set
> `DATABASE_URL` manually (as above). Either works - pick ONE Postgres.

5. Render builds the Docker images and starts both services. First build ~5 min.

---

## Step 4 - Run migrations (once)

The API's start command already runs `alembic upgrade head` on boot (see
`docker/entrypoint.sh`), so your tables are created automatically on first deploy.

If you ever need to run them manually: Render dashboard -> your API service ->
**Shell** -> `alembic upgrade head`.

---

## Step 5 - Seed demo data (optional)

Render dashboard -> API service -> **Shell**:
```bash
python -m scripts.seed
```

---

## Step 6 - Open your live app

Render gives your API a URL like `https://triage-api.onrender.com`.

- Dashboard: `https://triage-api.onrender.com/`
- API docs:  `https://triage-api.onrender.com/docs`
- Health:    `https://triage-api.onrender.com/health`

Share that link - real users can now sign up and submit tickets.

---

## Notes & gotchas

- **Free tier sleeps.** Render free services spin down after inactivity; the first
  request after idle takes ~30s to wake. Fine for a demo/portfolio.
- **Env vars are secret.** Never commit real keys; set them in the Render dashboard.
- **CORS.** `app/main.py` allows all origins for demo simplicity. For production,
  restrict `allow_origins` to your real domain.
- **Costs.** Groq's free tier + these free hosting tiers = $0 for a portfolio project.
