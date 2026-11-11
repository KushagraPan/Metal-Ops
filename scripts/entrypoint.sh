#!/bin/sh
set -e

echo "Waiting for database to be ready..."
python - << 'EOF'
import os
import sys
import time
from sqlalchemy.engine import make_url

url = os.getenv("DATABASE_URL")
if not url:
    print("DATABASE_URL not set, continuing.")
    sys.exit(0)

u = make_url(url)
if u.get_backend_name() != "postgresql":
    print(f"Backend is {u.get_backend_name()}, continuing.")
    sys.exit(0)

host = u.host or "127.0.0.1"
port = u.port or 5432
user = u.username or "postgres"
password = u.password or ""
dbname = u.database or "postgres"

start = time.time()
while time.time() - start < 45:
    try:
        import psycopg
        conn = psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            connect_timeout=2,
        )
        conn.close()
        print(f"PostgreSQL is ready at {host}:{port}/{dbname}")
        sys.exit(0)
    except Exception as err:
        time.sleep(1)

print("Timed out waiting for PostgreSQL", file=sys.stderr)
sys.exit(1)
EOF

echo "Applying Alembic migrations..."
alembic upgrade head

if [ "${SEED_DEMO}" = "1" ]; then
    echo "SEED_DEMO=1 detected: inserting demo seed data..."
    python -m app.seed
fi

echo "Starting application with 1 worker..."
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 1

