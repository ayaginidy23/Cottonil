# =============================================================================
#profile.py  -  Data profiling for every file in data/raw
# -----------------------------------------------------------------------------
# Goal: understand the "health" of each table BEFORE cleaning anything:
#   - How many rows / columns? Any fully duplicated rows? Is the main ID unique?
#   - Per column: data type, % missing, number of distinct values
#   - Numeric columns: negatives? zeros? numbers stored as text?
#   - Date columns: which format? (day/month or month/day?)
#   - Text columns: leading / trailing spaces?
# =============================================================================

import argparse          # reads command-line options (e.g. --with-values)
import re                # regular expressions: search for text patterns (e.g. date shapes)
import time              # measure how long each file takes
from pathlib import Path # modern, OS-independent way to handle file paths

import pandas as pd      # the main library for working with tables


# -----------------------------------------------------------------------------
# 1) Paths
# -----------------------------------------------------------------------------
# __file__    = path of this script   ->  D:\cottonil-ai\etl\01_profile.py
# .resolve()  = make it an absolute path
# .parent     = folder of the script  ->  D:\cottonil-ai\etl
# .parent     = one level up          ->  D:\cottonil-ai   (project root)
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"      # "/" joins path parts -> D:\cottonil-ai\data\raw
REPORT_DIR = ROOT / "reports"        # where the reports are saved

# -----------------------------------------------------------------------------
# 2) Date shapes we look for
# -----------------------------------------------------------------------------
# Each shape has a label and a regex. Regex symbols used:
#   ^       = start of text
#   \d{4}   = exactly 4 digits   (e.g. 2023)
#   \d{1,2} = 1 or 2 digits      (e.g. 5 or 12)
#   $       = end of text
DATE_PATTERNS = {
    "YYYY-MM-DD": r"^\d{4}-\d{1,2}-\d{1,2}",     # 2023-10-11
    "SLASH d/m/YYYY": r"^\d{1,2}/\d{1,2}/\d{4}", # 10/11/2023  <- risky: day/month or month/day?
    "YYYY/MM/DD": r"^\d{4}/\d{1,2}/\d{1,2}",     # 2023/10/11
    "YYYY-MM": r"^\d{4}-\d{1,2}$",               # 2018-10     (e.g. year_month)
}

# If a column name contains one of these words, its values should never be negative
NON_NEGATIVE_HINTS = ("qty", "quantity", "units", "price", "amount", "egp", "usd",
                      "cost", "fee", "budget", "spend", "count", "impressions", "clicks")
# Columns where negatives are normal (e.g. selling at a loss) - never flag them
NEGATIVE_OK_HINTS = ("margin", "profit", "variance", "diff", "change")

# Short warning marker (plain ASCII so the Windows terminal can print it)
FLAG = "[!]"


def table_name_from_file(path: Path) -> str:
    """Turn a file name into a clean table name: 'Sales Order Items.csv' -> 'sales_order_items'."""
    name = path.stem.lower()                          # stem = name without extension; lower = lowercase
    name = re.sub(r"[^a-z0-9]+", "_", name)           # anything that is not a letter/digit becomes "_"
    return name.strip("_")                            # remove "_" at the start or end


def read_file(path: Path):
    """Read a CSV or Excel file. For CSV, try the right Arabic-friendly encoding.
    Returns (DataFrame, name of the encoding that worked)."""
    if path.suffix.lower() in (".xlsx", ".xls"):      # suffix = file extension
        return pd.read_excel(path), "excel"

    # utf-8-sig = normal UTF-8, and also handles the hidden marker (BOM) Excel adds at the start
    # cp1256    = the old Windows Arabic encoding; some files come in it
    for enc in ("utf-8-sig", "cp1256"):
        try:
            # low_memory=False -> read the whole column before deciding its type
            # (otherwise pandas may give one column two different types in different chunks)
            return pd.read_csv(path, encoding=enc, low_memory=False), enc
        except UnicodeDecodeError:                    # wrong encoding -> try the next one
            continue
    raise ValueError(f"Could not read {path.name} with any known encoding")


def slash_date_order(values: pd.Series) -> str:
    """For dates like 10/11/2023: decide if they are day/month or month/day.
    Idea: a month can never be > 12. So if the first part is 25, it must be the day."""
    parts = values.str.extract(r"^(\d{1,2})/(\d{1,2})/")   # first and second part as two columns
    first = parts[0].astype(int)
    second = parts[1].astype(int)
    first_over_12 = (first > 12).any()                      # .any() = is at least one value True?
    second_over_12 = (second > 12).any()
    if first_over_12 and not second_over_12:
        return "DD/MM/YYYY (day first)"
    if second_over_12 and not first_over_12:
        return "MM/DD/YYYY (month first)"
    if not first_over_12 and not second_over_12:
        return f"AMBIGUOUS {FLAG} (no part > 12)"
    return f"MIXED {FLAG} (both orders found)"


def detect_date_format(text: pd.Series):
    """Check whether a text column holds dates, and in which shape.
    Returns None if it is not a date column."""
    results = {}
    for label, pattern in DATE_PATTERNS.items():
        share = text.str.match(pattern).mean()   # mean of True/False = share of True
        if share > 0:
            results[label] = share
    if not results or sum(results.values()) < 0.5:   # less than half look like dates -> not a date column
        return None

    best = max(results, key=results.get)             # most common shape
    label = best
    if best == "SLASH d/m/YYYY":
        label = slash_date_order(text[text.str.match(DATE_PATTERNS[best])])
    out = f"{label} [{results[best]:.0%}]"            # :.0% = format as a percentage, no decimals
    if len(results) > 1:
        out += f" {FLAG} multiple shapes: " + ", ".join(f"{k} {v:.0%}" for k, v in results.items())
    return out


def profile_column(table: str, col: str, s: pd.Series, n_rows: int, with_values: bool) -> dict:
    """Compute statistics for ONE column and return them as a dict (one row in the report)."""
    non_null = s.dropna()                                     # only the values that exist
    info = {
        "table": table,
        "column": col,
        "dtype": str(s.dtype),                                # the type pandas guessed
        "nulls": int(s.isna().sum()),                         # number of missing values
        "null_pct": round(s.isna().mean() * 100, 2),          # % missing
        "distinct": int(non_null.nunique()),                  # number of different values
        "distinct_pct": round(non_null.nunique() / max(n_rows, 1) * 100, 2),
        "min": None, "max": None, "mean": None,
        "negatives": None, "zeros": None,
        "numeric_like_text": None,
        "untrimmed": None,
        "date_format": None,
        "top_values": None,
        "warnings": [],                                       # every problem we find goes here
    }

    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        # ---- numeric column ----
        info["min"] = non_null.min() if len(non_null) else None
        info["max"] = non_null.max() if len(non_null) else None
        info["mean"] = round(float(non_null.mean()), 3) if len(non_null) else None
        info["negatives"] = int((non_null < 0).sum())
        info["zeros"] = int((non_null == 0).sum())
        name = col.lower()
        if info["negatives"] and not any(h in name for h in NEGATIVE_OK_HINTS) \
                and any(h in name for h in NON_NEGATIVE_HINTS):
            info["warnings"].append(f"{info['negatives']} negative values in a should-be-positive column")
    else:
        # ---- text column ----
        text = non_null.astype(str)

        # 1) Extra spaces at the start or end: " Cairo" or "Cairo "
        info["untrimmed"] = int((text != text.str.strip()).sum())
        if info["untrimmed"]:
            info["warnings"].append(f"{info['untrimmed']} values with leading/trailing spaces")

        # 2) Is it really numbers, but some "dirty" values made pandas read it as text?
        #    to_numeric(errors="coerce") = convert to numbers; whatever fails becomes NaN
        as_num = pd.to_numeric(text.str.replace(",", "", regex=False), errors="coerce")
        num_share = as_num.notna().mean() if len(text) else 0
        if 0.5 <= num_share < 1:                              # mostly numbers, but not all
            bad = int(as_num.isna().sum())
            info["numeric_like_text"] = bad
            info["warnings"].append(f"looks numeric but {bad} values are not numbers")
        elif num_share == 1 and len(text):
            info["warnings"].append("all numeric but stored as text (probably thousand separators)")

        # 3) Dates? (test on a sample for speed when the column is large)
        sample = text.sample(min(len(text), 200_000), random_state=42) if len(text) else text
        fmt = detect_date_format(sample)
        if fmt:
            info["date_format"] = fmt
            if FLAG in fmt:
                info["warnings"].append("date format needs review")

        # 4) Most frequent values - only for low-cardinality columns (status, channel, ...)
        #    and only when --with-values is passed
        if with_values and 0 < info["distinct"] <= 30:
            vc = text.value_counts().head(5)                  # top 5 values with their counts
            info["top_values"] = " | ".join(f"{k} ({v})" for k, v in vc.items())

    # General warnings for any column type
    if info["null_pct"] > 30:
        info["warnings"].append(f"high missing ({info['null_pct']}%)")
    elif info["nulls"]:
        info["warnings"].append(f"{info['nulls']} missing values")
    if info["distinct"] == 1:
        info["warnings"].append("constant column (single value - probably useless)")

    info["warnings"] = " ; ".join(info["warnings"])           # join into one text cell
    return info


def profile_table(path: Path, with_values: bool):
    """Profile one file. Returns (table summary, list of column rows)."""
    t0 = time.time()
    df, encoding = read_file(path)
    table = table_name_from_file(path)
    n_rows, n_cols = df.shape                                 # shape = (rows, columns)

    # The first column is usually the ID (primary key): it must be unique and never missing.
    # Note: some tables (e.g. monthly_stock) have a key made of several columns together
    # (month + location + category), so False there is normal, not an error.
    pk = df.columns[0]
    pk_ok = df[pk].notna().all() and df[pk].is_unique

    id_cols = [c for c in df.columns if c.lower().endswith("_id")]   # columns linking to other tables

    table_info = {
        "table": table,
        "file": path.name,
        "encoding": encoding,
        "rows": n_rows,
        "cols": n_cols,
        "duplicate_rows": int(df.duplicated().sum()),         # fully duplicated rows
        "pk_column": pk,
        "pk_unique_not_null": bool(pk_ok),
        "pk_duplicates": int(df[pk].duplicated().sum()),
        "id_columns": ", ".join(id_cols),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 1),
        "seconds": None,
    }
    columns = [profile_column(table, c, df[c], n_rows, with_values) for c in df.columns]
    table_info["seconds"] = round(time.time() - t0, 1)
    return table_info, columns


def write_markdown(tables: pd.DataFrame, cols: pd.DataFrame, out: Path):
    """Write an easy-to-read Markdown summary (this is the file to share)."""
    lines = ["# Profiling Summary", ""]
    lines.append("## Tables")
    lines.append(tables.drop(columns=["file"]).to_markdown(index=False))
    lines += ["", "## Warnings (only columns with issues)"]
    cols = cols.fillna("")                                    # so empty cells don't show "nan"
    flagged = cols[cols["warnings"] != ""]
    show = ["table", "column", "dtype", "null_pct", "distinct", "date_format", "warnings"]
    lines.append(flagged[show].to_markdown(index=False) if len(flagged) else "No issues found.")
    lines += ["", "## All columns (type, missing, dates)"]
    show_all = ["table", "column", "dtype", "null_pct", "distinct", "date_format"]
    lines.append(cols[show_all].to_markdown(index=False))
    out.write_text("\n".join(lines), encoding="utf-8")


def main():
    # ---- read command-line options ----
    parser = argparse.ArgumentParser(description="Profile all raw files")
    parser.add_argument("--with-values", action="store_true",
                        help="add top 5 values for low-cardinality text columns")
    args = parser.parse_args()

    REPORT_DIR.mkdir(exist_ok=True)                           # create reports/ if missing
    # data_dictionary is documentation, not data -> skip it
    files = sorted(p for p in RAW_DIR.iterdir()
                   if p.suffix.lower() in (".csv", ".xlsx", ".xls")
                   and "dictionary" not in p.name.lower())
    if not files:
        print(f"No files found in {RAW_DIR}")
        return

    print(f"Found {len(files)} files in {RAW_DIR}\n")
    all_tables, all_cols = [], []
    for i, path in enumerate(files, start=1):
        print(f"[{i}/{len(files)}] {path.name} ...", end=" ", flush=True)
        try:
            t, c = profile_table(path, args.with_values)
            all_tables.append(t)
            all_cols.extend(c)
            print(f"{t['rows']:,} rows | {t['seconds']}s")
        except Exception as e:                                # one bad file should not stop the rest
            print(f"ERROR: {e}")

    tables = pd.DataFrame(all_tables)
    cols = pd.DataFrame(all_cols)

    # utf-8-sig so the reports open correctly (with Arabic) in Excel
    tables.to_csv(REPORT_DIR / "profile_tables.csv", index=False, encoding="utf-8-sig")
    cols.to_csv(REPORT_DIR / "profile_columns.csv", index=False, encoding="utf-8-sig")
    write_markdown(tables, cols, REPORT_DIR / "profile_summary.md")

    print(f"\nDone. Reports saved in: {REPORT_DIR}")
    print("   - profile_tables.csv   (one row per table)")
    print("   - profile_columns.csv  (one row per column)")
    print("   - profile_summary.md   (the file to share)")


# Run main() only when this file is executed directly
# (not when another file imports it)
if __name__ == "__main__":
    main()