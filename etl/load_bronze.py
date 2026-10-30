# =============================================================================
# load_bronze.py  -  Load every raw CSV into PostgreSQL schema "bronze"
# -----------------------------------------------------------------------------
# Bronze layer rules:
#   - Data is loaded EXACTLY as it is in the files (no cleaning at all).
#   - Every column is TEXT, so nothing can fail because of a "bad" value.
#     (Types are fixed later, in the silver layer.)
#   - Two audit columns are added to every table:
#       _source_file : which file the row came from
#       _loaded_at   : when it was loaded
#   - Every run is recorded in audit.etl_log (rows in file vs rows loaded).
#   - The script is re-runnable: each table is dropped and fully reloaded.
#
# Loading uses PostgreSQL COPY, which streams the file straight into the table.
# It is much faster than pandas.to_sql (seconds instead of many minutes).
# =============================================================================

import csv                    
import os                     
import re                     
import time                   
import uuid                   
from datetime import datetime, timezone
from pathlib import Path

import psycopg             
from psycopg import sql       
from dotenv import load_dotenv  


# -----------------------------------------------------------------------------
# 1) Paths and connection settings
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

load_dotenv(ROOT / ".env")   

DB = {
    # We run this script ON THE LAPTOP, so we reach Postgres through the
    # port published by docker-compose (localhost:5435), not "db:5432".
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5435")),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

SCHEMA = "bronze"
CHUNK_SIZE = 1024 * 1024      # send the file to Postgres 1 MB at a time


def clean_name(name: str) -> str:
    """Make a safe, lowercase snake_case name: 'budget_EGP' -> 'budget_egp'.
    Postgres turns unquoted names to lowercase anyway, so using lowercase
    everywhere means we never have to write "quotes" around column names."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def read_header_and_count(path: Path):
    """Return (list of column names, number of data rows) for a CSV file."""
    with open(path, encoding="utf-8-sig", newline="") as f:  
        reader = csv.reader(f)
        header = next(reader)                                  
        n_rows = sum(1 for _ in reader)                        
    return [clean_name(c) for c in header], n_rows


def setup(conn):
    """Create the schemas and the audit log table (only if they don't exist yet)."""
    conn.execute("CREATE SCHEMA IF NOT EXISTS bronze;")
    conn.execute("CREATE SCHEMA IF NOT EXISTS silver;")
    conn.execute("CREATE SCHEMA IF NOT EXISTS gold;")
    conn.execute("CREATE SCHEMA IF NOT EXISTS audit;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit.etl_log (
            log_id         BIGSERIAL PRIMARY KEY,   -- auto-increment number
            run_id         TEXT        NOT NULL,    -- same value for all tables in one run
            layer          TEXT        NOT NULL,    -- bronze / silver / gold
            table_name     TEXT        NOT NULL,
            source_file    TEXT,
            rows_in_source BIGINT,
            rows_loaded    BIGINT,
            status         TEXT        NOT NULL,    -- SUCCESS / MISMATCH / FAILED
            error_message  TEXT,
            started_at     TIMESTAMPTZ NOT NULL,
            finished_at    TIMESTAMPTZ NOT NULL,
            seconds        NUMERIC(10, 2)
        );
    """)


def load_table(conn, path: Path):
    """Drop + recreate one bronze table and COPY the file into it.
    Returns (table_name, rows_in_file, rows_loaded)."""
    table = clean_name(path.stem)
    columns, rows_in_file = read_header_and_count(path)

    # sql.Identifier puts names inside "quotes" safely -> no SQL injection, no typos
    table_id = sql.Identifier(SCHEMA, table)                   # -> "bronze"."sales_orders"
    col_defs = sql.SQL(", ").join(
        sql.SQL("{} TEXT").format(sql.Identifier(c)) for c in columns
    )
    col_list = sql.SQL(", ").join(sql.Identifier(c) for c in columns)

    # conn.transaction(): everything inside either fully succeeds (COMMIT)
    # or is fully undone (ROLLBACK) if any error happens -> no half-loaded tables
    with conn.transaction():
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {};").format(table_id))
        conn.execute(sql.SQL("""
            CREATE TABLE {table} (
                {cols},
                _source_file TEXT        DEFAULT {file},
                _loaded_at   TIMESTAMPTZ DEFAULT now()
            );
        """).format(table=table_id, cols=col_defs, file=sql.Literal(path.name)))

        # COPY ... FROM STDIN = "I will stream the data to you from this program"
        #   FORMAT csv  -> understands commas, quotes, etc.
        #   HEADER true -> skip the first line (column names)
        # We list only the CSV columns, so the two audit columns get their DEFAULT values.
        copy_sql = sql.SQL(
            "COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')"
        ).format(table=table_id, cols=col_list)

        with conn.cursor() as cur:
            with cur.copy(copy_sql) as copy:
                with open(path, "rb") as f:                    # "rb" = read raw bytes
                    while chunk := f.read(CHUNK_SIZE):         # read 1 MB, send it, repeat
                        copy.write(chunk)

        rows_loaded = conn.execute(
            sql.SQL("SELECT COUNT(*) FROM {};").format(table_id)
        ).fetchone()[0]

    return table, rows_in_file, rows_loaded


def log(conn, run_id, table, file, rows_src, rows_loaded, status, error, started, finished):
    """Insert one row into audit.etl_log."""
    conn.execute(
        """
        INSERT INTO audit.etl_log (run_id, layer, table_name, source_file, rows_in_source,
                                   rows_loaded, status, error_message, started_at,
                                   finished_at, seconds)
        VALUES (%s, 'bronze', %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        # %s are placeholders: psycopg fills them safely with these values, in order
        (run_id, table, file, rows_src, rows_loaded, status, error, started, finished,
         round((finished - started).total_seconds(), 2)),
    )


def main():
    files = sorted(p for p in RAW_DIR.glob("*.csv") if "dictionary" not in p.name.lower())
    if not files:
        print(f"No CSV files found in {RAW_DIR}")
        return

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    print(f"Run id: {run_id}")
    print(f"Connecting to {DB['host']}:{DB['port']}/{DB['dbname']} ...")

    # autocommit=True: each statement is saved immediately, unless it is inside
    # a "with conn.transaction()" block (then the whole block is one unit)
    with psycopg.connect(**DB, autocommit=True) as conn:
        setup(conn)
        total_start = time.time()
        failed = 0

        for i, path in enumerate(files, start=1):
            print(f"[{i}/{len(files)}] {path.name:<42}", end=" ", flush=True)
            started = datetime.now(timezone.utc)
            try:
                table, rows_src, rows_loaded = load_table(conn, path)
                status = "SUCCESS" if rows_src == rows_loaded else "MISMATCH"
                log(conn, run_id, table, path.name, rows_src, rows_loaded, status, None,
                    started, datetime.now(timezone.utc))
                print(f"{rows_loaded:>10,} rows  {status}")
            except Exception as e:
                failed += 1
                log(conn, run_id, clean_name(path.stem), path.name, None, None, "FAILED",
                    str(e)[:1000], started, datetime.now(timezone.utc))
                print(f"FAILED: {e}")

    print(f"\nDone in {time.time() - total_start:.1f}s  |  failed tables: {failed}")
    print("Check in pgAdmin:  SELECT * FROM audit.etl_log ORDER BY log_id DESC;")


if __name__ == "__main__":
    main()