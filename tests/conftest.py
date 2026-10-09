import os
import uuid

import pytest


@pytest.fixture
def pg_url():
    """A throwaway schema with every migration applied; skipped without TEST_DATABASE_URL (marker pg)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg
    from psycopg.conninfo import make_conninfo
    from db import migrate
    schema = "test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    scoped = make_conninfo(url, options=f"-csearch_path={schema},public")
    migrate(scoped)
    yield scoped
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
