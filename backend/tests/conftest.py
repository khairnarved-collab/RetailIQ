"""
Test configuration.

By default tests run against a throw-away SQLite database in a temp folder.
To run them against PostgreSQL instead:

    TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/retailiq_test pytest

The schema is created with the real Alembic migrations (so migrations are
tested too), then a small subset of the synthetic sample data is loaded.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="retailiq_test_"))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{(TMP / 'test.db').as_posix()}")
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use-0123456789"
os.environ["RATE_LIMIT_AUTH_PER_MIN"] = "1000"
os.environ["RATE_LIMIT_ASSISTANT_PER_MIN"] = "1000"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
for d in ("UPLOAD_DIR", "PROCESSED_DIR", "MODEL_DIR", "REPORT_DIR", "SAMPLE_DIR"):
    os.environ[d] = str(TMP / d.lower())

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DEMO_ADMIN = ("admin@retailiq.dev", "Admin@12345")
DEMO_ANALYST = ("analyst@retailiq.dev", "Analyst@12345")


@pytest.fixture(scope="session", autouse=True)
def database():
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    if os.environ["DATABASE_URL"].startswith("postgres"):
        command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    from app.core.config import settings
    from app.database.session import SessionLocal
    from app.services import sample_data
    from app.services.m5_ingestion import IngestOptions, load_m5
    from scripts.seed import seed_customers, seed_users

    settings.ensure_dirs()
    sample_dir = Path(os.environ["SAMPLE_DIR"])
    sample_data.generate(sample_dir / "m5_synthetic")
    sample_data.generate_customers(sample_dir / "customer_transactions_synthetic.csv", n_customers=300)
    sample_data.generate_messy_sales(sample_dir / "messy_sales_sample.csv")
    with SessionLocal() as db:
        seed_users(db)
        load_m5(db, IngestOptions(data_dir=sample_dir / "m5_synthetic", stores=["CA_1", "TX_1", "WI_1"],
                                  items=["FOODS_1_001", "FOODS_3_003", "HOUSEHOLD_1_001", "HOBBIES_1_001",
                                         "FOODS_2_003", "HOBBIES_2_002"]))
        seed_customers(db, None)
    yield
    if os.environ["DATABASE_URL"].startswith("postgres"):
        from app.database.session import engine
        engine.dispose()
        command.downgrade(cfg, "base")


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def _login(client, email, password) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    return _login(client, *DEMO_ADMIN)


@pytest.fixture(scope="session")
def analyst_headers(client):
    return _login(client, *DEMO_ANALYST)


@pytest.fixture()
def db():
    from app.database.session import SessionLocal
    with SessionLocal() as s:
        yield s


@pytest.fixture(scope="session")
def sample_dir() -> Path:
    return Path(os.environ["SAMPLE_DIR"])
