# Transform Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-user FastAPI + SQLite + plain-JS PWA that prescribes Varun's daily training and meals, scores every day 0–100 against the plan, tracks weight against a timeline corridor, nudges via web push, and deploys to Railway.

**Architecture:** One Python process: FastAPI serves `/api/*` and the static PWA, APScheduler runs IST-timed nudges and the midnight close job, SQLite on `/data` holds logs. All plan content (exercises, meals, times, checkpoints) lives in `plan/plan.yaml`; `plan.py` resolves a date into a `DayPlan`; `scoring.py` is a pure function over a `DayPlan` plus the day's checks. The frontend is vanilla ES modules with no build step.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, SQLAlchemy 2, PyYAML, APScheduler 3.x, pywebpush, pytest + httpx TestClient. Frontend: HTML/CSS/ES modules, service worker, Web Push API.

**Spec:** `docs/superpowers/specs/2026-10-05-transform-tracker-design.md`

## Global Constraints

- Python 3.12 (Dockerfile `python:3.12-slim`); CI also runs 3.11.
- All "today" and schedule logic uses `Asia/Kolkata`; never `datetime.now()` without tz.
- Dates cross the API as ISO `YYYY-MM-DD` strings; times as `HH:MM`.
- Single user. Auth = PIN from `TRANSFORM_PIN` → HMAC bearer token signed with `TRANSFORM_SECRET`.
- Plan content is only in `plan/plan.yaml`. DB stores `item_key`s, never plan text.
- Scoring weights exactly as spec §6: meals 40, protein 15, rules 15, training 20, sleep 5 + supplements 5. Travel remap: protein 30, rules 30, circuit 25, sleep 8 + supplements 7.
- Grades: ≥90 green, 75–89 amber, <75 red. Day with zero checks = 0.
- Day is editable until `date + 3 days 00:00 IST` (48 h after the midnight that closes it); after that writes return 409.
- Calorie floor: level never goes below 0. Diet break 2026-12-06 → 2026-12-12 inclusive.
- No frontend build step; no npm. External JS libraries: none.
- Scoped simplification (agreed in planning): progression prompts are computed for exercises with per-set logs (gym). Court exercises are tick-only and change through the per-block variant rotation.

## Review Focus

Inputs the spec implies but which are easy to get wrong. Each has a test pinned to the owning task.

1. **Bed time after midnight** ("00:20") must count as late, not as 00:20 the previous evening. → Task 3 `test_sleep_after_midnight_is_late`.
2. **Swapped meal with no text at close** reverts to skipped and loses its half points. → Task 7 `test_close_day_reverts_textless_swap`.
3. **Writing to a frozen day** (older than 48 h past its midnight) returns 409, writing to tomorrow returns 400. → Task 6 `test_frozen_day_409`, `test_future_date_400`.
4. **Travel on a Sunday**: travel wins, the day is scored on the travel remap and the circuit, not on "rest logged". → Task 2 `test_travel_overrides_sunday`, Task 3 `test_travel_day_perfect_is_100`.
5. **Restart during the day**: midnight catch-up must not re-close and overwrite a day edited within its 48 h window with stale data, and must close any skipped past days once. → Task 7 `test_catch_up_closes_only_unscored_days`.

---

## File Structure

```
transform/
  __init__.py
  __main__.py          # python -m transform → uvicorn on PORT (default 8000)
  config.py            # Settings dataclass from env (pin, secret, data dir, vapid, tz)
  app.py               # create_app(settings, store, plan) → FastAPI; mounts static; starts scheduler
  plan.py              # load_plan(path) → Plan; Plan.resolve(date, travel, calorie_level) → DayPlan
  scoring.py           # score_day(plan, checks, rule_breaks) → ScoreResult; grade(); streak()
  timeline.py          # corridor(), moving_average(), projection()
  db.py                # SQLAlchemy models + Store (all DB access)
  auth.py              # pin verify, token mint/verify, rate limit
  guardrails.py        # close_day(), catch_up(), strength/sleep checks, progression prompts, level bump
  reports.py           # weekly scorecard, history range, export
  push.py              # send_push(store, title, body, url)
  scheduler.py         # build_scheduler(store, plan, settings) → APScheduler jobs
  api/__init__.py      # router aggregation
  api/deps.py          # get_store/get_plan/require_auth dependencies, date helpers
  api/routes_auth.py
  api/routes_day.py    # /today, /day/{date}, /check, /lift, /rule, /weight
  api/routes_meta.py   # /plan, /history, /week, /settings, /travel, /export, /push/*, /health
static/
  index.html, styles.css, manifest.json, sw.js
  app.js               # boot, router, api client, offline queue
  views/today.js, views/plan.js, views/weight.js, views/history.js, views/settings.js
plan/plan.yaml
tests/
  conftest.py, test_plan.py, test_scoring.py, test_timeline.py, test_db.py,
  test_api.py, test_guardrails.py, test_reports.py, test_push.py
Dockerfile, railway.toml, requirements.txt, pyproject.toml, .github/workflows/ci.yml, CLAUDE.md
```

---

### Task 1: Repo reset, scaffolding, health endpoint

**Files:**
- Delete: `index.html`, `manifest.json`, `server.sh`, `sw.js`, `claude.md`
- Create: `requirements.txt`, `pyproject.toml`, `Dockerfile`, `railway.toml`, `.github/workflows/ci.yml`, `.gitignore`, `transform/__init__.py`, `transform/__main__.py`, `transform/config.py`, `transform/app.py`, `tests/conftest.py`, `tests/test_app.py`

**Interfaces:**
- Produces: `config.Settings` (fields below), `config.load_settings() -> Settings`, `app.create_app(settings, store=None, plan=None, start_scheduler=False) -> FastAPI`. Later tasks add `store` and `plan` wiring; for now `create_app` accepts and ignores them.

- [ ] **Step 1: Remove the old static app and add tooling files**

```bash
cd /Users/varunsaini/Desktop/transform
git rm -q index.html manifest.json server.sh sw.js claude.md
```

`requirements.txt`:
```
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
sqlalchemy>=2.0,<3
pyyaml>=6
apscheduler>=3.10,<4
pywebpush>=2.0
pydantic>=2.7,<3
httpx>=0.27
pytest>=8
```

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "transform"
version = "1.0.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
include = ["transform*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
*.db
*.db-wal
*.db-shm
.env
data/
```

`Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=Asia/Kolkata
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
CMD ["python", "-m", "transform"]
```

`railway.toml`:
```toml
[build]
builder = "DOCKERFILE"

[deploy]
startCommand = "python -m transform"
healthcheckPath = "/health"
healthcheckTimeout = 120
restartPolicyType = "ON_FAILURE"
```

`.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
```

- [ ] **Step 2: Write the failing health test**

`tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient

from transform.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        pin="1234",
        secret="test-secret",
        data_dir=str(tmp_path),
        vapid_private_key="",
        vapid_public_key="",
        vapid_claims_email="mailto:test@example.com",
        tz="Asia/Kolkata",
        port=8000,
    )


@pytest.fixture
def client(settings):
    from transform.app import create_app

    app = create_app(settings, start_scheduler=False)
    with TestClient(app) as c:
        yield c
```

`tests/test_app.py`:
```python
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd /Users/varunsaini/Desktop/transform && python3 -m venv .venv && . .venv/bin/activate && pip install -q -r requirements.txt && pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'transform'`

- [ ] **Step 4: Write config, app factory, entry point**

`transform/__init__.py`: empty.

`transform/config.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    pin: str
    secret: str
    data_dir: str
    vapid_private_key: str
    vapid_public_key: str
    vapid_claims_email: str
    tz: str = "Asia/Kolkata"
    port: int = 8000

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "transform.db")


def load_settings() -> Settings:
    data_dir = os.environ.get("TRANSFORM_DATA_DIR") or ("/data" if os.path.isdir("/data") else "./data")
    os.makedirs(data_dir, exist_ok=True)
    return Settings(
        pin=os.environ.get("TRANSFORM_PIN", "0000"),
        secret=os.environ.get("TRANSFORM_SECRET", "change-me"),
        data_dir=data_dir,
        vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY", ""),
        vapid_public_key=os.environ.get("VAPID_PUBLIC_KEY", ""),
        vapid_claims_email=os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@example.com"),
        tz=os.environ.get("TZ", "Asia/Kolkata"),
        port=int(os.environ.get("PORT", "8000")),
    )
```

`transform/app.py` (first version; Task 6 and Task 9 extend it):
```python
from __future__ import annotations

from fastapi import FastAPI

from .config import Settings


def create_app(settings: Settings, store=None, plan=None, start_scheduler: bool = False) -> FastAPI:
    app = FastAPI(title="Transform", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.store = store
    app.state.plan = plan

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
```

`transform/__main__.py`:
```python
import uvicorn

from .config import load_settings


def main() -> None:
    settings = load_settings()
    from .app import create_app
    from .db import Store
    from .plan import load_plan

    store = Store(settings.db_path)
    plan = load_plan()
    app = create_app(settings, store=store, plan=plan, start_scheduler=True)
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
```

(`db.Store` and `plan.load_plan` arrive in Tasks 5 and 2; `__main__` is only executed in production, so tests pass now.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Reset repo: FastAPI scaffold, Dockerfile, Railway config, CI, health endpoint"
```

---

### Task 2: Plan content and resolver

**Files:**
- Create: `plan/plan.yaml`, `transform/plan.py`, `tests/test_plan.py`

**Interfaces:**
- Produces:
  - `load_plan(path: str | None = None) -> Plan`
  - `Plan.meta: dict` (start_date, start_weight, protein_target, travel_protein_target, block_weeks, adaptation_weeks, diet_break{start,end}, bed_by, goal_weight)
  - `Plan.checkpoints: list[tuple[date, float]]`
  - `Plan.notif_times: dict[str, str]`
  - `Plan.resolve(d: date, travel: bool = False, calorie_level: int = 0) -> DayPlan`
  - `Plan.weekday_plan(weekday: int) -> DayPlan` (resolve for the next occurrence of that weekday from start_date, normal mode)
  - Dataclasses `Exercise(key, name, sets, rep_min, rep_max, reps_label, load, logs_sets)`, `MealSlot(key, time, label, detail, protein, kcal, optional)`, `ScheduleItem(key, time, label, points)`, `DayPlan(...)` fields listed in the code.
  - Check item key conventions: schedule → `key` as-is (`badminton`, `court_block`, `gym`, `rest`, `run`, `travel_circuit`, `wake`); meals → `meal:<slot>`; exercises → `ex:<exercise_key>`; supplements → `supp:<key>`; sleep → `sleep`.

- [ ] **Step 1: Write failing tests**

`tests/test_plan.py`:
```python
from datetime import date

import pytest

from transform.plan import load_plan


@pytest.fixture(scope="module")
def plan():
    return load_plan()


def test_monday_is_court_push_day(plan):
    dp = plan.resolve(date(2026, 10, 5))
    assert dp.mode == "normal"
    assert dp.day_type == "Court day"
    assert dp.court_title == "Push"
    assert dp.gym_title is None
    keys = [s.key for s in dp.schedule]
    assert keys[:3] == ["wake", "badminton", "court_block"]
    pts = {s.key: s.points for s in dp.schedule}
    assert pts["badminton"] == 8 and pts["court_block"] == 12
    assert [e.key for e in dp.court_exercises][0] == "push_ups"


def test_tuesday_is_gym_day_with_core_block(plan):
    dp = plan.resolve(date(2026, 10, 6))
    assert dp.day_type == "Gym day"
    assert dp.court_title == "Core + mobility"
    assert dp.gym_title == "Upper push"
    pts = {s.key: s.points for s in dp.schedule}
    assert pts == {"wake": 0, "badminton": 8, "court_block": 6, "gym": 6, "sleep": 0}
    assert all(e.logs_sets for e in dp.gym_exercises)
    bench = dp.gym_exercises[0]
    assert (bench.key, bench.sets, bench.rep_min, bench.rep_max) == ("bench_press", 4, 6, 8)


def test_sunday_is_rest(plan):
    dp = plan.resolve(date(2026, 10, 11))
    assert dp.mode == "rest"
    pts = {s.key: s.points for s in dp.schedule}
    assert pts["rest"] == 20 and pts["run"] == 0
    assert dp.court_exercises == [] and dp.gym_exercises == []
    assert dp.sunday_prep


def test_meal_slots_and_protein(plan):
    dp = plan.resolve(date(2026, 10, 5))
    slots = {m.key: m for m in dp.meals}
    assert list(slots) == ["banana", "whey_am", "breakfast", "lunch", "snack", "dinner", "bedtime"]
    assert slots["bedtime"].optional and not slots["lunch"].optional
    assert sum(m.protein for m in dp.meals if not m.optional) == 180
    assert "Palak paneer" in slots["lunch"].detail
    assert "1 roti or ½ cup rice" in slots["lunch"].detail  # court day grain
    assert "No grain" in slots["dinner"].detail
    assert dp.protein_target == 185


def test_gym_day_lunch_gets_full_grain(plan):
    dp = plan.resolve(date(2026, 10, 6))
    lunch = next(m for m in dp.meals if m.key == "lunch")
    assert "2 roti or 1 cup rice" in lunch.detail


def test_calorie_level_1_adds_dinner_roti(plan):
    dp = plan.resolve(date(2026, 10, 5), calorie_level=1)
    dinner = next(m for m in dp.meals if m.key == "dinner")
    assert "1 roti" in dinner.detail
    assert dp.calorie_level == "level1"


def test_diet_break_mode_and_grains(plan):
    dp = plan.resolve(date(2026, 12, 8))
    assert dp.mode == "diet_break"
    assert dp.calorie_level == "maintenance"
    dinner = next(m for m in dp.meals if m.key == "dinner")
    assert "2 roti or 1 cup rice" in dinner.detail
    assert dp.gym_title == "Upper push"  # training unchanged on a Tuesday


def test_travel_overrides_sunday(plan):
    dp = plan.resolve(date(2026, 10, 11), travel=True)
    assert dp.mode == "travel"
    pts = {s.key: s.points for s in dp.schedule}
    assert pts["travel_circuit"] == 25 and "rest" not in pts
    assert dp.protein_target == 150
    assert dp.court_exercises == [] and dp.gym_exercises == []
    assert dp.travel_circuit  # exercises for the hotel circuit
    lunch = next(m for m in dp.meals if m.key == "lunch")
    assert "protein" in lunch.detail.lower()


def test_blocks_and_adaptation(plan):
    assert plan.resolve(date(2026, 10, 5)).adaptation is True
    assert plan.resolve(date(2026, 10, 18)).adaptation is True
    assert plan.resolve(date(2026, 10, 19)).adaptation is False
    assert plan.resolve(date(2026, 10, 19)).block_index == 0
    assert plan.resolve(date(2026, 11, 2)).block_index == 1


def test_variant_rotation_on_block_boundary(plan):
    b0 = plan.resolve(date(2026, 10, 6)).gym_exercises[0].name
    b1 = plan.resolve(date(2026, 11, 3)).gym_exercises[0].name
    assert b0 == "Bench press" and b1 == "Incline barbell press"
    c0 = plan.resolve(date(2026, 10, 9)).court_exercises[0].name
    c1 = plan.resolve(date(2026, 11, 6)).court_exercises[0].name
    assert c0 == "Goblet squat 10 kg" and c1 == "Rod front squat"


def test_supplements_rules_checkpoints(plan):
    dp = plan.resolve(date(2026, 10, 5))
    assert [s["key"] for s in dp.supplements] == ["creatine", "multivitamin", "omega3", "magnesium"]
    assert len(dp.rules) == 5
    assert dp.bed_by == "22:30"
    assert plan.checkpoints[0] == (date(2026, 10, 5), 92.0)
    assert plan.checkpoints[-1] == (date(2027, 1, 15), 81.5)


def test_weekday_plan_helper(plan):
    assert plan.weekday_plan(3).gym_title == "Lower"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'transform.plan'`

- [ ] **Step 3: Write `plan/plan.yaml`**

```yaml
meta:
  start_date: 2026-10-05
  start_weight: 92.0
  goal_weight: 81.5
  protein_target: 185
  travel_protein_target: 150
  block_weeks: 4
  adaptation_weeks: 2
  diet_break: { start: 2026-12-06, end: 2026-12-12 }
  bed_by: "22:30"
  kcal_level0: 2050
  kcal_maintenance: 2800

timeline:
  checkpoints:
    - { date: 2026-10-05, kg: 92.0 }
    - { date: 2026-10-18, kg: 89.5 }
    - { date: 2026-11-01, kg: 88.0 }
    - { date: 2026-11-29, kg: 84.5 }
    - { date: 2026-12-05, kg: 84.5 }
    - { date: 2026-12-12, kg: 84.5 }
    - { date: 2027-01-15, kg: 81.5 }
  band_kg: 1.0

notif_times:
  wake: "05:45"
  whey_am: "08:15"
  breakfast: "09:00"
  lunch: "13:00"
  snack: "16:30"
  gym: "18:45"
  dinner: "20:15"
  magnesium: "22:00"
  log_day: "22:15"
  weekly: "21:00"

rules:
  - { key: no_sugar_drinks, label: "No sugary drinks" }
  - { key: no_fried, label: "No fried food" }
  - { key: no_sweets, label: "No sweets (Sunday lunch excepted)" }
  - { key: water_3l, label: "3 L water" }
  - { key: no_alcohol, label: "No alcohol" }

supplements:
  - { key: creatine, time: "08:15", label: "Creatine 5 g in the morning shake" }
  - { key: multivitamin, time: "09:00", label: "Multivitamin with breakfast" }
  - { key: omega3, time: "13:00", label: "Omega-3 with lunch" }
  - { key: magnesium, time: "22:00", label: "Magnesium glycinate before bed" }

schedule:
  wake: { time: "05:45", label: "Wake · 500 ml water · black coffee" }
  badminton: { time: "06:30", label: "Badminton · 3 games", points: 8 }
  court_block: { time: "07:45", label: "Court block" }
  gym: { time: "19:00", label: "Gym", points: 6 }
  sleep: { time: "22:30", label: "Lights out by 22:30" }
  rest: { time: "08:00", label: "Rest day · log it", points: 20 }
  run: { time: "07:00", label: "Optional easy 5 km run", points: 0 }
  travel_circuit: { time: "07:00", label: "Hotel circuit · 20 min", points: 25 }

court_block_points: { court_weights: 12, core: 6 }

meals:
  slots:
    - { key: banana, time: "06:15", label: "Pre-session", detail: "1 banana", protein: 1, kcal: 105 }
    - { key: whey_am, time: "08:15", label: "Post-session shake", detail: "Whey 1 scoop in water + creatine 5 g", protein: 25, kcal: 120 }
    - { key: breakfast, time: "09:00", label: "Breakfast", detail: "3 whole eggs + 4 whites with veg (bhurji/omelette) · {toast} · 1 fruit", protein: 36, kcal: 430 }
    - { key: lunch, time: "13:00", label: "Lunch", detail: "{main} · 200 g curd · big salad · {grain}", protein: 45, kcal: 550 }
    - { key: snack, time: "16:30", label: "Snack", detail: "Whey 1 scoop in water + 1 apple or 30 g roasted chana", protein: 28, kcal: 200 }
    - { key: dinner, time: "20:15", label: "Dinner", detail: "{main} · sabzi · big salad · {grain}{whey}", protein: 45, kcal: 450 }
    - { key: bedtime, time: "22:00", label: "Optional", detail: "100 g curd or 200 ml milk", protein: 7, kcal: 80, optional: true }
  gym_day_dinner_whey: " · whey 1 scoop first"
  toast:
    level0: "1 multigrain toast"
    level1: "1 multigrain toast"
    level2: "2 multigrain toast"
    maintenance: "2 multigrain toast"
  grain_lunch:
    level0: { court: "1 roti or ½ cup rice", gym: "2 roti or 1 cup rice" }
    level1: { court: "1 roti or ½ cup rice", gym: "2 roti or 1 cup rice" }
    level2: { court: "2 roti or 1 cup rice", gym: "2 roti or 1 cup rice" }
    maintenance: { court: "2 roti + 1 cup rice", gym: "2 roti + 1 cup rice" }
  grain_dinner:
    level0: "No grain"
    level1: "1 roti"
    level2: "1 roti"
    maintenance: "2 roti or 1 cup rice"
  mains:          # weekday 0 = Monday
    0: { lunch: "Palak paneer 150 g", dinner: "Egg curry, 3 eggs" }
    1: { lunch: "Rajma", dinner: "Paneer tikka 150 g, air-fried" }
    2: { lunch: "Soya chunk curry, 50 g dry", dinner: "Tofu stir-fry 200 g", dinner_swap: "Grilled chicken 150 g" }
    3: { lunch: "Chana masala", dinner: "Moong dal chilla ×3 with paneer stuffing" }
    4: { lunch: "Matar paneer 150 g", dinner: "Besan-egg omelette, 3 eggs" }
    5: { lunch: "Dal tadka 1.5 cups", dinner: "Paneer bhurji 150 g", dinner_swap: "Fish tikka 150 g" }
    6: { lunch: "Flexible meal · one plate · log what you ate", dinner: "Dal khichdi + curd", dinner_grain: "1 cup rice (refeed)" }
  travel:
    banana: "1 banana or fruit before training"
    whey_am: "Rule1 sachet, 1 scoop · creatine"
    breakfast: "Eggs: 4–6 whole/whites, any style · log protein grams"
    lunch: "Dal / paneer / curd / chicken · no fried · log protein grams"
    snack: "Rule1 sachet or roasted chana · log protein grams"
    dinner: "Protein + sabzi + salad · no buffet seconds · log protein grams"
    bedtime: "Curd or milk if available"
  sunday_prep:
    - "Soak rajma and chana for Tue/Thu"
    - "Pressure-cook dal for 3 days"
    - "Boil 20 eggs for the week's whites"
    - "Cut paneer into 150 g portions, store in water"
    - "Chop salad veg for Mon–Wed"
    - "Portion whey + creatine into 12 sachets"

workouts:
  court:         # Mon/Wed/Fri; weekday → session
    0:
      title: Push
      exercises:
        - { key: push_ups, name: "Push-ups", sets: 3, reps: "15-20", variants: ["Decline push-ups"] }
        - { key: db_shoulder_press, name: "DB shoulder press 10 kg", sets: 3, reps: "12", variants: ["Single-arm DB press 10 kg"] }
        - { key: diamond_push_ups, name: "Diamond push-ups", sets: 3, reps: "12" }
        - { key: pike_push_ups, name: "Pike push-ups", sets: 3, reps: "10" }
        - { key: plank, name: "Plank", sets: 3, reps: "45 s" }
    2:
      title: Pull
      exercises:
        - { key: rod_row, name: "Rod bent-over row 35 kg", sets: 4, reps: "12", variants: ["Rod Pendlay row 35 kg"] }
        - { key: db_row, name: "Single-arm DB row 10 kg", sets: 3, reps: "15" }
        - { key: db_curl_court, name: "DB curl 10 kg", sets: 3, reps: "12" }
        - { key: rod_upright_row, name: "Rod upright row", sets: 3, reps: "12" }
        - { key: side_plank, name: "Side plank", sets: 3, reps: "30 s each" }
    4:
      title: Legs
      exercises:
        - { key: goblet_squat, name: "Goblet squat 10 kg", sets: 3, reps: "15", variants: ["Rod front squat"] }
        - { key: bulgarian_split_squat, name: "Bulgarian split squat", sets: 3, reps: "10/leg" }
        - { key: rod_rdl, name: "Rod RDL 35 kg", sets: 3, reps: "12" }
        - { key: walking_lunges, name: "Walking lunges", sets: 3, reps: "12/leg" }
        - { key: glute_bridge, name: "Glute bridge", sets: 3, reps: "20" }
        - { key: calf_raises_court, name: "Calf raises", sets: 3, reps: "20" }
  core:
    title: "Core + mobility"
    exercises:
      - { key: dead_bug, name: "Dead bug", sets: 3, reps: "10" }
      - { key: bird_dog, name: "Bird-dog", sets: 3, reps: "10" }
      - { key: hollow_hold, name: "Hollow hold", sets: 3, reps: "30 s" }
      - { key: stretch, name: "Hip-flexor + hamstring stretch", sets: 1, reps: "5 min" }
  gym:           # Tue/Thu/Sat
    1:
      title: Upper push
      exercises:
        - { key: bench_press, name: "Bench press", sets: 4, reps: "6-8", variants: ["Incline barbell press"] }
        - { key: incline_db_press, name: "Incline DB press", sets: 3, reps: "10", variants: ["Flat DB press"] }
        - { key: seated_db_shoulder_press, name: "Seated DB shoulder press", sets: 3, reps: "10" }
        - { key: cable_fly, name: "Cable fly", sets: 3, reps: "12" }
        - { key: triceps_pushdown, name: "Triceps rope pushdown", sets: 3, reps: "12" }
        - { key: face_pull, name: "Face pull", sets: 3, reps: "15" }
    3:
      title: Lower
      exercises:
        - { key: back_squat, name: "Back squat", sets: 4, reps: "6-8", variants: ["Front squat"] }
        - { key: rdl, name: "Romanian deadlift", sets: 3, reps: "8-10" }
        - { key: leg_press, name: "Leg press", sets: 3, reps: "12", variants: ["Hack squat"] }
        - { key: leg_curl, name: "Leg curl", sets: 3, reps: "12" }
        - { key: hanging_leg_raise, name: "Hanging leg raise", sets: 3, reps: "12" }
        - { key: calf_raise, name: "Standing calf raise", sets: 3, reps: "15" }
    5:
      title: Upper pull
      exercises:
        - { key: pull_ups, name: "Pull-ups or lat pulldown", sets: 4, reps: "8", variants: ["Chin-ups"] }
        - { key: barbell_row, name: "Barbell row", sets: 4, reps: "10", variants: ["T-bar row"] }
        - { key: chest_supported_row, name: "Chest-supported row", sets: 3, reps: "12" }
        - { key: overhead_press, name: "Overhead press", sets: 3, reps: "8" }
        - { key: db_curl, name: "DB curl", sets: 3, reps: "12" }
        - { key: rear_delt_fly, name: "Rear-delt fly", sets: 3, reps: "15" }
  travel_circuit:
    title: "Hotel circuit · 4 rounds"
    exercises:
      - { key: tc_push_ups, name: "Push-ups", sets: 4, reps: "15" }
      - { key: tc_squats, name: "Squats", sets: 4, reps: "20" }
      - { key: tc_reverse_lunges, name: "Reverse lunges", sets: 4, reps: "10/leg" }
      - { key: tc_plank, name: "Plank", sets: 4, reps: "45 s" }
      - { key: tc_mountain_climbers, name: "Mountain climbers", sets: 4, reps: "30 s" }
```

- [ ] **Step 4: Write `transform/plan.py`**

```python
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

    # ----- helpers -----
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

    def level_name(self, d: date, calorie_level: int, mode: str) -> str:
        if mode == "diet_break":
            return "maintenance"
        return f"level{min(max(int(calorie_level), 0), 2)}"

    # ----- main resolver -----
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
        level = self.level_name(d, calorie_level, mode)
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
        schedule: list[ScheduleItem]

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


def _to_date(v) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def load_plan(path: str | None = None) -> Plan:
    with open(path or DEFAULT_PATH, "r", encoding="utf-8") as f:
        return Plan(yaml.safe_load(f))
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_plan.py -v`
Expected: all PASS. If `test_meal_slots_and_protein` fails on the protein sum, confirm the six scored slots are 1+25+36+45+28+45 = 180.

- [ ] **Step 6: Commit**

```bash
git add plan/plan.yaml transform/plan.py tests/test_plan.py
git commit -m "Plan content in YAML and date→DayPlan resolver with modes, grains, block variants"
```

---

### Task 3: Scoring

**Files:**
- Create: `transform/scoring.py`, `tests/test_scoring.py`

**Interfaces:**
- Consumes: `plan.DayPlan`, `plan.load_plan`.
- Produces:
  - `@dataclass Check(state: str, value_num: float | None = None, value_text: str | None = None)` with states `done | swapped | skipped | untouched`
  - `@dataclass ScoreResult(total: int, breakdown: dict[str, int], protein: float, grade: str)`
  - `score_day(plan: DayPlan, checks: dict[str, Check], rule_breaks: set[str]) -> ScoreResult`
  - `protein_total(plan, checks) -> float`
  - `grade(total: int) -> str` → `"green" | "amber" | "red"`
  - `bed_minutes(hhmm: str) -> int` (minutes since 00:00 of the plan day's evening; `"00:20"` → 1460)
  - `streak(grades_newest_first: list[str]) -> int`

- [ ] **Step 1: Write failing tests**

`tests/test_scoring.py`:
```python
from datetime import date

import pytest

from transform.plan import load_plan
from transform.scoring import Check, bed_minutes, grade, score_day, streak


@pytest.fixture(scope="module")
def plan():
    return load_plan()


def perfect_checks(dp):
    c = {}
    for s in dp.schedule:
        if s.points > 0:
            c[s.key] = Check("done")
    for m in dp.meals:
        if not m.optional:
            c[f"meal:{m.key}"] = Check("done")
    for s in dp.supplements:
        c[f"supp:{s['key']}"] = Check("done")
    c["sleep"] = Check("done", value_text="22:15")
    return c


def test_perfect_court_day_is_100(plan):
    dp = plan.resolve(date(2026, 10, 5))
    r = score_day(dp, perfect_checks(dp), set())
    assert r.total == 100 and r.grade == "green"
    assert r.breakdown == {"meals": 40, "protein": 15, "rules": 15, "training": 20, "sleep": 5, "supplements": 5}
    assert r.protein == 180 + 0  # 6 slots, bedtime not ticked


def test_protein_needs_override_to_hit_target(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["meal:bedtime"] = Check("done")  # +7 → 187 ≥ 185
    assert score_day(dp, c, set()).protein == 187


def test_protein_linear_between_130_and_target(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["meal:dinner"] = Check("skipped")  # 180-45 = 135 → (135-130)/(185-130)*15 = 1.36 → 1
    r = score_day(dp, c, set())
    assert r.breakdown["protein"] == 1
    assert r.breakdown["meals"] == 33  # 5/6 of 40 = 33.3 → 33


def test_swapped_with_text_is_half_and_uses_entered_protein(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["meal:lunch"] = Check("swapped", value_num=30, value_text="dal rice at airport")
    r = score_day(dp, c, set())
    assert r.breakdown["meals"] == 37  # 5 full + 1 half = 5.5/6*40 = 36.67 → 37
    assert r.protein == 180 - 45 + 30


def test_swapped_without_text_scores_zero_for_that_meal(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["meal:lunch"] = Check("swapped", value_num=30)
    assert score_day(dp, c, set()).breakdown["meals"] == 33


def test_rule_breaks_cost_three_each(plan):
    dp = plan.resolve(date(2026, 10, 5))
    r = score_day(dp, perfect_checks(dp), {"no_fried", "no_sweets"})
    assert r.breakdown["rules"] == 9


def test_training_points_by_day(plan):
    court = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(court)
    c.pop("court_block")
    assert score_day(court, c, set()).breakdown["training"] == 8
    gym = plan.resolve(date(2026, 10, 6))
    c = perfect_checks(gym)
    c.pop("gym")
    assert score_day(gym, c, set()).breakdown["training"] == 14


def test_sunday_rest_logged_20_training_logged_0(plan):
    dp = plan.resolve(date(2026, 10, 11))
    c = perfect_checks(dp)
    assert score_day(dp, c, set()).breakdown["training"] == 20
    c["badminton"] = Check("done")
    assert score_day(dp, c, set()).breakdown["training"] == 0
    c.pop("badminton")
    c["run"] = Check("done")  # optional run does not break rest
    assert score_day(dp, c, set()).breakdown["training"] == 20


def test_sleep_after_midnight_is_late(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["sleep"] = Check("done", value_text="00:20")
    assert score_day(dp, c, set()).breakdown["sleep"] == 0
    assert bed_minutes("00:20") == 24 * 60 + 20
    assert bed_minutes("22:30") == 22 * 60 + 30


def test_sleep_missing_or_malformed_is_zero(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["sleep"] = Check("done", value_text="late")
    assert score_day(dp, c, set()).breakdown["sleep"] == 0
    c.pop("sleep")
    assert score_day(dp, c, set()).breakdown["sleep"] == 0


def test_supplements_all_or_nothing(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c.pop("supp:omega3")
    assert score_day(dp, c, set()).breakdown["supplements"] == 0


def test_empty_day_is_zero_red(plan):
    dp = plan.resolve(date(2026, 10, 5))
    r = score_day(dp, {}, set())
    assert r.total == 0 and r.grade == "red"


def test_travel_day_perfect_is_100(plan):
    dp = plan.resolve(date(2026, 10, 11), travel=True)
    c = {"travel_circuit": Check("done"), "sleep": Check("done", value_text="22:00")}
    for s in dp.supplements:
        c[f"supp:{s['key']}"] = Check("done")
    for m in dp.meals:
        if not m.optional:
            c[f"meal:{m.key}"] = Check("done", value_num=25)  # 6×25 = 150
    r = score_day(dp, c, set())
    assert r.breakdown == {"protein": 30, "rules": 30, "training": 25, "sleep": 8, "supplements": 7}
    assert r.total == 100


def test_travel_protein_linear_and_rules_six_each(plan):
    dp = plan.resolve(date(2026, 10, 11), travel=True)
    c = {"travel_circuit": Check("done")}
    c["meal:breakfast"] = Check("done", value_num=125)  # (125-100)/50*30 = 15
    r = score_day(dp, c, {"no_alcohol"})
    assert r.breakdown["protein"] == 15 and r.breakdown["rules"] == 24


def test_travel_done_meal_without_grams_counts_zero_protein(plan):
    dp = plan.resolve(date(2026, 10, 11), travel=True)
    c = {"meal:lunch": Check("done")}
    assert score_day(dp, c, set()).protein == 0


def test_grade_and_streak():
    assert grade(90) == "green" and grade(89) == "amber" and grade(75) == "amber" and grade(74) == "red"
    assert streak(["green", "green", "amber", "green"]) == 2
    assert streak([]) == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'transform.scoring'`

- [ ] **Step 3: Write `transform/scoring.py`**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scoring.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add transform/scoring.py tests/test_scoring.py
git commit -m "Pure daily scoring: meals, protein, rules, training, sleep, supplements, travel remap"
```

---

### Task 4: Timeline corridor and projection

**Files:**
- Create: `transform/timeline.py`, `tests/test_timeline.py`

**Interfaces:**
- Produces:
  - `corridor(checkpoints: list[tuple[date, float]], d: date) -> float | None` (linear interpolation; None outside range)
  - `corridor_band(checkpoints, d, band_kg) -> tuple[float, float] | None`
  - `moving_average(series: list[tuple[date, float]], n: int = 7) -> list[tuple[date, float]]` (trailing mean over available points ≤ n, series sorted by date)
  - `projection(series: list[tuple[date, float]], goal_kg: float, lookback: int = 14) -> date | None` (least-squares on MA7 of last `lookback` points; None if < 5 points or slope ≥ 0)
  - `corridor_status(ma7_kg: float, checkpoints, d, band_kg) -> str` → `"ahead" | "on_pace" | "behind"`

- [ ] **Step 1: Write failing tests**

`tests/test_timeline.py`:
```python
from datetime import date, timedelta

from transform.timeline import corridor, corridor_band, corridor_status, moving_average, projection

CP = [(date(2026, 10, 5), 92.0), (date(2026, 10, 19), 89.0), (date(2026, 11, 2), 87.0)]


def test_corridor_interpolates_and_bounds():
    assert corridor(CP, date(2026, 10, 5)) == 92.0
    assert corridor(CP, date(2026, 10, 12)) == 90.5
    assert corridor(CP, date(2026, 11, 2)) == 87.0
    assert corridor(CP, date(2026, 10, 4)) is None
    assert corridor(CP, date(2026, 11, 3)) is None
    assert corridor_band(CP, date(2026, 10, 12), 1.0) == (89.5, 91.5)


def test_moving_average_trailing():
    s = [(date(2026, 10, 1) + timedelta(days=i), 90 - i) for i in range(10)]
    ma = moving_average(s, 7)
    assert ma[0] == (date(2026, 10, 1), 90.0)
    assert ma[2][1] == 89.0
    assert round(ma[-1][1], 3) == 84.0  # mean of 87..81


def test_projection_hits_goal_date():
    s = [(date(2026, 10, 1) + timedelta(days=i), 92 - 0.1 * i) for i in range(20)]
    d = projection(s, 90.0)
    assert d is not None
    assert date(2026, 10, 18) <= d <= date(2026, 10, 24)


def test_projection_none_when_flat_or_short():
    flat = [(date(2026, 10, 1) + timedelta(days=i), 90.0) for i in range(20)]
    assert projection(flat, 85.0) is None
    assert projection(flat[:3], 85.0) is None


def test_corridor_status():
    assert corridor_status(90.5, CP, date(2026, 10, 12), 1.0) == "on_pace"
    assert corridor_status(92.0, CP, date(2026, 10, 12), 1.0) == "behind"
    assert corridor_status(89.0, CP, date(2026, 10, 12), 1.0) == "ahead"
    assert corridor_status(89.0, CP, date(2027, 1, 1), 1.0) == "on_pace"  # outside range → neutral
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_timeline.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `transform/timeline.py`**

```python
from __future__ import annotations

from datetime import date, timedelta


def corridor(checkpoints: list[tuple[date, float]], d: date) -> float | None:
    cps = sorted(checkpoints)
    if not cps or d < cps[0][0] or d > cps[-1][0]:
        return None
    for (d0, k0), (d1, k1) in zip(cps, cps[1:]):
        if d0 <= d <= d1:
            span = (d1 - d0).days
            if span == 0:
                return k1
            return round(k0 + (k1 - k0) * (d - d0).days / span, 3)
    return cps[-1][1]


def corridor_band(checkpoints, d: date, band_kg: float) -> tuple[float, float] | None:
    c = corridor(checkpoints, d)
    if c is None:
        return None
    return (round(c - band_kg, 3), round(c + band_kg, 3))


def corridor_status(ma7_kg: float, checkpoints, d: date, band_kg: float) -> str:
    band = corridor_band(checkpoints, d, band_kg)
    if band is None:
        return "on_pace"
    lo, hi = band
    if ma7_kg > hi:
        return "behind"
    if ma7_kg < lo:
        return "ahead"
    return "on_pace"


def moving_average(series: list[tuple[date, float]], n: int = 7) -> list[tuple[date, float]]:
    s = sorted(series)
    out: list[tuple[date, float]] = []
    for i in range(len(s)):
        window = [v for _, v in s[max(0, i - n + 1): i + 1]]
        out.append((s[i][0], round(sum(window) / len(window), 3)))
    return out


def projection(series: list[tuple[date, float]], goal_kg: float, lookback: int = 14) -> date | None:
    ma = moving_average(series, 7)[-lookback:]
    if len(ma) < 5:
        return None
    x0 = ma[0][0]
    xs = [(d - x0).days for d, _ in ma]
    ys = [v for _, v in ma]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if slope >= -1e-6:
        return None
    intercept = my - slope * mx
    days_to_goal = (goal_kg - intercept) / slope
    if days_to_goal < 0:
        return ma[-1][0]
    return x0 + timedelta(days=round(days_to_goal))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_timeline.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add transform/timeline.py tests/test_timeline.py
git commit -m "Timeline corridor, moving average, goal projection"
```

---

### Task 5: Database store

**Files:**
- Create: `transform/db.py`, `tests/test_db.py`

**Interfaces:**
- Produces `Store(path: str)` (`":memory:"` allowed) with methods:
  - days: `get_day(d) -> DayRow | None`, `upsert_day(d, *, mode=None, score=None, grade=None, locked_at=None, notes=None) -> DayRow`, `days_between(start, end) -> list[DayRow]`
  - checks: `upsert_check(d, item_key, state, value_num=None, value_text=None)`, `get_checks(d) -> dict[str, scoring.Check]`, `delete_check(d, item_key)`
  - lifts: `upsert_lift(d, exercise_key, set_no, reps, weight_kg)`, `get_lifts(d) -> list[LiftRow]`, `lift_sessions(exercise_key, on_or_before: date, limit=3) -> list[dict]` newest first, each `{"date", "top_weight", "sets": [(set_no, reps, weight_kg)]}`
  - weights: `set_weight(d, kg)`, `get_weights(start, end) -> list[tuple[date, float]]`, `all_weights()`
  - rules: `set_rule_break(d, rule_key, broken: bool)`, `get_rule_breaks(d) -> set[str]`
  - settings: `get_setting(key, default=None) -> str | None`, `set_setting(key, value: str)`
  - push: `add_subscription(endpoint, p256dh, auth)`, `remove_subscription(endpoint)`, `list_subscriptions() -> list[dict]`
  - calorie: `get_calorie_level(d) -> int` (0 default), `set_calorie_level(d, level, reason)`, `calorie_entries(start, end)`
  - travel: `set_travel(start, end, on: bool)`, `is_travel(d) -> bool`, `travel_days(start, end) -> set[date]`
  - `export_all() -> dict`
- Row classes expose attributes matching column names.

- [ ] **Step 1: Write failing tests**

`tests/test_db.py`:
```python
from datetime import date, datetime, timezone

import pytest

from transform.db import Store


@pytest.fixture
def store():
    return Store(":memory:")


def test_checks_upsert_and_fetch(store):
    d = date(2026, 10, 5)
    store.upsert_check(d, "meal:lunch", "swapped", value_num=30, value_text="dal")
    store.upsert_check(d, "meal:lunch", "done")
    checks = store.get_checks(d)
    assert checks["meal:lunch"].state == "done"
    assert checks["meal:lunch"].value_num is None
    store.delete_check(d, "meal:lunch")
    assert store.get_checks(d) == {}


def test_days_upsert_and_range(store):
    store.upsert_day(date(2026, 10, 5), mode="normal", score=88, grade="amber")
    store.upsert_day(date(2026, 10, 5), score=91, grade="green", locked_at=datetime(2026, 10, 6, tzinfo=timezone.utc))
    rows = store.days_between(date(2026, 10, 1), date(2026, 10, 31))
    assert len(rows) == 1 and rows[0].score == 91 and rows[0].mode == "normal"


def test_lifts_and_sessions(store):
    for i, d in enumerate([date(2026, 10, 6), date(2026, 10, 13), date(2026, 10, 20)]):
        store.upsert_lift(d, "bench_press", 1, 8, 60 + 2.5 * i)
        store.upsert_lift(d, "bench_press", 2, 7, 60 + 2.5 * i)
    store.upsert_lift(date(2026, 10, 20), "bench_press", 2, 8, 65)  # overwrite set 2
    s = store.lift_sessions("bench_press", date(2026, 10, 20), limit=2)
    assert [x["date"] for x in s] == [date(2026, 10, 20), date(2026, 10, 13)]
    assert s[0]["top_weight"] == 65 and s[0]["sets"] == [(1, 8, 65.0), (2, 8, 65.0)]
    assert len(store.get_lifts(date(2026, 10, 6))) == 2


def test_weights(store):
    store.set_weight(date(2026, 10, 5), 92.0)
    store.set_weight(date(2026, 10, 5), 91.8)
    store.set_weight(date(2026, 10, 6), 91.5)
    assert store.get_weights(date(2026, 10, 1), date(2026, 10, 31)) == [(date(2026, 10, 5), 91.8), (date(2026, 10, 6), 91.5)]


def test_rule_breaks(store):
    d = date(2026, 10, 5)
    store.set_rule_break(d, "no_fried", True)
    store.set_rule_break(d, "no_fried", True)
    store.set_rule_break(d, "no_sweets", True)
    store.set_rule_break(d, "no_sweets", False)
    assert store.get_rule_breaks(d) == {"no_fried"}


def test_settings_and_subscriptions(store):
    assert store.get_setting("x", "dflt") == "dflt"
    store.set_setting("x", "1")
    store.set_setting("x", "2")
    assert store.get_setting("x") == "2"
    store.add_subscription("https://p/1", "k", "a")
    store.add_subscription("https://p/1", "k2", "a2")
    assert store.list_subscriptions() == [{"endpoint": "https://p/1", "p256dh": "k2", "auth": "a2"}]
    store.remove_subscription("https://p/1")
    assert store.list_subscriptions() == []


def test_calorie_level_and_travel(store):
    assert store.get_calorie_level(date(2026, 10, 5)) == 0
    store.set_calorie_level(date(2026, 10, 6), 1, "strength drop")
    assert store.get_calorie_level(date(2026, 10, 6)) == 1
    assert store.get_calorie_level(date(2026, 10, 7)) == 0
    store.set_travel(date(2026, 10, 8), date(2026, 10, 10), True)
    assert store.is_travel(date(2026, 10, 9)) and not store.is_travel(date(2026, 10, 11))
    store.set_travel(date(2026, 10, 9), date(2026, 10, 9), False)
    assert store.travel_days(date(2026, 10, 1), date(2026, 10, 31)) == {date(2026, 10, 8), date(2026, 10, 10)}


def test_export_shape(store):
    store.set_weight(date(2026, 10, 5), 92.0)
    out = store.export_all()
    assert set(out) >= {"days", "checks", "lifts", "weights", "rule_breaks", "calorie_log", "travel_days", "settings"}
    assert out["weights"] == [{"date": "2026-10-05", "kg": 92.0}]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `transform/db.py`**

```python
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint,
                        create_engine, delete, event, select)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from .scoring import Check


class Base(DeclarativeBase):
    pass


class DayRow(Base):
    __tablename__ = "days"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    mode: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str | None] = mapped_column(String(8))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class CheckRow(Base):
    __tablename__ = "checks"
    __table_args__ = (UniqueConstraint("date", "item_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    item_key: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    value_num: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LiftRow(Base):
    __tablename__ = "lifts"
    __table_args__ = (UniqueConstraint("date", "exercise_key", "set_no"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    exercise_key: Mapped[str] = mapped_column(String(64), index=True)
    set_no: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[float] = mapped_column(Float)


class WeightRow(Base):
    __tablename__ = "weights"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    kg: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RuleBreakRow(Base):
    __tablename__ = "rule_breaks"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    rule_key: Mapped[str] = mapped_column(String(32), primary_key=True)


class SettingRow(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class PushSubRow(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CalorieRow(Base):
    __tablename__ = "calorie_log"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    level: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)


class TravelRow(Base):
    __tablename__ = "travel_days"
    date: Mapped[date] = mapped_column(Date, primary_key=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path: str):
        if path == ":memory:":
            self.engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                                        poolclass=StaticPool)
        else:
            self.engine = create_engine(f"sqlite+pysqlite:///{path}", connect_args={"check_same_thread": False})

            @event.listens_for(self.engine, "connect")
            def _wal(conn, _):
                conn.execute("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    # ---------- days ----------
    def get_day(self, d: date) -> DayRow | None:
        with self.Session() as s:
            return s.get(DayRow, d)

    def upsert_day(self, d: date, *, mode=None, score=None, grade=None, locked_at=None, notes=None) -> DayRow:
        with self.Session() as s:
            row = s.get(DayRow, d) or DayRow(date=d)
            for k, v in (("mode", mode), ("score", score), ("grade", grade), ("locked_at", locked_at), ("notes", notes)):
                if v is not None:
                    setattr(row, k, v)
            s.add(row)
            s.commit()
            return row

    def days_between(self, start: date, end: date) -> list[DayRow]:
        with self.Session() as s:
            return list(s.scalars(select(DayRow).where(DayRow.date >= start, DayRow.date <= end).order_by(DayRow.date)))

    # ---------- checks ----------
    def upsert_check(self, d: date, item_key: str, state: str, value_num=None, value_text=None) -> None:
        with self.Session() as s:
            row = s.scalar(select(CheckRow).where(CheckRow.date == d, CheckRow.item_key == item_key))
            if row is None:
                row = CheckRow(date=d, item_key=item_key)
            row.state, row.value_num, row.value_text, row.ts = state, value_num, value_text, _now()
            s.add(row)
            s.commit()

    def delete_check(self, d: date, item_key: str) -> None:
        with self.Session() as s:
            s.execute(delete(CheckRow).where(CheckRow.date == d, CheckRow.item_key == item_key))
            s.commit()

    def get_checks(self, d: date) -> dict[str, Check]:
        with self.Session() as s:
            rows = s.scalars(select(CheckRow).where(CheckRow.date == d))
            return {r.item_key: Check(r.state, r.value_num, r.value_text) for r in rows}

    # ---------- lifts ----------
    def upsert_lift(self, d: date, exercise_key: str, set_no: int, reps: int, weight_kg: float) -> None:
        with self.Session() as s:
            row = s.scalar(select(LiftRow).where(LiftRow.date == d, LiftRow.exercise_key == exercise_key,
                                                 LiftRow.set_no == set_no))
            if row is None:
                row = LiftRow(date=d, exercise_key=exercise_key, set_no=set_no)
            row.reps, row.weight_kg = int(reps), float(weight_kg)
            s.add(row)
            s.commit()

    def get_lifts(self, d: date) -> list[LiftRow]:
        with self.Session() as s:
            return list(s.scalars(select(LiftRow).where(LiftRow.date == d).order_by(LiftRow.exercise_key, LiftRow.set_no)))

    def lift_sessions(self, exercise_key: str, on_or_before: date, limit: int = 3) -> list[dict]:
        with self.Session() as s:
            rows = list(s.scalars(select(LiftRow).where(LiftRow.exercise_key == exercise_key, LiftRow.date <= on_or_before)
                                  .order_by(LiftRow.date.desc(), LiftRow.set_no)))
        out: list[dict] = []
        for r in rows:
            if not out or out[-1]["date"] != r.date:
                if len(out) == limit:
                    break
                out.append({"date": r.date, "top_weight": 0.0, "sets": []})
            out[-1]["sets"].append((r.set_no, r.reps, r.weight_kg))
            out[-1]["top_weight"] = max(out[-1]["top_weight"], r.weight_kg)
        return out

    # ---------- weights ----------
    def set_weight(self, d: date, kg: float) -> None:
        with self.Session() as s:
            row = s.get(WeightRow, d) or WeightRow(date=d)
            row.kg, row.ts = float(kg), _now()
            s.add(row)
            s.commit()

    def get_weights(self, start: date, end: date) -> list[tuple[date, float]]:
        with self.Session() as s:
            rows = s.scalars(select(WeightRow).where(WeightRow.date >= start, WeightRow.date <= end).order_by(WeightRow.date))
            return [(r.date, r.kg) for r in rows]

    def all_weights(self) -> list[tuple[date, float]]:
        with self.Session() as s:
            return [(r.date, r.kg) for r in s.scalars(select(WeightRow).order_by(WeightRow.date))]

    # ---------- rules ----------
    def set_rule_break(self, d: date, rule_key: str, broken: bool) -> None:
        with self.Session() as s:
            row = s.get(RuleBreakRow, (d, rule_key))
            if broken and row is None:
                s.add(RuleBreakRow(date=d, rule_key=rule_key))
            elif not broken and row is not None:
                s.delete(row)
            s.commit()

    def get_rule_breaks(self, d: date) -> set[str]:
        with self.Session() as s:
            return {r.rule_key for r in s.scalars(select(RuleBreakRow).where(RuleBreakRow.date == d))}

    # ---------- settings ----------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.Session() as s:
            row = s.get(SettingRow, key)
            return row.value if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.Session() as s:
            row = s.get(SettingRow, key) or SettingRow(key=key)
            row.value = value
            s.add(row)
            s.commit()

    # ---------- push ----------
    def add_subscription(self, endpoint: str, p256dh: str, auth: str) -> None:
        with self.Session() as s:
            row = s.scalar(select(PushSubRow).where(PushSubRow.endpoint == endpoint)) or PushSubRow(endpoint=endpoint, created_at=_now())
            row.p256dh, row.auth = p256dh, auth
            s.add(row)
            s.commit()

    def remove_subscription(self, endpoint: str) -> None:
        with self.Session() as s:
            s.execute(delete(PushSubRow).where(PushSubRow.endpoint == endpoint))
            s.commit()

    def list_subscriptions(self) -> list[dict]:
        with self.Session() as s:
            return [{"endpoint": r.endpoint, "p256dh": r.p256dh, "auth": r.auth}
                    for r in s.scalars(select(PushSubRow).order_by(PushSubRow.id))]

    # ---------- calorie level ----------
    def get_calorie_level(self, d: date) -> int:
        with self.Session() as s:
            row = s.get(CalorieRow, d)
            return int(row.level) if row else 0

    def set_calorie_level(self, d: date, level: int, reason: str) -> None:
        with self.Session() as s:
            row = s.get(CalorieRow, d) or CalorieRow(date=d)
            row.level, row.reason = int(level), reason
            s.add(row)
            s.commit()

    def calorie_entries(self, start: date, end: date) -> list[dict]:
        with self.Session() as s:
            rows = s.scalars(select(CalorieRow).where(CalorieRow.date >= start, CalorieRow.date <= end).order_by(CalorieRow.date))
            return [{"date": r.date, "level": r.level, "reason": r.reason} for r in rows]

    # ---------- travel ----------
    def set_travel(self, start: date, end: date, on: bool) -> None:
        from datetime import timedelta
        with self.Session() as s:
            d = start
            while d <= end:
                row = s.get(TravelRow, d)
                if on and row is None:
                    s.add(TravelRow(date=d))
                elif not on and row is not None:
                    s.delete(row)
                d += timedelta(days=1)
            s.commit()

    def is_travel(self, d: date) -> bool:
        with self.Session() as s:
            return s.get(TravelRow, d) is not None

    def travel_days(self, start: date, end: date) -> set[date]:
        with self.Session() as s:
            return {r.date for r in s.scalars(select(TravelRow).where(TravelRow.date >= start, TravelRow.date <= end))}

    # ---------- export ----------
    def export_all(self) -> dict:
        iso = lambda v: v.isoformat() if v is not None else None  # noqa: E731
        with self.Session() as s:
            return {
                "days": [{"date": iso(r.date), "mode": r.mode, "score": r.score, "grade": r.grade,
                          "locked_at": iso(r.locked_at), "notes": r.notes} for r in s.scalars(select(DayRow).order_by(DayRow.date))],
                "checks": [{"date": iso(r.date), "item_key": r.item_key, "state": r.state, "value_num": r.value_num,
                            "value_text": r.value_text, "ts": iso(r.ts)} for r in s.scalars(select(CheckRow).order_by(CheckRow.date, CheckRow.item_key))],
                "lifts": [{"date": iso(r.date), "exercise_key": r.exercise_key, "set_no": r.set_no, "reps": r.reps,
                           "weight_kg": r.weight_kg} for r in s.scalars(select(LiftRow).order_by(LiftRow.date, LiftRow.exercise_key, LiftRow.set_no))],
                "weights": [{"date": iso(r.date), "kg": r.kg} for r in s.scalars(select(WeightRow).order_by(WeightRow.date))],
                "rule_breaks": [{"date": iso(r.date), "rule_key": r.rule_key} for r in s.scalars(select(RuleBreakRow).order_by(RuleBreakRow.date))],
                "calorie_log": [{"date": iso(r.date), "level": r.level, "reason": r.reason} for r in s.scalars(select(CalorieRow).order_by(CalorieRow.date))],
                "travel_days": [iso(r.date) for r in s.scalars(select(TravelRow).order_by(TravelRow.date))],
                "settings": {r.key: r.value for r in s.scalars(select(SettingRow)) if r.key != "pin_hash"},
            }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_db.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add transform/db.py tests/test_db.py
git commit -m "SQLite store: days, checks, lifts, weights, rules, settings, push subs, calorie level, travel"
```

---

### Task 6: Auth and day API

**Files:**
- Create: `transform/auth.py`, `transform/api/__init__.py`, `transform/api/deps.py`, `transform/api/routes_auth.py`, `transform/api/routes_day.py`, `tests/test_api.py`
- Modify: `transform/app.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `Store`, `Plan`, `score_day`, `Check`, `streak`.
- Produces:
  - `auth.mint_token(secret) -> str`, `auth.verify_token(secret, token) -> bool`, `auth.RateLimiter(max_attempts=5, window_sec=900).allow(key) -> bool`, `.record_failure(key)`
  - `deps.today_ist(settings) -> date`, `deps.is_frozen(d, now) -> bool`, `deps.resolve_day(store, plan, d) -> DayPlan` (applies travel, calorie level, protein-target setting), `deps.build_day_payload(store, plan, d, today) -> dict`
  - `create_app(settings, store, plan, start_scheduler)` now mounts `/api` and serves `static/` at `/`.
  - Routes: `POST /api/auth`, `GET /api/today`, `GET /api/day/{date}`, `PUT /api/check`, `PUT /api/lift`, `PUT /api/rule`, `PUT /api/weight`, `GET /api/weight?from&to`.
  - Day payload shape (used by frontend):
    ```
    {date, today, frozen, plan:{mode, day_type, block_index, adaptation, calorie_level, protein_target, bed_by,
      schedule:[{key,time,label,points}], meals:[{key,time,label,detail,protein,kcal,optional}],
      court_title, court_exercises:[{key,name,sets,rep_min,rep_max,reps_label,load,logs_sets}],
      gym_title, gym_exercises:[...], travel_circuit:[...], supplements:[{key,time,label}], rules:[{key,label}], sunday_prep:[...]},
     checks:{item_key:{state,value_num,value_text}}, lifts:[{exercise_key,set_no,reps,weight_kg}], rule_breaks:[...],
     score:{total,breakdown,grade,protein}, stored_score, streak, weight, progression:[{exercise_key,message}]}
    ```
    `progression` is filled by Task 7; here it is `[]`.

- [ ] **Step 1: Update conftest and write failing API tests**

Replace `tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient

from transform.config import Settings
from transform.db import Store
from transform.plan import load_plan


@pytest.fixture(scope="session")
def plan():
    return load_plan()


@pytest.fixture
def settings(tmp_path):
    return Settings(pin="1234", secret="test-secret", data_dir=str(tmp_path), vapid_private_key="",
                    vapid_public_key="", vapid_claims_email="mailto:test@example.com", tz="Asia/Kolkata", port=8000)


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def client(settings, store, plan):
    from transform.app import create_app

    app = create_app(settings, store=store, plan=plan, start_scheduler=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    r = client.post("/api/auth", json={"pin": "1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}
```

`tests/test_api.py`:
```python
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from transform.api import deps

IST = ZoneInfo("Asia/Kolkata")


def test_health_and_static(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/")
    assert r.status_code == 200 and "<title>Transform</title>" in r.text


def test_auth_flow(client):
    assert client.get("/api/today").status_code == 401
    assert client.post("/api/auth", json={"pin": "9999"}).status_code == 401
    r = client.post("/api/auth", json={"pin": "1234"})
    assert r.status_code == 200
    tok = r.json()["token"]
    assert client.get("/api/today", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    assert client.get("/api/today", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_auth_rate_limit(client):
    for _ in range(5):
        client.post("/api/auth", json={"pin": "0"})
    assert client.post("/api/auth", json={"pin": "1234"}).status_code == 429


def test_today_payload_shape(client, auth):
    r = client.get("/api/today", headers=auth)
    body = r.json()
    assert body["date"] == body["today"]
    assert body["frozen"] is False
    assert body["plan"]["protein_target"] in (185, 150)
    assert body["score"]["total"] == 0 and body["streak"] == 0
    assert body["checks"] == {} and body["lifts"] == [] and body["progression"] == []


def test_check_lift_rule_weight_round_trip(client, auth):
    today = client.get("/api/today", headers=auth).json()["today"]
    r = client.put("/api/check", headers=auth, json={"date": today, "item_key": "meal:lunch", "state": "swapped",
                                                      "value_num": 30, "value_text": "dal rice"})
    assert r.status_code == 200
    assert r.json()["checks"]["meal:lunch"] == {"state": "swapped", "value_num": 30.0, "value_text": "dal rice"}
    assert r.json()["score"]["protein"] == 30
    r = client.put("/api/check", headers=auth, json={"date": today, "item_key": "meal:lunch", "state": "untouched"})
    assert "meal:lunch" not in r.json()["checks"]
    r = client.put("/api/lift", headers=auth, json={"date": today, "exercise_key": "bench_press", "set_no": 1, "reps": 8, "weight_kg": 60})
    assert r.json()["lifts"] == [{"exercise_key": "bench_press", "set_no": 1, "reps": 8, "weight_kg": 60.0}]
    r = client.put("/api/rule", headers=auth, json={"date": today, "rule_key": "no_fried", "broken": True})
    assert r.json()["rule_breaks"] == ["no_fried"]
    r = client.put("/api/weight", headers=auth, json={"date": today, "kg": 91.6})
    assert r.status_code == 200 and r.json()["weight"] == 91.6
    r = client.get(f"/api/weight?from={today}&to={today}", headers=auth)
    assert r.json()["series"] == [{"date": today, "kg": 91.6}]
    assert r.json()["ma7"] == [{"date": today, "kg": 91.6}]
    assert "corridor" in r.json() and "projection" in r.json()


def test_validation_errors(client, auth):
    today = client.get("/api/today", headers=auth).json()["today"]
    assert client.put("/api/check", headers=auth, json={"date": today, "item_key": "meal:lunch", "state": "eaten"}).status_code == 422
    assert client.put("/api/check", headers=auth, json={"date": today, "item_key": "meal:nope", "state": "done"}).status_code == 400
    assert client.put("/api/rule", headers=auth, json={"date": today, "rule_key": "nope", "broken": True}).status_code == 400
    assert client.put("/api/weight", headers=auth, json={"date": today, "kg": 5}).status_code == 422


def test_future_date_400(client, auth):
    tomorrow = (deps.today_ist(client.app.state.settings) + timedelta(days=1)).isoformat()
    r = client.put("/api/check", headers=auth, json={"date": tomorrow, "item_key": "badminton", "state": "done"})
    assert r.status_code == 400


def test_frozen_day_409(client, auth):
    old = (deps.today_ist(client.app.state.settings) - timedelta(days=4)).isoformat()
    r = client.put("/api/check", headers=auth, json={"date": old, "item_key": "badminton", "state": "done"})
    assert r.status_code == 409
    assert client.get(f"/api/day/{old}", headers=auth).json()["frozen"] is True
    two_days_ago = (deps.today_ist(client.app.state.settings) - timedelta(days=2)).isoformat()
    r = client.put("/api/check", headers=auth, json={"date": two_days_ago, "item_key": "badminton", "state": "done"})
    assert r.status_code == 200


def test_is_frozen_boundary():
    d = date(2026, 10, 5)
    assert deps.is_frozen(d, datetime(2026, 10, 7, 23, 59, tzinfo=IST)) is False
    assert deps.is_frozen(d, datetime(2026, 10, 8, 0, 0, tzinfo=IST)) is True


def test_past_day_edit_rescores_stored(client, auth, store):
    yesterday = deps.today_ist(client.app.state.settings) - timedelta(days=1)
    store.upsert_day(yesterday, score=0, grade="red")
    client.put("/api/check", headers=auth, json={"date": yesterday.isoformat(), "item_key": "badminton", "state": "done"})
    assert store.get_day(yesterday).score == 8


def test_travel_and_level_applied_in_resolve(client, auth, store, plan):
    today = deps.today_ist(client.app.state.settings)
    store.set_travel(today, today, True)
    assert client.get("/api/today", headers=auth).json()["plan"]["mode"] == "travel"
    store.set_travel(today, today, False)
    store.set_calorie_level(today, 1, "test")
    assert client.get("/api/today", headers=auth).json()["plan"]["calorie_level"] in ("level1", "maintenance")
    store.set_setting("protein_target", "190")
    assert client.get("/api/today", headers=auth).json()["plan"]["protein_target"] == 190
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_api.py -v`
Expected: FAIL (401s or import errors; `/api/auth` does not exist).

- [ ] **Step 3: Write `transform/auth.py`**

```python
from __future__ import annotations

import hashlib
import hmac
import time


def mint_token(secret: str) -> str:
    return hmac.new(secret.encode(), b"transform-token-v1", hashlib.sha256).hexdigest()


def verify_token(secret: str, token: str | None) -> bool:
    if not token:
        return False
    return hmac.compare_digest(mint_token(secret), token)


def verify_pin(expected: str, given: str) -> bool:
    return hmac.compare_digest(expected.encode(), given.encode())


class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_sec: int = 900):
        self.max_attempts, self.window = max_attempts, window_sec
        self._fails: dict[str, list[float]] = {}

    def _prune(self, key: str) -> list[float]:
        now = time.monotonic()
        lst = [t for t in self._fails.get(key, []) if now - t < self.window]
        self._fails[key] = lst
        return lst

    def allow(self, key: str) -> bool:
        return len(self._prune(key)) < self.max_attempts

    def record_failure(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
```

- [ ] **Step 4: Write `transform/api/deps.py`**

```python
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
    if not verify_token(settings.secret, token):
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
    }
```

- [ ] **Step 5: Write the routers**

`transform/api/routes_auth.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import RateLimiter, mint_token, verify_pin
from .deps import get_settings

router = APIRouter()
limiter = RateLimiter()


class PinIn(BaseModel):
    pin: str


@router.post("/auth")
def auth(body: PinIn, request: Request, settings=Depends(get_settings)):
    key = request.client.host if request.client else "anon"
    if not limiter.allow(key):
        raise HTTPException(429, "too many attempts, wait 15 minutes")
    if not verify_pin(settings.pin, body.pin):
        limiter.record_failure(key)
        raise HTTPException(401, "wrong PIN")
    limiter.reset(key)
    return {"token": mint_token(settings.secret)}
```

`transform/api/routes_day.py`:
```python
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..guardrails import progression_prompts, rescore
from ..timeline import corridor_band, moving_average, projection
from . import deps

router = APIRouter(dependencies=[Depends(deps.require_auth)])


class CheckIn(BaseModel):
    date: date
    item_key: str
    state: Literal["done", "swapped", "skipped", "untouched"]
    value_num: float | None = Field(default=None, ge=0, le=500)
    value_text: str | None = Field(default=None, max_length=300)


class LiftIn(BaseModel):
    date: date
    exercise_key: str
    set_no: int = Field(ge=1, le=10)
    reps: int = Field(ge=0, le=100)
    weight_kg: float = Field(ge=0, le=500)


class RuleIn(BaseModel):
    date: date
    rule_key: str
    broken: bool


class WeightIn(BaseModel):
    date: date
    kg: float = Field(ge=40, le=200)


def _payload(store, plan, settings, d: date) -> dict:
    dp = deps.resolve_day(store, plan, d)
    return deps.build_day_payload(store, plan, d, settings, progression=progression_prompts(store, dp))


def _after_write(store, plan, settings, d: date) -> dict:
    if d < deps.today_ist(settings):
        rescore(store, plan, d)
    return _payload(store, plan, settings, d)


@router.get("/today")
def today(store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    return _payload(store, plan, settings, deps.today_ist(settings))


@router.get("/day/{d}")
def day(d: str, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    return _payload(store, plan, settings, deps.parse_date(d))


@router.put("/check")
def put_check(body: CheckIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    deps.assert_writable(body.date, settings)
    dp = deps.resolve_day(store, plan, body.date)
    if body.item_key not in deps.valid_item_keys(dp):
        raise HTTPException(400, f"unknown item {body.item_key}")
    if body.state == "untouched":
        store.delete_check(body.date, body.item_key)
    else:
        store.upsert_check(body.date, body.item_key, body.state, body.value_num, body.value_text)
    return _after_write(store, plan, settings, body.date)


@router.put("/lift")
def put_lift(body: LiftIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    deps.assert_writable(body.date, settings)
    store.upsert_lift(body.date, body.exercise_key, body.set_no, body.reps, body.weight_kg)
    return _after_write(store, plan, settings, body.date)


@router.put("/rule")
def put_rule(body: RuleIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    deps.assert_writable(body.date, settings)
    if body.rule_key not in {r["key"] for r in plan.rules}:
        raise HTTPException(400, "unknown rule")
    store.set_rule_break(body.date, body.rule_key, body.broken)
    return _after_write(store, plan, settings, body.date)


@router.put("/weight")
def put_weight(body: WeightIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    if body.date > deps.today_ist(settings):
        raise HTTPException(400, "cannot log a future day")
    store.set_weight(body.date, body.kg)
    return _payload(store, plan, settings, body.date)


@router.get("/weight")
def get_weight(from_: str | None = Query(default=None, alias="from"), to: str | None = None,
               store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    today = deps.today_ist(settings)
    start = deps.parse_date(from_) if from_ else plan.start_date
    end = deps.parse_date(to) if to else today
    series = store.get_weights(start, end)
    all_series = store.all_weights()
    ma = moving_average(series, 7)
    corridor = []
    d = start
    while d <= end:
        band = corridor_band(plan.checkpoints, d, plan.band_kg)
        if band:
            corridor.append({"date": d.isoformat(), "lo": band[0], "hi": band[1], "mid": round((band[0] + band[1]) / 2, 3)})
        d += timedelta(days=1)
    proj = projection(all_series, float(plan.meta["goal_weight"]))
    return {
        "series": [{"date": d.isoformat(), "kg": kg} for d, kg in series],
        "ma7": [{"date": d.isoformat(), "kg": kg} for d, kg in ma],
        "corridor": corridor,
        "projection": proj.isoformat() if proj else None,
        "goal": float(plan.meta["goal_weight"]),
        "start_weight": float(plan.meta["start_weight"]),
        "checkpoints": [{"date": d.isoformat(), "kg": kg} for d, kg in plan.checkpoints],
        "creatine_loading_until": (plan.start_date + timedelta(days=14)).isoformat(),
    }
```

`transform/api/__init__.py`:
```python
from fastapi import APIRouter

from .routes_auth import router as auth_router
from .routes_day import router as day_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(day_router)
```

Until Task 7 exists, create a stub `transform/guardrails.py` so imports resolve:
```python
from __future__ import annotations


def rescore(store, plan, d):
    from .api.deps import resolve_day
    from .scoring import score_day
    dp = resolve_day(store, plan, d)
    r = score_day(dp, store.get_checks(d), store.get_rule_breaks(d))
    store.upsert_day(d, mode=dp.mode, score=r.total, grade=r.grade)
    return r


def progression_prompts(store, dp):
    return []
```

- [ ] **Step 6: Update `transform/app.py`**

```python
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def create_app(settings: Settings, store=None, plan=None, start_scheduler: bool = False) -> FastAPI:
    app = FastAPI(title="Transform", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.store = store
    app.state.plan = plan

    @app.get("/health")
    def health():
        return {"status": "ok"}

    from .api import api_router
    app.include_router(api_router)

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js")
    def sw():
        return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript",
                            headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    if start_scheduler and store is not None and plan is not None:
        from .scheduler import build_scheduler
        app.state.scheduler = build_scheduler(store, plan, settings)
        app.state.scheduler.start()

    return app
```

Create a minimal `static/index.html` now so `test_health_and_static` passes (Task 10 replaces it):
```html
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Transform</title></head><body>loading</body></html>
```
and an empty `static/sw.js`.

- [ ] **Step 7: Run tests**

Run: `pytest tests/ -v`
Expected: all PASS, including `test_past_day_edit_rescores_stored` via the stub `rescore`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Auth (PIN → HMAC token, rate limit) and day API: today, day, check, lift, rule, weight"
```

---

### Task 7: Guardrails, midnight close, progression

**Files:**
- Replace: `transform/guardrails.py`
- Create: `tests/test_guardrails.py`

**Interfaces:**
- Consumes: `Store`, `Plan`, `deps.resolve_day`, `score_day`, `bed_minutes`.
- Produces:
  - `rescore(store, plan, d) -> ScoreResult` (recomputes and stores score/grade/mode; no guardrails)
  - `close_day(store, plan, d, now) -> dict` `{date, score, grade, bump: str | None}`: textless swaps → skipped, rescore, set `locked_at=now`, run guardrails
  - `catch_up(store, plan, today, now) -> list[dict]`: closes every day from `max(start_date, today-60)` to `today-1` whose row has no `locked_at`
  - `strength_drop(store, dp) -> list[str]`: gym exercise keys whose top weight fell on two consecutive sessions ending on `dp.date`
  - `sleep_rule_hit(store, d) -> bool`: bed later than 00:30 on d, d-1, d-2
  - `bump_level(store, d, reason, level=1, days=7) -> None`: sets level for d+1..d+days, never lowering
  - `progression_prompts(store, dp) -> list[dict]` `{exercise_key, name, message}`

- [ ] **Step 1: Write failing tests**

`tests/test_guardrails.py`:
```python
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from transform.db import Store
from transform.guardrails import (bump_level, catch_up, close_day, progression_prompts, sleep_rule_hit,
                                  strength_drop)
from transform.plan import load_plan

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 21, 0, 5, tzinfo=IST)


@pytest.fixture(scope="module")
def plan():
    return load_plan()


@pytest.fixture
def store():
    return Store(":memory:")


def test_close_day_reverts_textless_swap(store, plan):
    d = date(2026, 10, 5)
    store.upsert_check(d, "meal:lunch", "swapped", value_num=30)
    store.upsert_check(d, "meal:dinner", "swapped", value_num=40, value_text="paneer at hotel")
    out = close_day(store, plan, d, NOW)
    checks = store.get_checks(d)
    assert checks["meal:lunch"].state == "skipped"
    assert checks["meal:dinner"].state == "swapped"
    row = store.get_day(d)
    assert row.locked_at is not None and row.score == out["score"] and row.grade == out["grade"]


def test_strength_drop_two_consecutive(store, plan):
    for d, w in [(date(2026, 10, 6), 65), (date(2026, 10, 13), 62.5), (date(2026, 10, 20), 60)]:
        store.upsert_lift(d, "bench_press", 1, 8, w)
    dp = plan.resolve(date(2026, 10, 20))
    assert strength_drop(store, dp) == ["bench_press"]
    store.upsert_lift(date(2026, 10, 13), "bench_press", 1, 8, 65)  # no longer monotone
    assert strength_drop(store, dp) == []


def test_sleep_rule_three_late_nights(store):
    d = date(2026, 10, 20)
    for i, t in enumerate(["00:45", "01:00", "00:35"]):
        store.upsert_check(d - timedelta(days=i), "sleep", "done", value_text=t)
    assert sleep_rule_hit(store, d) is True
    store.upsert_check(d - timedelta(days=1), "sleep", "done", value_text="23:00")
    assert sleep_rule_hit(store, d) is False


def test_bump_level_sets_seven_days_never_lowers(store):
    d = date(2026, 10, 20)
    store.set_calorie_level(d + timedelta(days=3), 2, "manual")
    bump_level(store, d, "strength drop")
    assert store.get_calorie_level(d) == 0
    assert store.get_calorie_level(d + timedelta(days=1)) == 1
    assert store.get_calorie_level(d + timedelta(days=3)) == 2
    assert store.get_calorie_level(d + timedelta(days=7)) == 1
    assert store.get_calorie_level(d + timedelta(days=8)) == 0


def test_close_day_applies_bump_on_strength_drop(store, plan):
    for d, w in [(date(2026, 10, 6), 65), (date(2026, 10, 13), 62.5), (date(2026, 10, 20), 60)]:
        store.upsert_lift(d, "bench_press", 1, 8, w)
    store.upsert_check(date(2026, 10, 20), "gym", "done")
    out = close_day(store, plan, date(2026, 10, 20), NOW)
    assert out["bump"] and "bench_press" in out["bump"]
    assert store.get_calorie_level(date(2026, 10, 21)) == 1


def test_catch_up_closes_only_unscored_days(store, plan):
    today = date(2026, 10, 10)
    store.upsert_check(date(2026, 10, 7), "badminton", "done")
    store.upsert_day(date(2026, 10, 8), score=95, grade="green", locked_at=NOW)
    closed = catch_up(store, plan, today, NOW)
    dates = [c["date"] for c in closed]
    assert date(2026, 10, 8) not in dates
    assert date(2026, 10, 7) in dates and date(2026, 10, 9) in dates and date(2026, 10, 5) in dates
    assert date(2026, 10, 10) not in dates
    assert store.get_day(date(2026, 10, 9)).score == 0
    assert store.get_day(date(2026, 10, 8)).score == 95
    assert catch_up(store, plan, today, NOW) == []


def test_progression_prompt_after_two_top_sessions(store, plan):
    dp = plan.resolve(date(2026, 10, 20))  # Tue, not adaptation
    for d in [date(2026, 10, 6), date(2026, 10, 13)]:
        for s in range(1, 5):
            store.upsert_lift(d, "bench_press", s, 8, 60)
    prompts = progression_prompts(store, dp)
    assert prompts == [{"exercise_key": "bench_press", "name": "Bench press", "message": "Bench press: +2.5 kg today (hit 4×8 twice)"}]
    store.upsert_lift(date(2026, 10, 13), "bench_press", 4, 7, 60)
    assert progression_prompts(store, dp) == []


def test_no_progression_in_adaptation(store, plan):
    dp = plan.resolve(date(2026, 10, 13))
    for d in [date(2026, 9, 29), date(2026, 10, 6)]:
        for s in range(1, 5):
            store.upsert_lift(d, "bench_press", s, 8, 60)
    assert progression_prompts(store, dp) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_guardrails.py -v`
Expected: FAIL (`ImportError` on `bump_level` etc.).

- [ ] **Step 3: Write `transform/guardrails.py`**

```python
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
    elif sleep_rule_hit(store, d):
        bump = "three nights in bed after 00:30; dinner roti added for 7 days"
    if bump:
        bump_level(store, d, bump)
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
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add transform/guardrails.py tests/test_guardrails.py
git commit -m "Guardrails: midnight close, textless-swap revert, strength/sleep bumps, catch-up, progression prompts"
```

---

### Task 8: Reports and meta routes

**Files:**
- Create: `transform/reports.py`, `transform/api/routes_meta.py`, `tests/test_reports.py`
- Modify: `transform/api/__init__.py` (include meta router)

**Interfaces:**
- Produces:
  - `reports.week_scorecard(store, plan, iso_year, iso_week, today, settings_tz) -> dict` with keys `week, start, end, days:[{date, score, grade, mode}], avg_score, green_days, protein_avg, sessions_done, sessions_target, lifts_progressed, weight_start, weight_end, weight_change, verdict, on_plan`
  - `reports.history(store, plan, start, end, today) -> list[{date, score, grade, mode, logged}]`
  - Routes (auth required unless stated): `GET /api/plan` (all 7 weekdays), `GET /api/plan/{weekday}`, `GET /api/history?from&to`, `GET /api/week/{iso_week}` (`2026-W41`), `GET /api/settings`, `PUT /api/settings`, `PUT /api/travel`, `GET /api/export`, `POST /api/push/subscribe`, `DELETE /api/push/subscribe`, `GET /api/push/vapid-public-key` (no auth).
  - Settings payload: `{protein_target, notif_times, notif_enabled: {key: bool}, vapid_public_key, start_date, start_weight, goal_weight, calorie_level_today, diet_break, travel_days_upcoming}`

- [ ] **Step 1: Write failing tests**

`tests/test_reports.py`:
```python
from datetime import date, timedelta

from transform.reports import history, week_scorecard


def _perfect(store, plan, d):
    dp = plan.resolve(d)
    for s in dp.schedule:
        if s.points > 0:
            store.upsert_check(d, s.key, "done")
    for m in dp.meals:
        if not m.optional:
            store.upsert_check(d, f"meal:{m.key}", "done")
    store.upsert_check(d, "meal:bedtime", "done")
    for s in dp.supplements:
        store.upsert_check(d, f"supp:{s['key']}", "done")
    store.upsert_check(d, "sleep", "done", value_text="22:00")


def test_week_scorecard_metrics(store, plan):
    monday = date(2026, 10, 12)
    for i in range(7):
        d = monday + timedelta(days=i)
        _perfect(store, plan, d)
        store.upsert_day(d, score=100 if i < 6 else 60, grade="green" if i < 6 else "red")
        store.set_weight(d, 91.0 - 0.1 * i)
    for i in range(7):
        store.set_weight(monday - 7 + timedelta(days=i), 92.0)
    store.upsert_lift(date(2026, 10, 6), "bench_press", 1, 8, 60)
    store.upsert_lift(date(2026, 10, 13), "bench_press", 1, 8, 62.5)
    sc = week_scorecard(store, plan, 2026, 42, today=date(2026, 10, 19))
    assert sc["start"] == "2026-10-12" and sc["end"] == "2026-10-18"
    assert sc["avg_score"] == round((600 + 60) / 7, 1)
    assert sc["green_days"] == 6
    assert sc["sessions_done"] == 6 and sc["sessions_target"] == 6
    assert sc["lifts_progressed"] == 1
    assert sc["protein_avg"] == 187.0
    assert sc["weight_change"] < 0
    assert sc["verdict"] in ("ahead", "on_pace", "behind")
    assert sc["on_plan"] is True


def test_week_uses_live_score_for_unclosed_days(store, plan):
    monday = date(2026, 10, 12)
    _perfect(store, plan, monday)
    sc = week_scorecard(store, plan, 2026, 42, today=date(2026, 10, 12))
    assert sc["days"][0]["score"] == 100
    assert sc["days"][1]["score"] is None  # future


def test_history_marks_logged(store, plan):
    store.upsert_check(date(2026, 10, 6), "badminton", "done")
    store.upsert_day(date(2026, 10, 5), score=0, grade="red")
    rows = history(store, plan, date(2026, 10, 5), date(2026, 10, 7), today=date(2026, 10, 7))
    assert [r["date"] for r in rows] == ["2026-10-05", "2026-10-06", "2026-10-07"]
    assert rows[0]["logged"] is False and rows[1]["logged"] is True
    assert rows[1]["score"] == 8  # live score, not yet closed


def test_meta_routes(client, auth, store):
    assert len(client.get("/api/plan", headers=auth).json()["days"]) == 7
    assert client.get("/api/plan/3", headers=auth).json()["gym_title"] == "Lower"
    assert client.get("/api/plan/9", headers=auth).status_code == 422
    assert client.get("/api/week/2026-W41", headers=auth).json()["week"] == "2026-W41"
    assert client.get("/api/week/bad", headers=auth).status_code == 422
    assert client.get("/api/history?from=2026-10-05&to=2026-10-07", headers=auth).status_code == 200
    s = client.get("/api/settings", headers=auth).json()
    assert s["protein_target"] == 185 and "wake" in s["notif_times"] and s["notif_enabled"]["wake"] is True
    r = client.put("/api/settings", headers=auth, json={"protein_target": 190, "notif_enabled": {"wake": False}})
    assert r.json()["protein_target"] == 190 and r.json()["notif_enabled"]["wake"] is False
    assert client.put("/api/settings", headers=auth, json={"protein_target": 50}).status_code == 422
    r = client.put("/api/travel", headers=auth, json={"start": "2026-10-20", "end": "2026-10-22", "on": True})
    assert r.status_code == 200 and store.is_travel(date(2026, 10, 21))
    assert client.put("/api/travel", headers=auth, json={"start": "2026-10-22", "end": "2026-10-20", "on": True}).status_code == 422
    assert client.get("/api/export", headers=auth).json()["travel_days"] == ["2026-10-20", "2026-10-21", "2026-10-22"]
    assert client.get("/api/push/vapid-public-key").json() == {"key": ""}
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "p", "auth": "a"}}
    assert client.post("/api/push/subscribe", headers=auth, json=sub).status_code == 200
    assert store.list_subscriptions()[0]["endpoint"] == "https://push.example/abc"
    assert client.request("DELETE", "/api/push/subscribe", headers=auth, json={"endpoint": "https://push.example/abc"}).status_code == 200
    assert store.list_subscriptions() == []
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_reports.py -v`
Expected: FAIL with `ModuleNotFoundError: transform.reports`

- [ ] **Step 3: Write `transform/reports.py`**

```python
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
        if d > today:
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
    ma = moving_average(series, 7)
    return ma[-1][1]


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
```

- [ ] **Step 4: Write `transform/api/routes_meta.py` and include it**

```python
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path
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
def get_history(from_: str = None, to: str = None, store=Depends(deps.get_store), plan=Depends(deps.get_plan),
                settings=Depends(deps.get_settings)):
    # FastAPI maps query param "from" via alias below
    raise HTTPException(500, "replaced")


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
```

Replace the placeholder `get_history` above with the real one (FastAPI needs `Query(alias="from")`):
```python
from fastapi import Query


@protected.get("/history")
def get_history(from_: str | None = Query(default=None, alias="from"), to: str | None = None,
                store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    today = deps.today_ist(settings)
    start = deps.parse_date(from_) if from_ else today - timedelta(days=90)
    end = deps.parse_date(to) if to else today
    if end < start or (end - start).days > 400:
        raise HTTPException(422, "bad range")
    return {"days": history(store, plan, start, end, today)}
```
(Write the file with only the real `get_history`; the placeholder exists in this plan only to show the import need.)

`transform/api/__init__.py`:
```python
from fastapi import APIRouter

from .routes_auth import router as auth_router
from .routes_day import router as day_router
from .routes_meta import protected as meta_protected
from .routes_meta import router as meta_public

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(day_router)
api_router.include_router(meta_public)
api_router.include_router(meta_protected)
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add transform/reports.py transform/api tests/test_reports.py
git commit -m "Weekly scorecard, history, plan/settings/travel/export/push routes"
```

---

### Task 9: Web push and scheduler

**Files:**
- Create: `transform/push.py`, `transform/scheduler.py`, `tests/test_push.py`

**Interfaces:**
- Produces:
  - `push.send_push(store, settings, title, body, url="/", tag=None) -> int` (count sent; removes 404/410 subs; returns 0 silently when VAPID keys missing)
  - `scheduler.run_nudge(store, plan, settings, key, now) -> bool` (sends if enabled and the item for `key` is untouched today)
  - `scheduler.run_midnight(store, plan, settings, now) -> list[dict]` (catch_up + push yesterday's score and any bump)
  - `scheduler.run_weekly(store, plan, settings, now) -> dict`
  - `scheduler.build_scheduler(store, plan, settings) -> BackgroundScheduler`
  - Nudge key → item map: `wake→wake`, `whey_am→meal:whey_am`, `breakfast→meal:breakfast`, `lunch→meal:lunch`, `snack→meal:snack`, `dinner→meal:dinner`, `gym→gym`, `magnesium→supp:magnesium`, `log_day→(any scored item untouched)`.

- [ ] **Step 1: Write failing tests**

`tests/test_push.py`:
```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

from transform import push as push_mod
from transform import scheduler as sched
from transform.config import Settings

IST = ZoneInfo("Asia/Kolkata")


def vapid_settings(tmp_path):
    return Settings(pin="1", secret="s", data_dir=str(tmp_path), vapid_private_key="priv", vapid_public_key="pub",
                    vapid_claims_email="mailto:x@y.z")


class FakeResp:
    def __init__(self, status):
        self.status_code = status


def test_send_push_removes_dead_subscriptions(store, tmp_path, monkeypatch):
    store.add_subscription("https://a", "p", "a")
    store.add_subscription("https://dead", "p", "a")
    calls = []

    def fake_webpush(subscription_info, data, vapid_private_key, vapid_claims, ttl):
        calls.append(subscription_info["endpoint"])
        if subscription_info["endpoint"] == "https://dead":
            raise push_mod.WebPushException("gone", response=FakeResp(410))

    monkeypatch.setattr(push_mod, "webpush", fake_webpush)
    n = push_mod.send_push(store, vapid_settings(tmp_path), "t", "b")
    assert n == 1 and sorted(calls) == ["https://a", "https://dead"]
    assert [s["endpoint"] for s in store.list_subscriptions()] == ["https://a"]


def test_send_push_noop_without_keys(store, settings, monkeypatch):
    store.add_subscription("https://a", "p", "a")
    monkeypatch.setattr(push_mod, "webpush", lambda **kw: (_ for _ in ()).throw(AssertionError("should not send")))
    assert push_mod.send_push(store, settings, "t", "b") == 0


def test_run_nudge_only_when_untouched(store, plan, settings, monkeypatch):
    sent = []
    monkeypatch.setattr(sched, "send_push", lambda st, se, title, body, **kw: sent.append(title) or 1)
    now = datetime(2026, 10, 6, 13, 0, tzinfo=IST)
    assert sched.run_nudge(store, plan, settings, "lunch", now) is True
    store.upsert_check(date(2026, 10, 6), "meal:lunch", "done")
    assert sched.run_nudge(store, plan, settings, "lunch", now) is False
    assert sched.run_nudge(store, plan, settings, "gym", now) is True          # Tuesday has gym
    assert sched.run_nudge(store, plan, settings, "gym", datetime(2026, 10, 5, 18, 45, tzinfo=IST)) is False  # Monday no gym
    store.set_setting("notif_enabled", '{"lunch": false}')
    store.delete_check(date(2026, 10, 6), "meal:lunch")
    assert sched.run_nudge(store, plan, settings, "lunch", now) is False
    assert len(sent) == 2


def test_run_log_day_nudge_when_anything_missing(store, plan, settings, monkeypatch):
    monkeypatch.setattr(sched, "send_push", lambda *a, **kw: 1)
    now = datetime(2026, 10, 6, 22, 15, tzinfo=IST)
    assert sched.run_nudge(store, plan, settings, "log_day", now) is True


def test_run_midnight_closes_and_notifies(store, plan, settings, monkeypatch):
    sent = []
    monkeypatch.setattr(sched, "send_push", lambda st, se, title, body, **kw: sent.append((title, body)) or 1)
    store.upsert_check(date(2026, 10, 6), "badminton", "done")
    closed = sched.run_midnight(store, plan, settings, datetime(2026, 10, 7, 0, 5, tzinfo=IST))
    assert any(c["date"] == date(2026, 10, 6) for c in closed)
    assert store.get_day(date(2026, 10, 6)).locked_at is not None
    assert sent and "Oct 06" in sent[-1][0] or "6 Oct" in sent[-1][0] or "2026-10-06" in sent[-1][0]


def test_run_weekly_pushes_scorecard(store, plan, settings, monkeypatch):
    sent = []
    monkeypatch.setattr(sched, "send_push", lambda st, se, title, body, **kw: sent.append(title) or 1)
    sc = sched.run_weekly(store, plan, settings, datetime(2026, 10, 11, 21, 0, tzinfo=IST))
    assert sc["week"] == "2026-W41" and sent and "Week" in sent[0]


def test_build_scheduler_has_jobs(store, plan, settings):
    s = sched.build_scheduler(store, plan, settings)
    ids = {j.id for j in s.get_jobs()}
    assert {"nudge:wake", "nudge:lunch", "nudge:gym", "nudge:log_day", "midnight", "weekly"} <= ids
    assert str(s.timezone) == "Asia/Kolkata"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_push.py -v`
Expected: FAIL with `ModuleNotFoundError: transform.push`

- [ ] **Step 3: Write `transform/push.py`**

```python
from __future__ import annotations

import json
import logging

from pywebpush import WebPushException, webpush  # noqa: F401  (re-exported for tests)

from .config import Settings
from .db import Store

log = logging.getLogger("transform.push")


def send_push(store: Store, settings: Settings, title: str, body: str, url: str = "/", tag: str | None = None) -> int:
    if not settings.vapid_private_key or not settings.vapid_public_key:
        return 0
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or title})
    sent = 0
    for sub in store.list_subscriptions():
        info = {"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}
        try:
            webpush(subscription_info=info, data=payload, vapid_private_key=settings.vapid_private_key,
                    vapid_claims={"sub": settings.vapid_claims_email}, ttl=3600)
            sent += 1
        except WebPushException as e:  # pragma: no cover - branch tested via fake
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                store.remove_subscription(sub["endpoint"])
                log.info("removed dead push subscription %s", sub["endpoint"])
            else:
                log.warning("push failed (%s): %s", status, e)
        except Exception as e:  # noqa: BLE001
            log.warning("push error: %s", e)
    return sent
```

- [ ] **Step 4: Write `transform/scheduler.py`**

```python
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
        if item_key not in {s.key for s in dp.schedule} | {f"meal:{m.key}" for m in dp.meals} | {f"supp:{s['key']}" for s in dp.supplements}:
            return False
        if item_key in checks:
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
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add transform/push.py transform/scheduler.py tests/test_push.py
git commit -m "VAPID web push and IST scheduler: nudges, midnight close, weekly scorecard, boot catch-up"
```

---

### Task 10: PWA shell, API client, offline queue, Today view

**Files:**
- Replace: `static/index.html`, `static/sw.js`
- Create: `static/styles.css`, `static/manifest.json`, `static/icon.svg`, `static/app.js`, `static/views/today.js`, `tests/test_static.py`

**Interfaces:**
- Consumes: day payload from Task 6, `PUT /api/check|lift|rule|weight|travel`.
- Produces (for Task 11 views): `app.js` exports `api(path, {method, body})`, `state`, `toast(msg)`, `h(tag, attrs, ...children)` element builder, `fmtDate(iso, opts)`, `todayISO()`, `addDays(iso, n)`, `navigate(hash)`, `logout()`, `QueuedError`. Views export `render<Name>(root, params)`.
- Hash routes: `#today`, `#today/2026-10-05`, `#plan`, `#weight`, `#history`, `#settings`.

- [ ] **Step 1: Write a failing static-assets test**

`tests/test_static.py`:
```python
import os
import re

STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def test_shell_references_exist():
    html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
    assert "<title>Transform</title>" in html
    for ref in re.findall(r'(?:src|href)="/static/([^"]+)"', html):
        assert os.path.exists(os.path.join(STATIC, ref)), ref
    for view in ["today", "plan", "weight", "history", "settings"]:
        assert os.path.exists(os.path.join(STATIC, "views", f"{view}.js")), view
    sw = open(os.path.join(STATIC, "sw.js"), encoding="utf-8").read()
    assert "addEventListener('push'" in sw and "notificationclick" in sw


def test_sw_served_at_root(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_static.py -v`
Expected: FAIL (views missing, sw.js empty).

- [ ] **Step 3: Write `static/index.html`, `manifest.json`, `icon.svg`, `styles.css`**

`static/index.html`:
```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Transform">
<meta name="theme-color" content="#0b0b0c">
<link rel="manifest" href="/static/manifest.json">
<link rel="apple-touch-icon" href="/static/icon.svg">
<link rel="icon" href="/static/icon.svg">
<title>Transform</title>
<link rel="stylesheet" href="/static/styles.css">
</head>
<body>
<div id="login" class="login hidden">
  <div class="login-card">
    <div class="brand">TRANSFORM</div>
    <p class="muted">Enter your PIN</p>
    <form id="loginForm">
      <input id="pin" type="password" inputmode="numeric" autocomplete="one-time-code" placeholder="PIN" required>
      <button type="submit" class="btn primary">Unlock</button>
    </form>
    <p id="loginErr" class="err"></p>
  </div>
</div>
<main id="view" class="view"></main>
<nav id="tabs" class="tabs">
  <a href="#today" data-route="today">Today</a>
  <a href="#plan" data-route="plan">Plan</a>
  <a href="#weight" data-route="weight">Weight</a>
  <a href="#history" data-route="history">History</a>
  <a href="#settings" data-route="settings">Settings</a>
</nav>
<div id="toast" class="toast hidden"></div>
<script type="module" src="/static/app.js"></script>
</body>
</html>
```

`static/manifest.json`:
```json
{
  "name": "Transform",
  "short_name": "Transform",
  "start_url": "/#today",
  "scope": "/",
  "display": "standalone",
  "background_color": "#0b0b0c",
  "theme_color": "#0b0b0c",
  "icons": [{ "src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any" }]
}
```

`static/icon.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180"><rect width="180" height="180" rx="40" fill="#0b0b0c"/><path d="M40 60h100v16H98v70H82V76H40z" fill="#4ade80"/></svg>
```

`static/styles.css`: dark theme with CSS variables (`--bg`, `--card`, `--line`, `--text`, `--muted`, `--green`, `--amber`, `--red`, `--blue`, `--purple`, `--cyan`), classes: `.view .card .badge(.court .gym .rest .travel .diet_break) .btn(.primary .ghost .sm .danger .on .swap .skip) .tabs .score(.green .amber .red) .bar .item .time .body .title .detail .tick(.on .swap .skip) .sub .ex .sets .set .rules .rule(.broken) .login .toast .daytabs .heat .cell(.green .amber .red .today .sel) .kpi svg.chart .alert(.warn .info .bad) .frozen .hidden .muted .small .row .between .wrap`. Fixed bottom tab bar with `env(safe-area-inset-bottom)`. Full text is in the repo file; it carries no logic.

- [ ] **Step 4: Write `static/app.js`**

```js
import { renderToday } from './views/today.js';
import { renderPlan } from './views/plan.js';
import { renderWeight } from './views/weight.js';
import { renderHistory } from './views/history.js';
import { renderSettings } from './views/settings.js';

const TOKEN_KEY = 'tf_token';
const QUEUE_KEY = 'tf_queue';

export const state = { token: localStorage.getItem(TOKEN_KEY) };

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function todayISO() {
  const n = new Date();
  const ist = new Date(n.getTime() + (330 + n.getTimezoneOffset()) * 60000);
  return ist.toISOString().slice(0, 10);
}

export function fmtDate(iso, opts = { weekday: 'short', day: 'numeric', month: 'short' }) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-IN', opts);
}

export function addDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(y, m - 1, d + n);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
}

let toastTimer;
export function toast(msg, ms = 2200) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add('hidden'), ms);
}

export class QueuedError extends Error {}

function readQueue() { try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); } catch { return []; } }
function writeQueue(q) { localStorage.setItem(QUEUE_KEY, JSON.stringify(q)); }

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (e) {
    if (method === 'PUT') {
      const q = readQueue(); q.push({ path, body, ts: Date.now() }); writeQueue(q);
      toast('Offline — saved, will sync');
      throw new QueuedError('queued');
    }
    throw e;
  }
  if (res.status === 401) { logout(); throw new Error('unauthorised'); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    if (typeof detail !== 'string') detail = JSON.stringify(detail);
    throw new Error(detail);
  }
  return res.json();
}

export async function flushQueue() {
  const q = readQueue();
  if (!q.length || !navigator.onLine) return;
  writeQueue([]);
  for (const item of q) {
    try { await api(item.path, { method: 'PUT', body: item.body }); }
    catch (e) { if (!(e instanceof QueuedError)) console.warn('dropped queued write', item, e.message); }
  }
  if (!readQueue().length) { toast(`Synced ${q.length} change${q.length > 1 ? 's' : ''}`); render(); }
}

export function logout() {
  state.token = null; localStorage.removeItem(TOKEN_KEY);
  document.getElementById('login').classList.remove('hidden');
}

export function navigate(hash) { location.hash = hash; }

const routes = { today: renderToday, plan: renderPlan, weight: renderWeight, history: renderHistory, settings: renderSettings };

export async function render() {
  if (!state.token) { document.getElementById('login').classList.remove('hidden'); return; }
  const [route, ...rest] = (location.hash.slice(1) || 'today').split('/');
  const fn = routes[route] || renderToday;
  document.querySelectorAll('#tabs a').forEach(a => a.classList.toggle('active', a.dataset.route === (routes[route] ? route : 'today')));
  const root = document.getElementById('view');
  root.innerHTML = '<p class="muted">Loading…</p>';
  try { await fn(root, { param: rest.join('/') }); }
  catch (e) { if (!(e instanceof QueuedError)) root.innerHTML = `<div class="alert bad">${e.message}</div>`; }
}

document.getElementById('loginForm').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const pin = document.getElementById('pin').value;
  const err = document.getElementById('loginErr');
  err.textContent = '';
  try {
    const r = await fetch('/api/auth', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin }) });
    if (!r.ok) { err.textContent = r.status === 429 ? 'Too many attempts. Wait 15 min.' : 'Wrong PIN'; return; }
    state.token = (await r.json()).token; localStorage.setItem(TOKEN_KEY, state.token);
    document.getElementById('login').classList.add('hidden'); document.getElementById('pin').value = '';
    render();
  } catch { err.textContent = 'Network error'; }
});

window.addEventListener('hashchange', render);
window.addEventListener('online', flushQueue);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { flushQueue(); render(); } });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
flushQueue().finally(render);
```

- [ ] **Step 5: Write `static/views/today.js`**

Renders the day payload: header with prev/next day, score card with protein bar and breakdown, adaptation / progression / calorie-level alerts, weigh-in quick entry (today only), timeline of schedule items and meals merged by time, supplements card, rules card, Sunday prep, travel toggle. Builders: `tick(key, onclick)`, `schedRow(s)` (expands `court_block` / `gym` / `travel_circuit` into `exerciseList`), `exerciseList(exs)` (ticks for tick-only exercises, reps+kg inputs per set for `logs_sets`, saving via `PUT /api/lift` on change), `mealRow(m)` (Ate / Swapped / Skipped buttons; `detailInputs` with text + protein grams shown for swapped/skipped, and for done meals in travel mode), `sleepRow(s)` (time input → `PUT /api/check sleep`). After every PUT the API's returned payload replaces `current` and the view redraws, preserving scroll and the `expanded` set. Frozen days get the `.frozen` class. Full code is in the repo file.

- [ ] **Step 6: Write `static/sw.js`**

```js
const CACHE = 'transform-v1';
const SHELL = ['/', '/static/styles.css', '/static/app.js', '/static/manifest.json', '/static/icon.svg',
  '/static/views/today.js', '/static/views/plan.js', '/static/views/weight.js', '/static/views/history.js', '/static/views/settings.js'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;
  e.respondWith(
    fetch(e.request).then((res) => { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return res; })
      .catch(() => caches.match(e.request).then((r) => r || caches.match('/')))
  );
});
self.addEventListener('push', (e) => {
  let data = { title: 'Transform', body: '', url: '/#today', tag: 'transform' };
  try { data = { ...data, ...e.data.json() }; } catch {}
  e.waitUntil(self.registration.showNotification(data.title, { body: data.body, tag: data.tag, icon: '/static/icon.svg', badge: '/static/icon.svg', data: { url: data.url } }));
});
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/#today';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
```

Create placeholder modules so the shell loads before Task 11 (`static/views/plan.js`, `weight.js`, `history.js`, `settings.js`), each exporting its `render<Name>` that appends a "Coming next" paragraph.

- [ ] **Step 7: Run tests, then smoke in a browser**

Run: `pytest tests/ -v`
Expected: all PASS.

Smoke: `TRANSFORM_PIN=1234 TRANSFORM_SECRET=dev TRANSFORM_DATA_DIR=./data python -m transform`, open `http://localhost:8000/#today`: log in with 1234, tick badminton, mark lunch swapped with text, enter a bench set, confirm the score updates and survives reload.

- [ ] **Step 8: Commit**

```bash
git add static tests/test_static.py
git commit -m "PWA shell, API client with offline queue, service worker with push, Today view"
```

---

### Task 11: Plan, Weight, History, Settings views

**Files:**
- Replace: `static/views/plan.js`, `static/views/weight.js`, `static/views/history.js`, `static/views/settings.js`

**Interfaces:**
- Consumes: `GET /api/plan`, `GET /api/weight`, `PUT /api/weight`, `GET /api/history`, `GET /api/week/{w}`, `GET /api/day/{d}`, `GET/PUT /api/settings`, `PUT /api/travel`, `GET /api/export`, `POST/DELETE /api/push/subscribe`.

- [ ] **Step 1: `plan.js`** — fetches `/api/plan` once, weekday tabs (default = today's weekday), shows badge, schedule timeline, court block card, gym card, meals with protein/kcal, supplements, rules, Sunday prep.
- [ ] **Step 2: `weight.js`** — weigh-in input for today, KPI row (latest, 7-day avg, target today), status alert (ahead / on pace / behind + projection date), creatine-loading notice for the first 14 days, inline SVG chart: corridor band polygon, raw points, MA7 line, dashed goal line; checkpoint list.
- [ ] **Step 3: `history.js`** — ISO-week helper, week scorecard card (`/api/week`), 12-week heatmap (`/api/history`) coloured by grade with today outlined, tap a cell → day detail card (score, breakdown, logged items, swap texts) with an "Edit day" / "View day" link to `#today/<date>`.
- [ ] **Step 4: `settings.js`** — push enable/disable (VAPID key → `pushManager.subscribe` → `POST /api/push/subscribe`; iPhone install hint when not standalone), per-nudge toggles (`PUT /api/settings notif_enabled`), travel range (`PUT /api/travel`) with upcoming list, protein target, calorie level and diet-break info, Export JSON (authenticated fetch → blob download), Lock app.

Full code for all four is in the repo files.

- [ ] **Step 5: Run tests and smoke every tab**

Run: `pytest tests/ -v` → all PASS. Browser: Plan shows seven days; Weight accepts a value and draws the corridor; History shows heatmap + week card and opens a past day; Settings toggles save and travel range marks days.

- [ ] **Step 6: Commit**

```bash
git add static/views
git commit -m "Plan, Weight (corridor chart), History (heatmap + scorecard), Settings (push, travel, targets, export) views"
```

---

### Task 12: Documentation and Railway deployment

**Files:**
- Create: `CLAUDE.md` (replaces the deleted `claude.md`), `.env.example`

- [ ] **Step 1: Write `CLAUDE.md`**

Contents: purpose paragraph; run locally (`pip install -r requirements.txt`, env vars, `python -m transform`); test (`pytest tests/ -v`); deploy (`railway up --detach`); directory map from this plan's File Structure; env var table (`TRANSFORM_PIN`, `TRANSFORM_SECRET`, `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_EMAIL`, `TRANSFORM_DATA_DIR`, `TZ`, `PORT`); scoring table from spec §6; push schedule from spec §7.3; "How to change the plan" (edit `plan/plan.yaml`, run tests, commit, deploy); links to the spec and this plan.

`.env.example`:
```
TRANSFORM_PIN=1234
TRANSFORM_SECRET=replace-with-a-long-random-string
VAPID_PRIVATE_KEY=
VAPID_PUBLIC_KEY=
VAPID_CLAIMS_EMAIL=mailto:you@example.com
TRANSFORM_DATA_DIR=./data
TZ=Asia/Kolkata
```

- [ ] **Step 2: Generate VAPID keys** (output goes to Railway variables only, never git)

```bash
python - <<'PYEOF'
from py_vapid import Vapid, b64urlencode
from cryptography.hazmat.primitives import serialization
v = Vapid(); v.generate_keys()
priv = v.private_key.private_numbers().private_value.to_bytes(32, 'big')
pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print("VAPID_PRIVATE_KEY=" + b64urlencode(priv))
print("VAPID_PUBLIC_KEY=" + b64urlencode(pub))
PYEOF
```

- [ ] **Step 3: Create the Railway service and volume, set variables, deploy**

```bash
cd /Users/varunsaini/Desktop/transform
railway init --name transform          # or `railway link` to an existing project
railway volume add --mount-path /data
railway variables --set TRANSFORM_PIN=<pin> --set TRANSFORM_SECRET=$(openssl rand -hex 32) \
  --set VAPID_PRIVATE_KEY=<step 2> --set VAPID_PUBLIC_KEY=<step 2> \
  --set VAPID_CLAIMS_EMAIL=mailto:hellovarunsaini@gmail.com --set TZ=Asia/Kolkata
railway up --detach
railway domain
railway logs --lines 50
```
The PIN is the user's choice: ask for it, or generate one and tell them. Never commit it.

- [ ] **Step 4: Verify the deployment**

- `curl https://<domain>/health` → `{"status":"ok"}`
- iPhone Safari: Share → Add to Home Screen, open from the icon, log in, Settings → Enable push, accept the prompt. Log one item on Today, reload, confirm it persisted.
- `railway logs` shows the scheduler jobs and the boot catch-up.

- [ ] **Step 5: Commit and push**

```bash
git add CLAUDE.md .env.example
git commit -m "Docs: CLAUDE.md for the tracker, env example"
git push origin main
```

---

## Self-review notes

- Spec coverage: screens (T10–T11), programme + meals + supplements (T2 YAML), progression + block rotation (T2, T7), nutrition levels + guardrails + diet break (T2, T7), timeline corridor (T4, T6 `/weight`), scoring (T3), midnight close + 48 h freeze (T6 deps, T7), weekly scorecard (T8, T9), data model + API (T5, T6, T8), push schedule (T9), auth (T6), offline queue (T10), export (T8), deploy (T1, T12). The spec's `travel_ranges` table is implemented as per-day `travel_days`, equivalent for the API and simpler to query.
- Known deferral agreed in planning: court-exercise rep progression prompts (gym-only prompts; court rotates per block).
- Types are consistent: `Check(state, value_num, value_text)` is shared by `scoring`, `db` and the API payload; `DayPlan` field names emitted by `deps.plan_dict` match what the views read.
