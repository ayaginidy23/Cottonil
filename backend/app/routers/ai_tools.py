# =============================================================================
# routers/ai_tools.py  -  AI features for management (besides the analyst chat)
#   GET  /api/insights                 -> Insight Scout cards (EN + AR)
#   POST /api/analyst/report           -> Report Agent: topic -> full bilingual report
#   GET  /api/analyst/report/{id}      -> a saved report (for the PDF page)
#   GET  /api/security/events          -> latest security events of the assistants
#   GET  /api/security/summary         -> counts per kind / per day
#   GET/POST /api/offers, PATCH/DELETE /api/offers/{id} -> manage the offers (Offers page)
# ("Explain this page" lives in routers/apps.py: POST /api/apps/{id}/explain)
# =============================================================================

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .. import promotions, security_log
from ..chat import insight_scout, memory, report_agent
from .chat import _ai_error

router = APIRouter(prefix="/api", tags=["ai tools"])


@router.get("/insights")
def insights(refresh: bool = False):
    try:
        return insight_scout.scout(refresh)
    except Exception as e:
        raise _ai_error(e)


class ReportRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    client_id: str = Field(default="", max_length=64)


@router.post("/analyst/report")
def create_report(req: ReportRequest):
    try:
        return report_agent.make_report(req.topic, memory.owner_key("analyst", req.client_id))
    except ValueError as e:                         # the model did not return valid JSON
        raise HTTPException(502, f"The AI did not return a valid report, please try again ({e})")
    except Exception as e:
        raise _ai_error(e)


@router.get("/analyst/report/{report_id}")
def read_report(report_id: str):
    report = report_agent.get_report(report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/security/events")
def security_events(limit: int = 200):
    return security_log.recent_events(limit)


@router.get("/security/summary")
def security_summary(days: int = 30):
    return security_log.summary(max(1, min(days, 365)))


# ---------------------------------------------------------------------------
# Offers (management)
# ---------------------------------------------------------------------------
class OfferIn(BaseModel):
    title_en: str = Field(min_length=3, max_length=120)
    title_ar: str = Field(min_length=3, max_length=120)
    scope: Literal["category", "audience", "order"]
    target: str | None = Field(default=None, max_length=80)
    min_units: int = Field(default=1, ge=1, le=1000)
    discount_pct: float = Field(gt=0, le=0.7)          # 0.15 = 15%
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def check(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must be after starts_on")
        if self.scope != "order" and not self.target:
            raise ValueError("choose the category / audience")
        if self.scope == "order":
            self.target = None
        else:
            self.min_units = 1
        return self


class OfferActive(BaseModel):
    active: bool


@router.get("/offers")
def list_offers():
    return {"offers": promotions.all_offers(), **promotions.targets()}


@router.post("/offers")
def add_offer(o: OfferIn):
    return promotions.create_offer(o.model_dump())


@router.patch("/offers/{promo_id}")
def pause_offer(promo_id: int, body: OfferActive):
    row = promotions.set_active(promo_id, body.active)
    if not row:
        raise HTTPException(404, "Offer not found")
    return row


@router.delete("/offers/{promo_id}")
def remove_offer(promo_id: int):
    promotions.delete_offer(promo_id)
    return {"deleted": promo_id}
