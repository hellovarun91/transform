from __future__ import annotations

import json
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..reports import history, week_scorecard
from . import deps

router = APIRouter()
protected = APIRouter(dependencies=[Depends(deps.require_auth)])

NOTIF_KEYS = ["wake", "whey_am", "breakfast", "lunch", "snack", "gym", "dinner", "magnesium", "log_day", "weekly"]


class SettingsIn(BaseModel):
    protein_target: int | None = Field(default=None, ge=100, le=300)
    notif_enabled: dict[str, bool] | None = None


class TravelIn(BaseModel):
    start: date
    end: date
    on: bool


class SubIn(BaseModel):
    endpoint: str
    keys: dict[str, str]


class UnsubIn(BaseModel):
    endpoint: str


def notif_enabled(store) -> dict[str, bool]:
    raw = store.get_setting("notif_enabled")
    current = json.loads(raw) if raw else {}
    return {k: bool(current.get(k, True)) for k in NOTIF_KEYS}


def _settings_payload(store, plan, settings) -> dict:
    today = deps.today_ist(settings)
    override = store.get_setting("protein_target")
    return {
        "protein_target": int(override) if override else int(plan.meta["protein_target"]),
        "notif_times": plan.notif_times,
        "notif_enabled": notif_enabled(store),
        "vapid_public_key": settings.vapid_public_key,
        "start_date": plan.start_date.isoformat(),
        "start_weight": float(plan.meta["start_weight"]),
        "goal_weight": float(plan.meta["goal_weight"]),
        "calorie_level_today": store.get_calorie_level(today),
        "diet_break": {k: v.isoformat() for k, v in plan.meta["diet_break"].items()},
        "travel_days_upcoming": sorted(d.isoformat() for d in store.travel_days(today, today + timedelta(days=60))),
    }


@router.get("/push/vapid-public-key")
def vapid_key(settings=Depends(deps.get_settings)):
    return {"key": settings.vapid_public_key}


@protected.get("/plan")
def plan_all(plan=Depends(deps.get_plan)):
    return {"days": [deps.plan_dict(plan.weekday_plan(w)) for w in range(7)]}


@protected.get("/plan/{weekday}")
def plan_day(weekday: int = Path(ge=0, le=6), plan=Depends(deps.get_plan)):
    return deps.plan_dict(plan.weekday_plan(weekday))


@protected.get("/history")
def get_history(from_: str | None = Query(default=None, alias="from"), to: str | None = None,
                store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    today = deps.today_ist(settings)
    start = deps.parse_date(from_) if from_ else today - timedelta(days=90)
    end = deps.parse_date(to) if to else today
    if end < start or (end - start).days > 400:
        raise HTTPException(422, "bad range")
    return {"days": history(store, plan, start, end, today)}


@protected.get("/week/{week}")
def get_week(week: str, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    m = re.fullmatch(r"(\d{4})-W(\d{2})", week)
    if not m:
        raise HTTPException(422, "week must look like 2026-W41")
    return week_scorecard(store, plan, int(m.group(1)), int(m.group(2)), deps.today_ist(settings))


@protected.get("/settings")
def get_settings_route(store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    return _settings_payload(store, plan, settings)


@protected.put("/settings")
def put_settings(body: SettingsIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    if body.protein_target is not None:
        store.set_setting("protein_target", str(body.protein_target))
    if body.notif_enabled is not None:
        current = notif_enabled(store)
        current.update({k: v for k, v in body.notif_enabled.items() if k in NOTIF_KEYS})
        store.set_setting("notif_enabled", json.dumps(current))
    return _settings_payload(store, plan, settings)


@protected.put("/travel")
def put_travel(body: TravelIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    if body.end < body.start or (body.end - body.start).days > 60:
        raise HTTPException(422, "bad range")
    store.set_travel(body.start, body.end, body.on)
    return _settings_payload(store, plan, settings)


@protected.get("/export")
def export(store=Depends(deps.get_store)):
    return store.export_all()


@protected.post("/push/subscribe")
def subscribe(body: SubIn, store=Depends(deps.get_store)):
    if "p256dh" not in body.keys or "auth" not in body.keys:
        raise HTTPException(422, "missing keys")
    store.add_subscription(body.endpoint, body.keys["p256dh"], body.keys["auth"])
    return {"ok": True, "count": len(store.list_subscriptions())}


@protected.delete("/push/subscribe")
def unsubscribe(body: UnsubIn, store=Depends(deps.get_store)):
    store.remove_subscription(body.endpoint)
    return {"ok": True}
