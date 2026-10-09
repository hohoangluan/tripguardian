"""One psycopg connection pool per connection URL, opened on first use."""

import os
import threading

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pools: dict[str, ConnectionPool] = {}
_guard = threading.Lock()


def database_url(readonly: bool = False) -> str:
    """DATABASE_URL (role tg_app) or DATABASE_URL_READONLY (role tg_analytics)."""
    name = "DATABASE_URL_READONLY" if readonly else "DATABASE_URL"
    url = os.environ.get(name, "").strip()
    if not url:
        raise RuntimeError(f"{name} is not set (see .env.example)")
    return url


def pool(url: str | None = None) -> ConnectionPool:
    """Rows come back as dicts. `with pool().connection() as conn:` commits on success, rolls back on error."""
    url = url or database_url()
    with _guard:
        if url not in _pools:
            _pools[url] = ConnectionPool(url, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True)
        return _pools[url]
