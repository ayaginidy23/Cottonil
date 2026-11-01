# =============================================================================
# main.py  -  The FastAPI application (entry point)
# -----------------------------------------------------------------------------
# Run locally (from the backend folder, venv active):
#     uvicorn app.main:app --reload --port 8000
# Then open http://localhost:8000/docs  -> interactive API documentation
# =============================================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import pool
from .registry import reload_apps
from .routers import ai_tools, apps, chat, meta, products


@asynccontextmanager
async def lifespan(_: FastAPI):
    # --- runs once when the server starts ---
    try:
        pool.open(wait=True, timeout=15)        # connect to Postgres
    except Exception:
        # the usual reason: Docker Desktop or the database container is not running
        print("\n" + "=" * 70)
        print(f"Cannot connect to PostgreSQL at {settings.db_host}:{settings.db_port} "
              f"(database '{settings.db_name}').")
        print("Check: 1) Docker Desktop is open  2) the Postgres container is Running")
        print("       3) POSTGRES_HOST / POSTGRES_PORT / POSTGRES_PASSWORD in .env are right")
        print("=" * 70 + "\n")
        raise
    reload_apps()               # read app/apps/*.yaml
    yield
    # --- runs once when the server stops ---
    pool.close()


app = FastAPI(
    title="Cottonil Data & AI API",
    description="Serves the gold layer to the React dashboard, the ML models and the AI assistant.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: the browser blocks a page on localhost:5173 (React) from calling
# localhost:8000 (API) unless the API explicitly allows it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(apps.router)
app.include_router(chat.router)
app.include_router(ai_tools.router)
app.include_router(products.router)