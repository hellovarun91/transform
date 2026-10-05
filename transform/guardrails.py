from __future__ import annotations

from datetime import date, datetime, timedelta

from .db import Store
from .plan import DayPlan, Plan
from .scoring import ScoreResult, bed_minutes, score_day

LATE_BED_MINUTES = 24 * 60 + 30
BUMP_DAYS = 7
CATCH_UP_WINDOW_DAYS = 60


def _resolve(store: Store, plan: Plan, d: date) -> DayPlan:
    from .api.deps import resolve_day
    return resolve_day(store, plan, d)


def rescore(store: Store, plan: Plan, d: date) -> ScoreResult:
    dp = _resolve(store, plan, d)
    r = score_day(dp, store.get_checks(d), store.get_rule_breaks(d))
    store.upsert_day(d, mode=dp.mode, score=r.total, grade=r.grade)
    return r


def strength_drop(store: Store, dp: DayPlan) -> list[str]:
    hit: list[str] = []
    for ex in dp.gym_exercises:
        sessions = store.lift_sessions(ex.key, dp.date, limit=3)
        if len(sessions) < 3 or sessions[0]["date"] != dp.date:
            continue
        s0, s1, s2 = (s["top_weight"] for s in sessions)
        if s0 < s1 < s2:
            hit.append(ex.key)
    return hit


def sleep_rule_hit(store: Store, d: date) -> bool:
    for i in range(3):
        c = store.get_checks(d - timedelta(days=i)).get("sleep")
        if not c or not c.value_text:
            return False
        try:
            if bed_minutes(c.value_text) <= LATE_BED_MINUTES:
                return False
        except ValueError:
            return False
    return True


def bump_level(store: Store, d: date, reason: str, level: int = 1, days: int = BUMP_DAYS) -> None:
    for i in range(1, days + 1):
        day = d + timedelta(days=i)
        if store.get_calorie_level(day) < level:
            store.set_calorie_level(day, level, reason)


def apply_sleep_guardrail(store: Store, d: date) -> str | None:
    """Run the late-bedtime rule for day d (callable at close or when a past day's bedtime is logged)."""
    if sleep_rule_hit(store, d):
        reason = "three nights in bed after 00:30; dinner roti added for 7 days"
        bump_level(store, d, reason)
        return reason
    return None


def close_day(store: Store, plan: Plan, d: date, now: datetime) -> dict:
    for key, c in store.get_checks(d).items():
        if key.startswith("meal:") and c.state == "swapped" and not (c.value_text or "").strip():
            store.upsert_check(d, key, "skipped", c.value_num, None)
    r = rescore(store, plan, d)
    store.upsert_day(d, locked_at=now)
    dp = _resolve(store, plan, d)
    bump: str | None = None
    drops = strength_drop(store, dp)
    if drops:
        bump = f"strength dropped two sessions running on {', '.join(drops)}; dinner roti added for 7 days"
    if bump:
        bump_level(store, d, bump)
    else:
        bump = apply_sleep_guardrail(store, d)
    return {"date": d, "score": r.total, "grade": r.grade, "bump": bump}


def catch_up(store: Store, plan: Plan, today: date, now: datetime) -> list[dict]:
    start = max(plan.start_date, today - timedelta(days=CATCH_UP_WINDOW_DAYS))
    rows = {r.date: r for r in store.days_between(start, today - timedelta(days=1))}
    out: list[dict] = []
    d = start
    while d < today:
        row = rows.get(d)
        if row is None or row.locked_at is None:
            out.append(close_day(store, plan, d, now))
        d += timedelta(days=1)
    return out


def progression_prompts(store: Store, dp: DayPlan) -> list[dict]:
    if dp.adaptation or not dp.gym_exercises:
        return []
    out: list[dict] = []
    for ex in dp.gym_exercises:
        if ex.rep_max is None:
            continue
        sessions = store.lift_sessions(ex.key, dp.date - timedelta(days=1), limit=2)
        if len(sessions) < 2:
            continue
        if all(len(s["sets"]) >= ex.sets and all(reps >= ex.rep_max for _, reps, _ in s["sets"]) for s in sessions):
            out.append({"exercise_key": ex.key, "name": ex.name,
                        "message": f"{ex.name}: +2.5 kg today (hit {ex.sets}×{ex.rep_max} twice)"})
    return out
