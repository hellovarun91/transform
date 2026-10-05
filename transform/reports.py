from __future__ import annotations

from datetime import date, timedelta

from .db import Store
from .plan import Plan
from .scoring import protein_total, score_day
from .timeline import corridor_status, moving_average


def _resolve(store: Store, plan: Plan, d: date):
    from .api.deps import resolve_day
    return resolve_day(store, plan, d)


def _live(store: Store, plan: Plan, d: date):
    dp = _resolve(store, plan, d)
    checks = store.get_checks(d)
    return dp, checks, score_day(dp, checks, store.get_rule_breaks(d))


def history(store: Store, plan: Plan, start: date, end: date, today: date) -> list[dict]:
    rows = {r.date: r for r in store.days_between(start, end)}
    out: list[dict] = []
    d = start
    while d <= end:
        row = rows.get(d)
        checks = store.get_checks(d)
        if d > today or d < plan.start_date:
            score = grade = None
            mode = _resolve(store, plan, d).mode
        elif row and row.locked_at is not None:
            score, grade, mode = row.score, row.grade, row.mode
        else:
            dp, checks, r = _live(store, plan, d)
            score, grade, mode = r.total, r.grade, dp.mode
        out.append({"date": d.isoformat(), "score": score, "grade": grade, "mode": mode, "logged": bool(checks)})
        d += timedelta(days=1)
    return out


def _ma7_at(store: Store, d: date) -> float | None:
    series = store.get_weights(d - timedelta(days=13), d)
    if not series:
        return None
    return moving_average(series, 7)[-1][1]


def week_scorecard(store: Store, plan: Plan, iso_year: int, iso_week: int, today: date) -> dict:
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    sunday = monday + timedelta(days=6)
    days = history(store, plan, monday, sunday, today)
    scored = [d for d in days if d["score"] is not None]
    avg = round(sum(d["score"] for d in scored) / len(scored), 1) if scored else 0.0
    green = sum(1 for d in scored if d["grade"] == "green")

    proteins: list[float] = []
    sessions = 0
    for i in range(7):
        d = monday + timedelta(days=i)
        if d > today:
            continue
        dp, checks, _ = _live(store, plan, d)
        if checks:
            proteins.append(protein_total(dp, checks))
        done = {k for k, c in checks.items() if c.state == "done"}
        if dp.mode == "travel":
            sessions += "travel_circuit" in done
        elif dp.mode != "rest":
            sessions += "badminton" in done
    protein_avg = round(sum(proteins) / len(proteins), 1) if proteins else 0.0

    progressed = 0
    keys = {l.exercise_key for i in range(7) for l in store.get_lifts(monday + timedelta(days=i))}
    for k in keys:
        this_week = store.lift_sessions(k, sunday, limit=1)
        last_week = store.lift_sessions(k, monday - timedelta(days=1), limit=1)
        if this_week and last_week and this_week[0]["date"] >= monday and this_week[0]["top_weight"] > last_week[0]["top_weight"]:
            progressed += 1

    w_end = _ma7_at(store, min(sunday, today))
    w_start = _ma7_at(store, monday - timedelta(days=1))
    change = round(w_end - w_start, 2) if (w_end is not None and w_start is not None) else None
    verdict = corridor_status(w_end, plan.checkpoints, min(sunday, today), plan.band_kg) if w_end is not None else "on_pace"
    return {
        "week": f"{iso_year}-W{iso_week:02d}",
        "start": monday.isoformat(), "end": sunday.isoformat(),
        "days": days, "avg_score": avg, "green_days": green, "protein_avg": protein_avg,
        "sessions_done": sessions, "sessions_target": 6, "lifts_progressed": progressed,
        "weight_start": w_start, "weight_end": w_end, "weight_change": change,
        "verdict": verdict, "on_plan": avg >= 85,
    }
