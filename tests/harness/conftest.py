import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planning"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "decision"))

import pytest


@pytest.fixture(autouse=True, params=["file", "pg"])
def store_kind(request, monkeypatch):
    """Every harness test runs on the file Store and, with TEST_DATABASE_URL, again on PgStore."""
    if request.param == "pg":
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        from harness import PgStore
        import test_dispatch
        url = request.getfixturevalue("pg_url")
        pool = ConnectionPool(url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True)
        request.addfinalizer(pool.close)
        with pool.connection() as conn:  # the owners the server tests sign in as (journeys.user_id is a foreign key)
            conn.execute("INSERT INTO users (id) VALUES (%s), (%s)", ("a" * 32, "b" * 32))
        monkeypatch.setattr(test_dispatch, "STORE", lambda root: PgStore(pool, "test"))
    return request.param
