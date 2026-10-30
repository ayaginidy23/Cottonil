# =============================================================================
# build_silver.py  -  Run sql/build_silver.sql step by step and log each table
# -----------------------------------------------------------------------------
# The cleaning logic itself is written in SQL (sql/build_silver.sql) because the
# data is already inside Postgres: transforming it there is much faster than
# pulling 1M+ rows into pandas and pushing them back.
# =============================================================================

import time

from psycopg import sql

from db_utils import SQL_DIR, get_connection, log_step, new_run_id, now_utc, split_sql_steps

# Phase 1 (types, dates, keys) then phase 2 (decisions from docs/cleaning_decisions.md)
SQL_FILES = [SQL_DIR / "build_silver.sql", SQL_DIR / "silver_fixes.sql"]
NON_TABLE_STEPS = {"setup", "analyze"}      # steps that don't build a table
# steps named "fix_..." change existing tables -> no bronze/silver row comparison


def count_rows(conn, schema: str, table: str) -> int:
    return conn.execute(
        sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(schema, table))
    ).fetchone()[0]


def main():
    steps = []
    for f in SQL_FILES:
        steps += split_sql_steps(f.read_text(encoding="utf-8"))
    run_id = new_run_id()
    print(f"Run id: {run_id}  |  {len(steps)} steps from {', '.join(f.name for f in SQL_FILES)}\n")

    total_start = time.time()
    failed = 0
    with get_connection() as conn:
        for i, (name, code) in enumerate(steps, start=1):
            print(f"[{i}/{len(steps)}] {name:<36}", end=" ", flush=True)
            started = now_utc()
            try:
                with conn.transaction():            # all-or-nothing for this step
                    conn.execute(code)

                if name in NON_TABLE_STEPS or name.startswith("fix_"):
                    print("OK")
                    continue

                rows_bronze = count_rows(conn, "bronze", name)
                rows_silver = count_rows(conn, "silver", name)
                status = "SUCCESS" if rows_bronze == rows_silver else "MISMATCH"
                log_step(conn, run_id, "silver", name, f"bronze.{name}", rows_bronze,
                         rows_silver, status, None, started, now_utc())
                print(f"{rows_silver:>10,} rows  {status}")

            except Exception as e:
                failed += 1
                log_step(conn, run_id, "silver", name, f"bronze.{name}", None, None,
                         "FAILED", str(e)[:1000], started, now_utc())
                print(f"FAILED: {e}")
                if name == "setup":                 # nothing else can work without the helpers
                    break

    print(f"\nDone in {time.time() - total_start:.1f}s  |  failed steps: {failed}")
    print("Next:  python etl/check_quality.py")


if __name__ == "__main__":
    main()