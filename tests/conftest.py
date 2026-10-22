"""Shared test setup: a throw-away PostgreSQL database for each test that needs one."""
import uuid

import pytest
from sqlalchemy import create_engine, text

from ingestion import db
from ingestion.config import load_settings


@pytest.fixture
def engine():
    """A brand-new empty database inside the Docker PostgreSQL, dropped again after the test.
    Your real data in the main database is never touched."""
    try:
        settings = load_settings()
    except RuntimeError:
        pytest.skip(".env is missing")
    name = f"test_bronze_{uuid.uuid4().hex[:10]}"
    admin = create_engine(settings.url("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception:
        pytest.skip("PostgreSQL is not reachable (is the Docker container running?)")
    test_engine = db.get_engine(settings, database=name)
    yield test_engine
    test_engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()
