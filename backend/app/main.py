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
from .routers import apps, chat, meta


@asynccontextmanager
async def lifespan(_: FastAPI):
    # --- runs once when the server starts ---
    pool.open(wait=True)        # connect to Postgres
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
