"""Test setup. Unit tests need nothing. Integration tests (marked `integration`) need
PostgreSQL with pgvector and Redis - `docker compose up -d postgres redis` is enough.

The test database is TEST_DATABASE_URL (default: a `crossexam_test` database next to the dev one).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GEN = Path(os.environ.get("TEST_DATA_DIR", ROOT / "data" / "test_generated"))

os.environ.setdefault("ENV", "test")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL",
                                            "postgresql+psycopg://crossexam:crossexam@localhost:5432/crossexam_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["LLM_PROVIDER"] = "fake"
os.environ["FAKE_LLM_FACTORY"] = "tests.fake_llm:factory"
os.environ["FAKE_GROUND_TRUTH"] = str(GEN / "ground_truth.json")
os.environ["METRICS_EXPORTER"] = "none"
os.environ["OTEL_EXPORTER"] = "none"
os.environ["LOCAL_STORAGE_DIR"] = str(ROOT / "data" / "test_storage")
os.environ["LANGSMITH_TRACING"] = "false"


@pytest.fixture(scope="session")
def generated_data() -> Path:
    if not (GEN / "ground_truth.json").exists():
        subprocess.run([sys.executable, "-m", "datagen.generate", "--shipments", "16", "--ensure-each-problem",
                        "--seed", "11", "--out", str(GEN)], check=True, cwd=ROOT)
    return GEN


def _ensure_database(url: str) -> None:
    import psycopg

    base, name = url.replace("postgresql+psycopg://", "postgresql://").rsplit("/", 1)
    with psycopg.connect(f"{base}/postgres", autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
            conn.execute(f'CREATE DATABASE "{name}"')


@pytest.fixture(scope="session")
def db(generated_data):
    _ensure_database(os.environ["DATABASE_URL"])
    from sqlalchemy import text

    from app.db.session import engine, init_db

    with engine.begin() as conn:  # fresh schema every session
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    init_db()
    from app.db.seed import seed

    seed(str(generated_data / "master.json"))
    import redis

    redis.Redis.from_url(os.environ["REDIS_URL"]).flushdb()
    yield engine


@pytest.fixture(scope="session")
def eager_celery(db):
    from app.workers.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield celery_app
    celery_app.conf.task_always_eager = False
