from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, Header, HTTPException, Request

from ..auth import verify_token
from ..config import Settings
from ..db import Store
from ..plan import DayPlan, Plan
from ..scoring import score_day, streak

FREEZE_DAYS = 3  # writes allowed until date + 3 days 00:00 IST


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_plan(request: Request) -> Plan:
    return request.app.state.plan


def require_auth(settings: Settings = Depends(get_settings), authorization: str | None = Header(default=None)) -> None:
    token = authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None
    if not verify_token(settings.secret, settings.pin, token):
        raise HTTPException(401, "unauthorised")


def tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.tz)


def now_ist(settings: Settings) -> datetime:
    return datetime.now(tz(settings))


def today_ist(settings: Settings) -> date:
    return now_ist(settings).date()


def is_frozen(d: date, now: datetime) -> bool:
    cutoff = datetime.combine(d + timedelta(days=FREEZE_DAYS), datetime.min.time(), tzinfo=now.tzinfo)
    return now >= cutoff


def parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, "bad date")


def assert_writable(d: date, settings: Settings) -> None:
    now = now_ist(settings)
    if d > now.date():
        raise HTTPException(400, "cannot log a future day")
    if is_frozen(d, now):
        raise HTTPException(409, "day is frozen")


def resolve_day(store: Store, plan: Plan, d: date) -> DayPlan:
    dp = plan.resolve(d, travel=store.is_travel(d), calorie_level=store.get_calorie_level(d))
    override = store.get_setting("protein_target")
    if override and dp.mode != "travel":
        dp.protein_target = int(override)
    return dp


def valid_item_keys(dp: DayPlan) -> set[str]:
    keys = {s.key for s in dp.schedule} | {"sleep"}
    keys |= {f"meal:{m.key}" for m in dp.meals}
    keys |= {f"ex:{e.key}" for e in dp.court_exercises + dp.gym_exercises + dp.travel_circuit}
    keys |= {f"supp:{s['key']}" for s in dp.supplements}
    return keys


def compute_streak(store: Store, plan: Plan, today: date) -> int:
    start = plan.start_date
    if today <= start:
        return 0
    rows = {r.date: r for r in store.days_between(start, today - timedelta(days=1))}
    grades: list[str] = []
    d = today - timedelta(days=1)
    while d >= start:
        r = rows.get(d)
        grades.append(r.grade if r and r.grade else "red")
        d -= timedelta(days=1)
    return streak(grades)


def plan_dict(dp: DayPlan) -> dict:
    out = asdict(dp)
    out["date"] = dp.date.isoformat()
    return out


def build_day_payload(store: Store, plan: Plan, d: date, settings: Settings, progression=None) -> dict:
    today = today_ist(settings)
    dp = resolve_day(store, plan, d)
    checks = store.get_checks(d)
    breaks = store.get_rule_breaks(d)
    result = score_day(dp, checks, breaks)
    row = store.get_day(d)
    weights = store.get_weights(d, d)
    return {
        "date": d.isoformat(),
        "today": today.isoformat(),
        "frozen": is_frozen(d, now_ist(settings)),
        "plan": plan_dict(dp),
        "checks": {k: {"state": c.state, "value_num": c.value_num, "value_text": c.value_text} for k, c in checks.items()},
        "lifts": [{"exercise_key": l.exercise_key, "set_no": l.set_no, "reps": l.reps, "weight_kg": l.weight_kg}
                  for l in store.get_lifts(d)],
        "rule_breaks": sorted(breaks),
        "score": {"total": result.total, "breakdown": result.breakdown, "grade": result.grade, "protein": result.protein},
        "stored_score": row.score if row else None,
        "streak": compute_streak(store, plan, today),
        "weight": weights[0][1] if weights else None,
        "progression": progression or [],
        "yesterday_sleep_missing": d == today and d > plan.start_date and "sleep" not in store.get_checks(d - timedelta(days=1)),
    }
