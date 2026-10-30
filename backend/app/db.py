# =============================================================================
# db.py  -  Database connection pool + one helper to run queries
# -----------------------------------------------------------------------------
# A connection POOL keeps a few connections open and lends them to requests.
# Opening a new connection for every request is slow (~50 ms); borrowing one
# from the pool is almost free.
# =============================================================================

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

pool = ConnectionPool(
    conninfo=settings.dsn,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},   # every row comes back as a dict: {"column": value}
    open=False,                         # opened when the app starts (see main.py)
)


def fetch_all(query: str, params: dict | None = None) -> list[dict]:
    """Run a SELECT and return all rows as a list of dicts."""
    with pool.connection() as conn:
        return conn.execute(query, params or {}).fetchall()


def fetch_one(query: str, params: dict | None = None) -> dict | None:
    rows = fetch_all(query, params)
    return rows[0] if rows else None
