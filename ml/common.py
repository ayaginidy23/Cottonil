# =============================================================================
# ml/common.py  -  Shared helpers for the ML scripts
# -----------------------------------------------------------------------------
# read_sql():   run a query on PostgreSQL and get a pandas DataFrame
# write_table(): save a DataFrame as a table in schema "gold" (replaced each run)
# Every model writes its results to gold.ml_* tables, so the dashboard and the
# AI assistant can read predictions exactly like any other gold table.
# =============================================================================

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ENGINE = create_engine(
    "postgresql+psycopg://{u}:{p}@{h}:{port}/{db}".format(
        u=os.getenv("POSTGRES_USER"), p=os.getenv("POSTGRES_PASSWORD"),
        h=os.getenv("POSTGRES_HOST", "localhost"), port=os.getenv("POSTGRES_PORT", "5435"),
        db=os.getenv("POSTGRES_DB"),
    )
)


def read_sql(query: str, **params) -> pd.DataFrame:
    with ENGINE.connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


def write_table(df: pd.DataFrame, name: str, comment: str, primary_key: list[str] | None = None):
    """Replace gold.<name> with df, add a COMMENT (read by the AI assistant) and a primary key."""
    with ENGINE.begin() as conn:
        df.to_sql(name, conn, schema="gold", if_exists="replace", index=False, method="multi",
                  chunksize=5000)
        # COMMENT can't use bound parameters, so the text is quoted safely by hand
        safe = comment.replace("'", "''").replace(":", "\\:")
        conn.execute(text(f"COMMENT ON TABLE gold.{name} IS '{safe}'"))
        if primary_key:
            conn.execute(text(f"ALTER TABLE gold.{name} ADD PRIMARY KEY ({', '.join(primary_key)})"))
    print(f"   -> gold.{name}: {len(df):,} rows")


def save_metrics(model: str, metrics: dict):
    """Keep one row per model with its latest evaluation numbers in gold.ml_model_metrics."""
    with ENGINE.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS gold.ml_model_metrics (
                model TEXT, metric TEXT, value NUMERIC, details TEXT,
                trained_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (model, metric))
        """))
        conn.execute(text("DELETE FROM gold.ml_model_metrics WHERE model = :m"), {"m": model})
        for metric, (value, details) in metrics.items():
            conn.execute(text("""INSERT INTO gold.ml_model_metrics (model, metric, value, details)
                                 VALUES (:m, :k, :v, :d)"""),
                         {"m": model, "k": metric, "v": float(value), "d": details})
        conn.execute(text("COMMENT ON TABLE gold.ml_model_metrics IS "
                          "'Evaluation metrics of the ML models (one row per model and metric).'"))
