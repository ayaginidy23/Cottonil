# =============================================================================
# registry.py  -  Loads every dashboard app definition from app/apps/*.yaml
# -----------------------------------------------------------------------------
# The "engine" idea: an app is DATA, not code. Each YAML file describes the
# app's KPIs and charts (title, format, SQL). Adding app number 25 = adding one
# YAML file - no new Python, no new React page.
# =============================================================================

import yaml

from .config import settings

REQUIRED_KEYS = {"id", "title", "group"}


def load_apps() -> dict[str, dict]:
    apps = {}
    for path in sorted(settings.apps_dir.glob("*.yaml")):
        with open(path, encoding="utf-8") as fh:
            app = yaml.safe_load(fh)
        missing = REQUIRED_KEYS - app.keys()
        if missing:
            raise ValueError(f"{path.name} is missing keys: {missing}")
        app.setdefault("order", 999)
        app.setdefault("description", "")
        app.setdefault("columns", {})
        app.setdefault("kpis", [])
        app.setdefault("charts", [])
        apps[app["id"]] = app
    # keep the menu order defined in the YAML files
    return dict(sorted(apps.items(), key=lambda kv: (kv[1]["order"], kv[1]["title"])))


APPS: dict[str, dict] = {}


def reload_apps() -> None:
    APPS.clear()
    APPS.update(load_apps())
