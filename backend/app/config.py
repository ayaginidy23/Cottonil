# =============================================================================
# config.py  -  All settings in one place, read from environment variables
# -----------------------------------------------------------------------------
# Locally the values come from the project .env file (POSTGRES_HOST=localhost,
# POSTGRES_PORT=5435). Inside Docker, docker-compose sets POSTGRES_HOST=db and
# POSTGRES_PORT=5432; load_dotenv never overrides variables that already exist,
# so the same code works in both places.
# =============================================================================

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent          # backend/app
ROOT_DIR = APP_DIR.parent.parent                    # project root (where .env lives)

load_dotenv(ROOT_DIR / ".env")


class Settings:
    db_host: str = os.getenv("POSTGRES_HOST", "localhost")
    db_port: int = int(os.getenv("POSTGRES_PORT", "5435"))
    db_name: str = os.getenv("POSTGRES_DB", "cottonil_db")
    db_user: str = os.getenv("POSTGRES_USER", "cottonil")
    db_password: str = os.getenv("POSTGRES_PASSWORD", "")

    # Folder with one YAML file per dashboard app
    apps_dir: Path = APP_DIR / "apps"

    # Which websites may call this API from the browser (the React dev server)
    cors_origins: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")

    @property
    def dsn(self) -> str:
        """Connection string in the format psycopg expects."""
        return (f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
                f"user={self.db_user} password={self.db_password}")


settings = Settings()
