# =============================================================================
# filters.py  -  The global dashboard filters and how they become SQL
# -----------------------------------------------------------------------------
# Every app shares the same filters (date range, branches, channels).
# Each query in an app YAML declares WHICH column each filter applies to, e.g.
#     columns: {date: f.order_date, branch: f.branch_id, channel: f.sales_channel}
# and writes {where} in its SQL. build_where() turns the filters into a safe
# SQL condition with bound parameters (never string-pasted values).
#
# Supported column keys:
#   date    : a DATE column filtered by day
#   month   : a month_start column (filtered by the months touching the range)
#   branch  : a branch_id column
#   channel : a sales_channel column
# If a query doesn't declare a column, that filter is simply ignored for it.
# =============================================================================

from dataclasses import dataclass, field, replace
from datetime import date, timedelta


@dataclass(frozen=True)
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    branches: tuple[str, ...] = field(default_factory=tuple)
    channels: tuple[str, ...] = field(default_factory=tuple)

    def cache_key(self) -> tuple:
        return (self.date_from, self.date_to, self.branches, self.channels)


def build_where(columns: dict, f: Filters) -> tuple[str, dict]:
    """Return (sql_condition, params). Example:
    ("f.order_date >= %(date_from)s AND f.branch_id = ANY(%(branches)s)", {...})"""
    conds, params = [], {}

    if "date" in columns:
        if f.date_from:
            conds.append(f"{columns['date']} >= %(date_from)s")
            params["date_from"] = f.date_from
        if f.date_to:
            conds.append(f"{columns['date']} <= %(date_to)s")
            params["date_to"] = f.date_to
    elif "month" in columns:
        if f.date_from:
            conds.append(f"{columns['month']} >= date_trunc('month', %(date_from)s::date)")
            params["date_from"] = f.date_from
        if f.date_to:
            conds.append(f"{columns['month']} <= %(date_to)s")
            params["date_to"] = f.date_to

    if "branch" in columns and f.branches:
        conds.append(f"{columns['branch']} = ANY(%(branches)s)")   # ANY(list) = "is in this list"
        params["branches"] = list(f.branches)

    if "channel" in columns and f.channels:
        conds.append(f"{columns['channel']} = ANY(%(channels)s)")
        params["channels"] = list(f.channels)

    return (" AND ".join(conds) if conds else "TRUE"), params


def previous_period(f: Filters) -> Filters | None:
    """Same-length period right before the selected one (for KPI % change).
    Jan-Mar 2026 -> Oct-Dec 2025."""
    if not (f.date_from and f.date_to):
        return None
    length = (f.date_to - f.date_from).days + 1
    prev_to = f.date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=length - 1)
    return replace(f, date_from=prev_from, date_to=prev_to)
