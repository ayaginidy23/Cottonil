# =============================================================================
# build_gold.py  -  Run sql/build_gold.sql step by step (star schema + marts)
# =============================================================================

import time

from psycopg import sql

from db_utils import SQL_DIR, get_connection, log_step, new_run_id, now_utc, split_sql_steps

SQL_FILE = SQL_DIR / "build_gold.sql"
NON_TABLE_STEPS = {"setup", "reconciliation", "analyze"}


def main():
    steps = split_sql_steps(SQL_FILE.read_text(encoding="utf-8"))
    run_id = new_run_id()
    print(f"Run id: {run_id}  |  {len(steps)} steps from {SQL_FILE.name}\n")

    total_start = time.time()
    failed = 0
    with get_connection() as conn:
        for i, (name, code) in enumerate(steps, start=1):
            print(f"[{i}/{len(steps)}] {name:<28}", end=" ", flush=True)
            started = now_utc()
            t0 = time.time()
            try:
                with conn.transaction():
                    conn.execute(code)
                if name in NON_TABLE_STEPS:
                    print(f"OK  ({time.time() - t0:.1f}s)")
                    continue
                rows = conn.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier("gold", name))
                ).fetchone()[0]
                log_step(conn, run_id, "gold", name, "silver", None, rows, "SUCCESS", None,
                         started, now_utc())
                print(f"{rows:>10,} rows  ({time.time() - t0:.1f}s)")
            except Exception as e:
                failed += 1
                log_step(conn, run_id, "gold", name, "silver", None, None, "FAILED",
                         str(e)[:1000], started, now_utc())
                print(f"FAILED: {e}")

        # Show the reconciliation results
        recon = conn.execute("""
            SELECT table_name, check_name, failed_rows, details
            FROM audit.data_quality_checks
            WHERE category = 'reconciliation'
            ORDER BY check_id
        """).fetchall()

    print("\nReconciliation (gold vs silver):")
    for table, check, failed_rows, details in recon:
        flag = "PASS" if failed_rows == 0 else "FAIL"
        print(f"  [{flag}] {table:<24} {check:<52} {details or ''}")

    print(f"\nDone in {time.time() - total_start:.1f}s  |  failed steps: {failed}")


if __name__ == "__main__":
    main()