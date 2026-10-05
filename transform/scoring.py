from __future__ import annotations

from dataclasses import dataclass

from .plan import DayPlan

NORMAL_WEIGHTS = {"meals": 40, "protein": 15, "rules": 15, "training": 20, "sleep": 5, "supplements": 5}
TRAVEL_WEIGHTS = {"protein": 30, "rules": 30, "training": 25, "sleep": 8, "supplements": 7}
PROTEIN_FLOOR_NORMAL = 130
PROTEIN_FLOOR_TRAVEL = 100
TRAINING_KEYS = ("badminton", "court_block", "gym")


@dataclass
class Check:
    state: str
    value_num: float | None = None
    value_text: str | None = None


@dataclass
class ScoreResult:
    total: int
    breakdown: dict[str, int]
    protein: float
    grade: str


def grade(total: int) -> str:
    if total >= 90:
        return "green"
    if total >= 75:
        return "amber"
    return "red"


def streak(grades_newest_first: list[str]) -> int:
    n = 0
    for g in grades_newest_first:
        if g != "green":
            break
        n += 1
    return n


def bed_minutes(hhmm: str) -> int:
    """Minutes since 00:00 of the plan day. Hours < 12 are read as past midnight."""
    h, m = hhmm.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(hhmm)
    if h < 12:
        h += 24
    return h * 60 + m


def protein_total(plan: DayPlan, checks: dict[str, Check]) -> float:
    total = 0.0
    for meal in plan.meals:
        c = checks.get(f"meal:{meal.key}")
        if not c:
            continue
        if c.state == "done":
            if plan.mode == "travel":
                total += c.value_num or 0
            else:
                total += meal.protein if c.value_num is None else c.value_num
        elif c.state == "swapped":
            total += c.value_num or 0
    return total


def _linear(value: float, floor: float, target: float, points: int) -> int:
    if value >= target:
        return points
    if value <= floor:
        return 0
    return round((value - floor) / (target - floor) * points)


def _meals_points(plan: DayPlan, checks: dict[str, Check], points: int) -> int:
    keys = plan.scored_meal_keys
    share = 0.0
    for k in keys:
        c = checks.get(f"meal:{k}")
        if not c:
            continue
        if c.state == "done":
            share += 1
        elif c.state == "swapped" and (c.value_text or "").strip():
            share += 0.5
    return round(share / len(keys) * points)


def _rules_points(plan: DayPlan, rule_breaks: set[str], points: int) -> int:
    keys = {r["key"] for r in plan.rules}
    per = points // len(keys)
    return max(0, points - per * len(rule_breaks & keys))


def _training_points(plan: DayPlan, checks: dict[str, Check]) -> int:
    done = {k for k, c in checks.items() if c.state == "done"}
    if plan.mode == "rest":
        if done & set(TRAINING_KEYS):
            return 0
        return next((s.points for s in plan.schedule if s.key == "rest"), 0) if "rest" in done else 0
    return sum(s.points for s in plan.schedule if s.points > 0 and s.key in done)


def _sleep_points(plan: DayPlan, checks: dict[str, Check], points: int) -> int:
    c = checks.get("sleep")
    if not c or not c.value_text:
        return 0
    try:
        return points if bed_minutes(c.value_text) <= bed_minutes(plan.bed_by) else 0
    except ValueError:
        return 0


def _supp_points(plan: DayPlan, checks: dict[str, Check], points: int) -> int:
    for s in plan.supplements:
        c = checks.get(f"supp:{s['key']}")
        if not c or c.state != "done":
            return 0
    return points


def score_day(plan: DayPlan, checks: dict[str, Check], rule_breaks: set[str]) -> ScoreResult:
    if not checks:
        return ScoreResult(0, {}, 0.0, "red")
    protein = protein_total(plan, checks)
    if plan.mode == "travel":
        w = TRAVEL_WEIGHTS
        b = {
            "protein": _linear(protein, PROTEIN_FLOOR_TRAVEL, plan.protein_target, w["protein"]),
            "rules": _rules_points(plan, rule_breaks, w["rules"]),
            "training": _training_points(plan, checks),
            "sleep": _sleep_points(plan, checks, w["sleep"]),
            "supplements": _supp_points(plan, checks, w["supplements"]),
        }
    else:
        w = NORMAL_WEIGHTS
        b = {
            "meals": _meals_points(plan, checks, w["meals"]),
            "protein": _linear(protein, PROTEIN_FLOOR_NORMAL, plan.protein_target, w["protein"]),
            "rules": _rules_points(plan, rule_breaks, w["rules"]),
            "training": _training_points(plan, checks),
            "sleep": _sleep_points(plan, checks, w["sleep"]),
            "supplements": _supp_points(plan, checks, w["supplements"]),
        }
    total = min(100, sum(b.values()))
    return ScoreResult(total, b, protein, grade(total))
