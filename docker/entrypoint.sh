#!/usr/bin/env bash
set -e

# Wait for Postgres to be reachable, then run migrations, then start the API.
echo "Waiting for Postgres..."
python - <<'PY'
import asyncio, os, sys
import asyncpg

url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")

async def wait():
    for i in range(30):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            print("Postgres is up.")
            return
        except Exception as e:
            print(f"  ...not ready ({e}); retrying")
            await asyncio.sleep(1)
    print("Postgres never came up", file=sys.stderr)
    sys.exit(1)

asyncio.run(wait())
PY

echo "Running migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
