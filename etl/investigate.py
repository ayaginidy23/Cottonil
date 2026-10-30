# =============================================================================
# investigate.py  -  Run sql/investigations.sql and save every result as Markdown
# =============================================================================

import time

import pandas as pd

from db_utils import ROOT, SQL_DIR, get_connection, split_sql_steps

SQL_FILE = SQL_DIR / "investigations.sql"
REPORT = ROOT / "reports" / "investigation_report.md"


def main():
    steps = split_sql_steps(SQL_FILE.read_text(encoding="utf-8"))
    lines = ["# Investigation Report", ""]

    with get_connection() as conn:
        for i, (name, code) in enumerate(steps, start=1):
            print(f"[{i}/{len(steps)}] {name:<32}", end=" ", flush=True)
            t0 = time.time()
            lines.append(f"## {name}")
            try:
                cur = conn.execute(code)
                cols = [d.name for d in cur.description]   # column names of the result
                df = pd.DataFrame(cur.fetchall(), columns=cols)
                lines.append(df.to_markdown(index=False) if len(df) else "(no rows)")
                print(f"{len(df)} rows  ({time.time() - t0:.1f}s)")
            except Exception as e:
                lines.append(f"FAILED: {e}")
                print(f"FAILED: {e}")
            lines.append("")

    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {REPORT}")


if __name__ == "__main__":
    main()