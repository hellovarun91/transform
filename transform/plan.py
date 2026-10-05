from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import yaml

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plan", "plan.yaml")
COURT_DAYS = (0, 2, 4)
GYM_DAYS = (1, 3, 5)


@dataclass
class Exercise:
    key: str
    name: str
    sets: int
    rep_min: int | None
    rep_max: int | None
    reps_label: str
    load: str | None = None
    logs_sets: bool = False


@dataclass
class MealSlot:
    key: str
    time: str
    label: str
    detail: str
    protein: int
    kcal: int
    optional: bool = False


@dataclass
class ScheduleItem:
    key: str
    time: str
    label: str
    points: int = 0


@dataclass
class DayPlan:
    date: date
    weekday: int
    mode: str              # normal | rest | travel | diet_break
    day_type: str          # "Court day" | "Gym day" | "Rest day" | "Travel" | "Diet break"
    block_index: int
    variant_index: int
    adaptation: bool
    calorie_level: str     # level0 | level1 | level2 | maintenance
    protein_target: int
    bed_by: str
    schedule: list[ScheduleItem]
    meals: list[MealSlot]
    court_title: str | None
    court_exercises: list[Exercise]
    gym_title: str | None
    gym_exercises: list[Exercise]
    travel_circuit: list[Exercise]
    supplements: list[dict]
    rules: list[dict]
    sunday_prep: list[str] = field(default_factory=list)

    @property
    def scored_meal_keys(self) -> list[str]:
        return [m.key for m in self.meals if not m.optional]


def _parse_reps(reps: str) -> tuple[int | None, int | None]:
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", reps.strip())
    if not m:
        return None, None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return lo, hi


def _exercise(raw: dict, variant_index: int, logs_sets: bool) -> Exercise:
    name = raw["name"]
    variants = raw.get("variants") or []
    if variant_index > 0 and variants:
        name = variants[(variant_index - 1) % len(variants)]
    lo, hi = _parse_reps(str(raw["reps"]))
    return Exercise(
        key=raw["key"], name=name, sets=int(raw["sets"]), rep_min=lo, rep_max=hi,
        reps_label=str(raw["reps"]), load=raw.get("load"), logs_sets=logs_sets,
    )


def _to_date(v) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


class Plan:
    def __init__(self, raw: dict):
        self.raw = raw
        self.meta = dict(raw["meta"])
        self.meta["start_date"] = _to_date(self.meta["start_date"])
        self.meta["diet_break"] = {k: _to_date(v) for k, v in self.meta["diet_break"].items()}
        self.checkpoints: list[tuple[date, float]] = [
            (_to_date(c["date"]), float(c["kg"])) for c in raw["timeline"]["checkpoints"]
        ]
        self.band_kg: float = float(raw["timeline"].get("band_kg", 1.0))
        self.notif_times: dict[str, str] = dict(raw["notif_times"])
        self.rules: list[dict] = list(raw["rules"])
        self.supplements: list[dict] = list(raw["supplements"])

    @property
    def start_date(self) -> date:
        return self.meta["start_date"]

    def block_index(self, d: date) -> int:
        days = (d - self.start_date).days
        return max(0, days // (7 * int(self.meta["block_weeks"])))

    def is_adaptation(self, d: date) -> bool:
        return 0 <= (d - self.start_date).days < 7 * int(self.meta["adaptation_weeks"])

    def in_diet_break(self, d: date) -> bool:
        db = self.meta["diet_break"]
        return db["start"] <= d <= db["end"]

    def level_name(self, calorie_level: int, mode: str) -> str:
        if mode == "diet_break":
            return "maintenance"
        return f"level{min(max(int(calorie_level), 0), 2)}"

    def resolve(self, d: date, travel: bool = False, calorie_level: int = 0) -> DayPlan:
        wd = d.weekday()
        if travel:
            mode = "travel"
        elif self.in_diet_break(d):
            mode = "diet_break"
        elif wd == 6:
            mode = "rest"
        else:
            mode = "normal"
        variant = self.block_index(d)
        level = self.level_name(calorie_level, mode)
        sched_raw = self.raw["schedule"]
        wk = self.raw["workouts"]

        def sitem(key: str, points: int | None = None) -> ScheduleItem:
            r = sched_raw[key]
            return ScheduleItem(key=key, time=r["time"], label=r["label"],
                                points=r.get("points", 0) if points is None else points)

        court_title = gym_title = None
        court_ex: list[Exercise] = []
        gym_ex: list[Exercise] = []
        circuit: list[Exercise] = []

        if mode == "travel":
            tc = wk["travel_circuit"]
            circuit = [_exercise(e, 0, False) for e in tc["exercises"]]
            schedule = [sitem("wake"), sitem("travel_circuit"), sitem("run"), sitem("sleep")]
            day_type = "Travel"
        elif wd == 6:
            schedule = [sitem("wake"), sitem("rest"), sitem("run"), sitem("sleep")]
            day_type = "Diet break" if mode == "diet_break" else "Rest day"
        else:
            if wd in COURT_DAYS:
                c = wk["court"][wd]
                court_title = c["title"]
                court_ex = [_exercise(e, variant, False) for e in c["exercises"]]
                schedule = [sitem("wake"), sitem("badminton"),
                            sitem("court_block", self.raw["court_block_points"]["court_weights"]),
                            sitem("sleep")]
                day_type = "Court day"
            else:
                core = wk["core"]
                court_title = core["title"]
                court_ex = [_exercise(e, 0, False) for e in core["exercises"]]
                g = wk["gym"][wd]
                gym_title = g["title"]
                gym_ex = [_exercise(e, variant, True) for e in g["exercises"]]
                schedule = [sitem("wake"), sitem("badminton"),
                            sitem("court_block", self.raw["court_block_points"]["core"]),
                            sitem("gym"), sitem("sleep")]
                day_type = "Gym day"
            if mode == "diet_break":
                day_type = "Diet break"

        meals = self._meals(wd, mode, level)
        protein_target = int(self.meta["travel_protein_target"] if mode == "travel" else self.meta["protein_target"])
        return DayPlan(
            date=d, weekday=wd, mode=mode, day_type=day_type,
            block_index=self.block_index(d), variant_index=variant, adaptation=self.is_adaptation(d),
            calorie_level=level, protein_target=protein_target, bed_by=str(self.meta["bed_by"]),
            schedule=schedule, meals=meals,
            court_title=court_title, court_exercises=court_ex,
            gym_title=gym_title, gym_exercises=gym_ex, travel_circuit=circuit,
            supplements=list(self.supplements), rules=list(self.rules),
            sunday_prep=list(self.raw["meals"]["sunday_prep"]) if wd == 6 else [],
        )

    def _meals(self, wd: int, mode: str, level: str) -> list[MealSlot]:
        m = self.raw["meals"]
        out: list[MealSlot] = []
        mains = m["mains"][wd]
        is_gym_day = wd in GYM_DAYS
        for s in m["slots"]:
            detail = s["detail"]
            if mode == "travel":
                detail = m["travel"][s["key"]]
            elif s["key"] == "breakfast":
                detail = detail.replace("{toast}", m["toast"][level])
            elif s["key"] == "lunch":
                grain = m["grain_lunch"][level]["gym" if is_gym_day else "court"]
                if wd == 6:
                    grain = "grain as you like, one plate"
                detail = detail.replace("{main}", mains["lunch"]).replace("{grain}", grain)
            elif s["key"] == "dinner":
                main = mains["dinner"]
                if mains.get("dinner_swap"):
                    main += f" (swap: {mains['dinner_swap']})"
                grain = mains.get("dinner_grain") or m["grain_dinner"][level]
                whey = m["gym_day_dinner_whey"] if is_gym_day else ""
                detail = detail.replace("{main}", main).replace("{grain}", grain).replace("{whey}", whey)
            out.append(MealSlot(
                key=s["key"], time=s["time"], label=s["label"], detail=detail,
                protein=int(s["protein"]), kcal=int(s["kcal"]), optional=bool(s.get("optional", False)),
            ))
        return out

    def weekday_plan(self, weekday: int) -> DayPlan:
        d = self.start_date
        while d.weekday() != weekday:
            d += timedelta(days=1)
        return self.resolve(d)


def load_plan(path: str | None = None) -> Plan:
    with open(path or DEFAULT_PATH, "r", encoding="utf-8") as f:
        return Plan(yaml.safe_load(f))
