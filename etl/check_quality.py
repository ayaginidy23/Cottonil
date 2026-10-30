# =============================================================================
# check_quality.py  -  Run sql/quality_checks.sql and write a readable report
# -----------------------------------------------------------------------------
# Results are stored in the table audit.data_quality_checks (query it any time
# in pgAdmin) and summarised in reports/quality_report.md.
# The report contains only counts, percentages, category values and date
# =============================================================================

import time

import pandas as pd

from db_utils import ROOT, SQL_DIR, get_connection, split_sql_steps

SQL_FILE = SQL_DIR / "quality_checks.sql"
REPORT = ROOT / "reports" / "quality_report.md"

COLUMNS = ["severity", "category", "table_name", "check_name", "failed_rows",
           "total_rows", "failed_pct", "details"]


def main():
    steps = split_sql_steps(SQL_FILE.read_text(encoding="utf-8"))
    print(f"{len(steps)} steps from {SQL_FILE.name}\n")
    t0 = time.time()

    with get_connection() as conn:
        for i, (name, code) in enumerate(steps, start=1):
            print(f"[{i}/{len(steps)}] {name:<28}", end=" ", flush=True)
            s = time.time()
            try:
                with conn.transaction():
                    conn.execute(code)
                print(f"OK  ({time.time() - s:.1f}s)")
            except Exception as e:
                print(f"FAILED: {e}")       # one broken check must not stop the others

        rows = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM audit.data_quality_checks ORDER BY check_id"
        ).fetchall()

    df = pd.DataFrame(rows, columns=COLUMNS)
    checks = df[~df["category"].isin(["distribution", "date_range"])]
    problems = checks[(checks["failed_rows"] > 0) & (checks["severity"] != "info")]
    passed = checks[(checks["failed_rows"] == 0) & (checks["severity"] != "info")]
    info = checks[checks["severity"] == "info"]

    lines = ["# Data Quality Report", "",
             f"- Rule checks: {len(checks[checks['severity'] != 'info'])}"
             f"  |  passed: {len(passed)}  |  failed: {len(problems)}", ""]
    lines += ["## Failed checks (errors and warnings)",
              problems.drop(columns="details").to_markdown(index=False) if len(problems)
              else "None - all rule checks passed.", ""]
    lines += ["## Info (not errors, useful facts)",
              info.fillna("").to_markdown(index=False), ""]
    lines += ["## Category values",
              df[df["category"] == "distribution"][["table_name", "check_name", "details"]]
              .to_markdown(index=False), ""]
    lines += ["## Date ranges",
              df[df["category"] == "date_range"][["table_name", "check_name", "failed_rows", "details"]]
              .to_markdown(index=False), ""]
    lines += ["## Passed checks", passed[["category", "table_name", "check_name"]]
              .to_markdown(index=False)]

    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nDone in {time.time() - t0:.1f}s")
    print(f"Rule checks passed: {len(passed)}  |  failed: {len(problems)}")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()