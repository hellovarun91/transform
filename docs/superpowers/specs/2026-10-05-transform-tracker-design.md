# Transform — Fitness, Meal and Routine Tracker: Design Spec

Date: 2026-10-05
Status: approved in brainstorming, pending implementation plan

## 1. Purpose

A single-user, mobile-first PWA that holds Varun to a strict daily training and diet
routine and records every day's compliance. Goal: 92 kg → 81–82 kg lean, while
keeping six badminton mornings a week and gaining strength. Work and travel broke the
previous routine; the app's job is to make every day scored and visible so slipping is
obvious the same day, not a month later.

Replaces the existing static planner in `hellovarun91/transform` (family meal plan,
no logging). This is a fresh build in the same repo; the old files are removed.

### User profile (fixed inputs, editable in Settings)
- Male, 35, 174 cm, 92 kg at start (5 Oct 2026). Athletic, no visible fat, high bone density.
- Badminton Mon–Sat mornings, 3 games treated as cardio.
- Gym Tue / Thu / Sat evenings. Sunday rest.
- Court gear: 5 kg and 10 kg dumbbells, short rod with 35 kg of plates.
- Diet: vegetarian + eggs by default, two optional non-veg dinner swaps. Whey: Rule1 R1.
- Device: iPhone, app installed to home screen.

### Decisions made
- Meal logging is **hybrid**: compliance taps against a prescribed plan, plus free text
  whenever a meal is swapped or skipped.
- Accountability via **PWA web push only** (no Telegram).
- **Travel mode** replaces the plan with a rule set and a hotel circuit; still scored to 100.
- **Aggressive diet**: ~2,050 kcal, 185 g protein, with guardrails (section 4.4).
- Training volume: one strength session per day, six per week. Court weights M/W/F,
  gym T/T/S, core + mobility on gym-day mornings. Running is optional Sunday only.

## 2. Screens

Five screens behind a bottom tab bar, dark theme.

1. **Today** – date, day type badge (Court / Gym / Rest / Travel / Diet break), daily
   score 0–100, protein counter (logged / target). Checklist in time order with
   one-tap items; expandable groups for court weights, gym (with weight-lifted
   fields per set) and each meal (ate / swapped / skipped, text box on swap/skip,
   protein grams shown and auto-summed). Rules row (5 toggles, default kept).
   Supplements group (4 ticks). Sleep: "in bed" time picker. Travel toggle shortcut.
2. **Plan** – weekday selector, read-only. Shows that day's full timeline, exercises
   with sets/reps/load, meals with portions and protein. Sunday prep list.
3. **Weight** – morning weigh-in input, 7-day moving average line, target corridor
   from the timeline (section 5), projected date at current rate, "creatine
   loading" label for the first 14 days.
4. **History** – calendar heatmap by score colour; tap a day to see its log. Weekly
   scorecards list. Block reviews at block boundaries.
5. **Settings** – PIN change, enable push + install hint, notification times,
   travel mode for a date range, protein target, calorie level (auto-managed but
   visible), export JSON.

Past days editable for 48 h after midnight, then frozen.

## 3. Training programme

### 3.1 Daily skeleton (Mon–Sat)

| Time | Item |
|---|---|
| 5:45 | Wake, 500 ml water, black coffee |
| 6:15 | 1 banana |
| 6:30–7:45 | Badminton, 3 games |
| 7:45–8:10 | Court weights (M/W/F) or core + mobility (T/T/S) |
| 8:15 | Whey 1 scoop + creatine 5 g |
| 9:00 | Breakfast + multivitamin |
| 13:00 | Lunch + omega-3 |
| 16:30 | Snack |
| 19:00–20:00 | Gym (Tue/Thu/Sat) |
| 20:15 | Dinner (whey 1 scoop first on gym days) |
| 22:00 | Magnesium glycinate, optional curd/milk |
| 22:30 | Lights out |

Sunday: rest, optional easy 5 km run, flexible lunch, Sunday prep.

### 3.2 Court weights (Mon / Wed / Fri, ~25 min)

| Day | Exercises |
|---|---|
| Mon – Push | Push-ups 3×15-20 · DB shoulder press 10 kg 3×12 · Diamond push-ups 3×12 · Pike push-ups 3×10 · Plank 3×45 s |
| Wed – Pull | Rod bent-over row 35 kg 4×12 · Single-arm DB row 10 kg 3×15 · DB curl 10 kg 3×12 · Rod upright row 3×12 · Side plank 3×30 s each |
| Fri – Legs | Goblet squat 10 kg 3×15 · Bulgarian split squat 3×10/leg · Rod RDL 35 kg 3×12 · Walking lunges 3×12/leg · Glute bridge 3×20 · Calf raises 3×20 |

Tue/Thu/Sat court block (10 min): dead bug 3×10, bird-dog 3×10, hollow hold 3×30 s,
hip-flexor and hamstring stretch 5 min.

### 3.3 Gym (Tue / Thu / Sat evenings, ~60 min)

| Day | Exercises |
|---|---|
| Tue – Upper push | Bench press 4×6-8 · Incline DB press 3×10 · Seated DB shoulder press 3×10 · Cable fly 3×12 · Triceps rope pushdown 3×12 · Face pull 3×15 |
| Thu – Lower | Back squat 4×6-8 · Romanian deadlift 3×8-10 · Leg press 3×12 · Leg curl 3×12 · Hanging leg raise 3×12 · Standing calf raise 3×15 |
| Sat – Upper pull | Pull-ups or lat pulldown 4×8 · Barbell row 4×10 · Chest-supported row 3×12 · Overhead press 3×8 · DB curl 3×12 · Rear-delt fly 3×15 |

### 3.4 Progression
Double progression. When every set of an exercise hits the top of its rep range in two
consecutive sessions, the app prompts +2.5 kg (gym) or +2 reps / harder variation
(court). Progression prompts are off during weeks 1–2 (adaptation). Gym sets record
reps and weight per set.

### 3.5 Block rotation
Plan runs in 4-week blocks. At each block boundary the plan's "variant" index advances
and swaps exercise variants defined in the plan file (e.g. flat bench → incline barbell,
goblet squat → rod front squat, lat pulldown → chin-ups). Meal mains do not rotate.

### 3.6 Travel workout
20-min hotel circuit, 4 rounds: push-ups 15, squats 20, reverse lunges 10/leg, plank
45 s, mountain climbers 30 s. Optional 5 km run.

## 4. Nutrition

### 4.1 Targets (aggressive)
~2,050 kcal · protein 185 g · fat ~60 g · carbs ~150 g. Estimated maintenance ~3,000.
Floor 2,000 kcal.

### 4.2 Daily meals

| Time | Meal | ~kcal / protein |
|---|---|---|
| 6:15 | 1 banana | 105 / 1 g |
| 8:15 | Whey 1 scoop + creatine 5 g | 120 / 25 g |
| 9:00 | 3 whole eggs + 4 whites with veg, 1 multigrain toast, 1 fruit | 430 / 36 g |
| 13:00 | Rotating main + 200 g curd + big salad. Grain: 1 roti or ½ cup rice on court days; 2 roti or 1 cup rice on gym days | 550 / 45 g |
| 16:30 | Whey 1 scoop in water + 1 apple or 30 g roasted chana | 200 / 28 g |
| 20:15 | Rotating dinner main + sabzi + salad, no grain | 450 / 45 g |
| 22:00 | Optional 100 g curd or 200 ml milk (no points) | 80 / 7 g |

Rotating mains:

| Day | Lunch main | Dinner main |
|---|---|---|
| Mon | Palak paneer 150 g | Egg curry, 3 eggs + sabzi |
| Tue | Rajma + rice | Paneer tikka 150 g, air-fried |
| Wed | Soya chunk curry 50 g dry | Tofu stir-fry 200 g (swap: grilled chicken 150 g) |
| Thu | Chana masala | Moong dal chilla ×3 + paneer stuffing |
| Fri | Matar paneer 150 g | Besan-egg omelette 3 eggs + sabzi |
| Sat | Dal tadka 1.5 cups + rice | Paneer bhurji 150 g (swap: fish tikka 150 g) |
| Sun | Flexible meal, one plate, logged | Dal khichdi + curd, 1 cup rice (refeed) |

Sunday is a planned refeed (~2,600 kcal), scored like any day.

### 4.3 Rules (scored daily)
No sugary drinks · no fried food · no sweets outside Sunday lunch · 3 L water · no alcohol.

### 4.4 Guardrails (automatic, midnight job)
- Calorie floor 2,000; the weekly auto-cut rule is disabled at the aggressive level.
- If the logged top weight of the same gym lift drops on two consecutive sessions, or
  logged bed time is later than 00:30 (i.e. sleep < 6 h) three days running, the app
  sets calorie level +1 (adds the dinner roti) for 7 days and notifies with the reason.
- Weeks 9: mandatory diet break at ~2,800 kcal (6–12 Dec 2026). Day mode `diet_break`
  restores grains at all meals; scoring unchanged.
- Calorie level is an integer: 0 = aggressive plan, +1 adds dinner roti, +2 also
  doubles lunch grain, maintenance = diet-break plan. Stored per day in `calorie_log`.

### 4.5 Supplements

| When | Supplement | Suggested brands |
|---|---|---|
| Breakfast | Multivitamin 1 tab | ON Opti-Men · Centrum Men · HK Vitals Men |
| Lunch | Omega-3 1 cap (≥500 mg EPA+DHA) | Wow Omega-3 1300 · HK Vitals Fish Oil high strength · Sports Research Triple Strength |
| 22:00 | Magnesium glycinate 1 tab (200–300 mg elemental) | Carbamide Forte · Himalayan Organics · Wellbeing Nutrition |
| 8:15 shake | Creatine monohydrate 5 g daily (Creapure) | MuscleBlaze Creapure · Nutrabay Pure · Avvatar · ON Micronized |

Not in-app, advisory: blood panel (vit D, B12, lipids, HbA1c, thyroid) in week 1;
vitamin D only under test. Electrolytes on heavy-sweat days optional.

### 4.6 Travel mode nutrition
Rules replace the plan: protein 150 g, eggs at breakfast, Rule1 sachets, dal / paneer /
curd at meals, no fried, no sugar, no buffet seconds, no alcohol, 3 L water. Meal slots
become "protein logged" entries with grams.

## 5. Timeline and corridor

Start 5 Oct 2026, 92 kg. Corridor is a straight line between checkpoints ±1 kg.

| Block | Dates | Target 7-day avg |
|---|---|---|
| Weeks 1–2 | 5–18 Oct | 92 → 89.5 |
| Weeks 3–4 | 19 Oct – 1 Nov | 88 |
| Weeks 5–8 | 2–29 Nov | 84.5 |
| Checkpoint | 5 Dec | 84–85 |
| Diet break | 6–12 Dec | hold |
| Weeks 10–14 | 13 Dec – ~15 Jan 2027 | 81–82 (goal) |

Block reviews on 1 Nov, 29 Nov, 27 Dec. If the 7-day average is > 1 kg above the
corridor at a checkpoint, History and Weight show a red flag; no automatic calorie cut
below the floor.

## 6. Scoring

Daily 0–100, pure function `scoring.score_day(day_plan, checks, lifts, rule_breaks, bed_time)`.

| Category | Pts | Rule |
|---|---|---|
| Meals | 40 | 6 slots (banana, whey, breakfast, lunch, snack, dinner), equal share. done = full, swapped = half (requires text), skipped/untouched = 0 |
| Protein | 15 | 15 at ≥ target; linear to 0 at 130 g (travel: 150 g target, 0 at 100 g) |
| Rules | 15 | 5 × 3; unlogged day loses all |
| Training | 20 | Badminton 8 · post-court block 6 · gym 6 (M/W/F: court weights worth 12). Sunday: 20 for logging rest, 0 if training logged |
| Sleep + supplements | 10 | Bed by 22:30 = 5; all 4 supplement ticks = 5 |

Travel day remap: protein 30, rules 30, hotel circuit 25, sleep + supplements 15.

Grades: ≥90 green, 75–89 amber, <75 red. Streak = consecutive green days. Week on-plan
at average ≥ 85. Day with no checks at all = 0.

Midnight (IST) job: swapped meals without text → skipped; compute and store score;
run guardrails; lock scoring (edits allowed for 48 h, then frozen; a re-edit within
48 h re-scores).

Weekly scorecard (Sunday 21:00 push + History): average score, green days, protein
average, sessions done / 6, lifts progressed, weight change vs last week, verdict
(on pace / behind / ahead vs corridor).

## 7. Architecture

Single Railway service, Python 3.12, FastAPI + uvicorn, SQLite (WAL) via SQLAlchemy on
`/data`. Static PWA served by FastAPI from `static/`. APScheduler in-process.

```
transform/
  __main__.py        # `python -m transform` → uvicorn
  app.py             # FastAPI factory, static mount, scheduler start
  config.py          # env + settings
  db.py              # engine, models, session
  plan.py            # loads plan/plan.yaml, resolves a date → DayPlan (mode, items, meals, variant)
  scoring.py         # pure scoring + grade + streak
  guardrails.py      # strength/sleep checks, calorie level, block boundaries
  timeline.py        # corridor + projection
  api/               # routers: auth, today, day, lifts, weight, history, settings, push, plan, export
  scheduler.py       # jobs: nudges, midnight close, weekly scorecard
  push.py            # pywebpush VAPID send
static/
  index.html, app.js, views/*.js, styles.css, sw.js, manifest.json
plan/plan.yaml       # all programme + meal content, variants per block
tests/
Dockerfile, railway.toml, requirements.txt, pyproject.toml, .github/workflows/ci.yml
```

### 7.1 Data model

- `days(date PK, mode, score, grade, locked_at, notes)`
- `checks(id, date, item_key, state, value_num, value_text, ts)` unique (date, item_key)
- `lifts(id, date, exercise_key, set_no, reps, weight_kg)` unique (date, exercise_key, set_no)
- `weights(date PK, kg, ts)`
- `rule_breaks(date, rule_key)` PK both
- `settings(key PK, value)` — pin_hash, protein_target, notif_times JSON, start_date, start_weight
- `push_subscriptions(id, endpoint UNIQUE, p256dh, auth, created_at)`
- `calorie_log(date PK, level, reason)`
- `travel_ranges(id, start, end)`

Plan content is YAML in the repo (versioned); DB never stores plan text, only
`item_key`s resolved against the plan for the date.

### 7.2 API (all under `/api`, bearer token except `/auth` and `/health`)

- `POST /auth` {pin} → {token}
- `GET /today` → DayPlan + checks + lifts + score + protein + streak
- `GET /day/{date}`, `PUT /check` {date, item_key, state, value_num?, value_text?}
- `PUT /lift` {date, exercise_key, set_no, reps, weight_kg}
- `PUT /weight` {date, kg}; `GET /weight?from&to` → series + MA7 + corridor + projection
- `PUT /rule` {date, rule_key, broken}
- `GET /history?from&to`, `GET /week/{iso_week}` → scorecard
- `GET /plan`, `GET /plan/{weekday}`
- `GET/PUT /settings`, `PUT /travel` {start, end, on}
- `POST /push/subscribe`, `DELETE /push/subscribe`, `GET /push/vapid-public-key`
- `GET /export` → full JSON dump
- `GET /health`

Writes to a frozen day (>48 h after midnight) return 409.

### 7.3 Push schedule (IST)
5:45 wake · 8:15 shake · 9:00 / 13:00 / 16:30 / 20:15 meals · 18:45 gym (T/T/S) ·
22:00 magnesium · 22:15 "log your day" · Sun 21:00 weekly scorecard. A nudge fires only
if its item is still untouched. Midnight job at 00:05 IST.

### 7.4 Auth
Single PIN from `TRANSFORM_PIN` env (hashed at boot into settings). `POST /auth` issues
an HMAC-signed long-lived token stored in localStorage. Rate-limit 5 attempts / 15 min.

### 7.5 Error handling
- Offline: service worker caches the shell; checks queue in IndexedDB and replay on
  reconnect (`PUT /check` is idempotent per (date, item_key)).
- Push send failures with 404/410 delete the subscription.
- Scheduler jobs log and never raise; midnight job is idempotent and catches up on
  any unscored past days at boot.

### 7.6 Testing
- `scoring.py`: every category, travel remap, zero-log day, swapped-without-text.
- `plan.py`: each weekday resolves correct items, variant rotation at block
  boundaries, travel and diet-break modes.
- `guardrails.py`: strength drop, sleep rule, floor, diet-break window.
- `timeline.py`: corridor values at checkpoints, projection.
- API: auth, check/lift/weight round trips, frozen-day 409, export shape.
- Frontend: manual on iPhone; no JS test harness (no build step).

## 8. Deployment

Railway service `transform`, Dockerfile (python:3.12-slim), start `python -m transform`,
health `/health` on 8000, volume at `/data`. Deploy with `railway up --detach`.
Env: `TRANSFORM_PIN`, `TRANSFORM_SECRET` (token HMAC), `VAPID_PRIVATE_KEY`,
`VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_EMAIL`, `TRANSFORM_DATA_DIR` (default `/data`),
`TZ=Asia/Kolkata`. GitHub Actions runs pytest on push.

## 9. Out of scope
Family meals, multi-user, calorie database lookup, Telegram, Apple Health sync,
automatic plan editing in the UI (plan changes are commits).
