# =============================================================================
# routers/apps.py  -  List the dashboard apps and run one with filters
#   GET  /api/apps                 -> the menu
#   GET  /api/apps/{id}            -> KPIs + charts with the filters
#   POST /api/apps/{id}/explain    -> "Explain this page" (AI summary, EN + AR)
#   POST /api/apps/reload          -> re-read the YAML files
# =============================================================================

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..chat.explain import explain_app
from ..engine import clear_cache, run_app
from ..filters import Filters
from ..registry import APPS, reload_apps
from .chat import _ai_error

router = APIRouter(prefix="/api/apps", tags=["apps"])


@router.get("")
def list_apps():
    """Menu of all apps (no data) - the frontend builds its sidebar from this."""
    return [
        {"id": a["id"], "title": a["title"], "group": a["group"],
         "description": a["description"], "icon": a.get("icon", "chart")}
        for a in APPS.values()
    ]


@router.get("/{app_id}")
def get_app(
    app_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    branch: list[str] = Query(default=[]),     # ?branch=BR001&branch=BR002
    channel: list[str] = Query(default=[]),
):
    """Run one app: returns its KPIs (with % change vs previous period) and chart data."""
    app = APPS.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Unknown app '{app_id}'")
    f = Filters(date_from=date_from, date_to=date_to,
                branches=tuple(sorted(branch)), channels=tuple(sorted(channel)))
    return run_app(app, f)


@router.post("/{app_id}/explain")
def explain(
    app_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    branch: list[str] = Query(default=[]),
    channel: list[str] = Query(default=[]),
):
    """AI summary of the page the user is looking at (same filters), in English and Arabic."""
    app = APPS.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Unknown app '{app_id}'")
    f = Filters(date_from=date_from, date_to=date_to,
                branches=tuple(sorted(branch)), channels=tuple(sorted(channel)))
    try:
        return explain_app(app, f)
    except ValueError as e:
        raise HTTPException(502, f"The AI answer could not be read, please try again ({e})")
    except Exception as e:
        raise _ai_error(e)


@router.post("/reload")
def reload():
    """Re-read the YAML files and clear the cache (handy while editing apps)."""
    reload_apps()
    clear_cache()
    return {"apps": len(APPS)}
