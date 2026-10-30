# =============================================================================
# db_utils.py  -  Shared helpers used by every ETL script
# -----------------------------------------------------------------------------
# Instead of copying the same connection / logging code into every script,
# we keep it here once and import it:   from db_utils import get_connection
# =============================================================================

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"

load_dotenv(ROOT / ".env")


def get_connection(autocommit: bool = True) -> psycopg.Connection:
    """Open a connection to the project database using the values in .env."""
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5435")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        autocommit=autocommit,
    )


def new_run_id() -> str:
    """A unique id for one pipeline run, e.g. 20261025_201500."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def log_step(conn, run_id, layer, table, source, rows_src, rows_out, status, error,
             started, finished):
    """Insert one row into audit.etl_log (created by load_bronze.py)."""
    conn.execute(
        """
        INSERT INTO audit.etl_log (run_id, layer, table_name, source_file, rows_in_source,
                                   rows_loaded, status, error_message, started_at,
                                   finished_at, seconds)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        (run_id, layer, table, source, rows_src, rows_out, status, error, started, finished,
         round((finished - started).total_seconds(), 2)),
    )


def split_sql_steps(sql_text: str):
    """Split a .sql file into named steps.
    A step starts with a line like:   -- @step: sales_orders
    Returns a list of (step_name, sql_code)."""
    parts = re.split(r"^--\s*@step:\s*(\S+)\s*$", sql_text, flags=re.MULTILINE)
    # re.split with a (group) returns: [before, name1, code1, name2, code2, ...]
    return [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]