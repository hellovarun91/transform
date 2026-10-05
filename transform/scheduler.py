from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings
from .db import Store
from .guardrails import catch_up
from .plan import Plan
from .push import send_push
from .reports import week_scorecard

log = logging.getLogger("transform.scheduler")

NUDGE_ITEMS: dict[str, tuple[str | None, str, str]] = {
    # key: (item_key or None for log_day, title, body)
    "wake": ("wake", "Up. Water, coffee, banana at 6:15", "Badminton 6:30. Tick as you go."),
    "whey_am": ("meal:whey_am", "Shake + creatine", "1 scoop Rule1 in water, 5 g creatine."),
    "breakfast": ("meal:breakfast", "Breakfast + multivitamin", "3 eggs + 4 whites, 1 toast, fruit."),
    "lunch": ("meal:lunch", "Lunch + omega-3", "Main, curd, salad. Grain per today's plan."),
    "snack": ("meal:snack", "Snack", "Whey in water + apple or roasted chana."),
    "gym": ("gym", "Gym at 19:00", "Log weights per set. Progression prompts are on the Today screen."),
    "dinner": ("meal:dinner", "Dinner", "Protein + sabzi + salad. No grain."),
    "magnesium": ("supp:magnesium", "Magnesium, then bed by 22:30", "Log your bed time."),
    "log_day": (None, "Log your day", "Unticked items count as missed at midnight."),
}


def _enabled(store: Store, key: str) -> bool:
    raw = store.get_setting("notif_enabled")
    if not raw:
        return True
    return bool(json.loads(raw).get(key, True))


def run_nudge(store: Store, plan: Plan, settings: Settings, key: str, now: datetime) -> bool:
    if key not in NUDGE_ITEMS or not _enabled(store, key):
        return False
    from .api.deps import resolve_day
    today = now.date()
    dp = resolve_day(store, plan, today)
    checks = store.get_checks(today)
    item_key, title, body = NUDGE_ITEMS[key]
    if item_key is None:
        scored = {s.key for s in dp.schedule if s.points > 0} | {f"meal:{k}" for k in dp.scored_meal_keys} | {"sleep"}
        if all(k in checks for k in scored):
            return False
    else:
        valid = {s.key for s in dp.schedule} | {f"meal:{m.key}" for m in dp.meals} | {f"supp:{s['key']}" for s in dp.supplements}
        if item_key not in valid or item_key in checks:
            return False
    send_push(store, settings, title, body, url="/#today", tag=f"nudge-{key}")
    return True


def run_midnight(store: Store, plan: Plan, settings: Settings, now: datetime) -> list[dict]:
    closed = catch_up(store, plan, now.date(), now)
    if closed:
        last = closed[-1]
        title = f"{last['date'].strftime('%a %d %b')}: {last['score']}/100 ({last['grade']})"
        body = last["bump"] or ("Green day. Keep the streak." if last["grade"] == "green" else "Below plan. Today is a fresh 100.")
        send_push(store, settings, title, body, url="/#history", tag="midnight")
    return closed


def run_weekly(store: Store, plan: Plan, settings: Settings, now: datetime) -> dict:
    y, w, _ = now.date().isocalendar()
    sc = week_scorecard(store, plan, y, w, now.date())
    title = f"Week {w}: {sc['avg_score']}/100, {sc['green_days']} green days"
    chg = f"{sc['weight_change']:+.1f} kg" if sc["weight_change"] is not None else "no weigh-ins"
    body = f"{sc['sessions_done']}/6 sessions · protein {sc['protein_avg']} g · {chg} · {sc['verdict'].replace('_', ' ')}"
    send_push(store, settings, title, body, url="/#history", tag="weekly")
    return sc


def build_scheduler(store: Store, plan: Plan, settings: Settings) -> BackgroundScheduler:
    tz = ZoneInfo(settings.tz)
    s = BackgroundScheduler(timezone=tz, job_defaults={"coalesce": True, "misfire_grace_time": 600})

    def safe(fn, *args):
        def run():
            try:
                fn(store, plan, settings, *args, datetime.now(tz))
            except Exception:  # noqa: BLE001
                log.exception("job failed: %s", fn.__name__)
        return run

    for key, hhmm in plan.notif_times.items():
        if key == "weekly":
            continue
        h, m = hhmm.split(":")
        s.add_job(safe(run_nudge, key), CronTrigger(hour=int(h), minute=int(m), timezone=tz), id=f"nudge:{key}")
    wh, wm = plan.notif_times.get("weekly", "21:00").split(":")
    s.add_job(safe(run_weekly), CronTrigger(day_of_week="sun", hour=int(wh), minute=int(wm), timezone=tz), id="weekly")
    s.add_job(safe(run_midnight), CronTrigger(hour=0, minute=5, timezone=tz), id="midnight")
    s.add_job(safe(run_midnight), "date", id="midnight-boot")  # catch up immediately after deploy
    return s
