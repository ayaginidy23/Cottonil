# =============================================================================
# routers/apps.py  -  List the dashboard apps and run one with filters
# =============================================================================

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..engine import clear_cache, run_app
from ..filters import Filters
from ..registry import APPS, reload_apps

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


@router.post("/reload")
def reload():
    """Re-read the YAML files and clear the cache (handy while editing apps)."""
    reload_apps()
    clear_cache()
    return {"apps": len(APPS)}
