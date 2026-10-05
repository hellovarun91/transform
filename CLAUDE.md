# Transform — Varun's training, meal and routine tracker

Single-user PWA that prescribes each day's training and meals, scores the day 0–100 against the plan,
tracks weight against a timeline corridor, nudges via web push, and stores everything in SQLite on a
Railway volume. Design: `docs/superpowers/specs/2026-10-05-transform-tracker-design.md`.
Implementation plan: `docs/superpowers/plans/2026-10-05-transform-tracker.md`.

## Run locally

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then export the vars, or prefix the command
TRANSFORM_PIN=1234 TRANSFORM_SECRET=dev TRANSFORM_DATA_DIR=./data python -m transform
# open http://localhost:8000/#today
```

## Test

```bash
pytest tests/ -v
```

## Deploy

Railway, Dockerfile build, start `python -m transform`, health `/health`, volume at `/data`.

```bash
railway up --detach
railway logs --lines 50
```

## Environment variables

| Variable | Purpose |
|---|---|
| `TRANSFORM_PIN` | Login PIN (single user) |
| `TRANSFORM_SECRET` | HMAC secret for the bearer token issued after PIN login |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` | Web push keys (base64url). Generate once, never commit |
| `VAPID_CLAIMS_EMAIL` | `mailto:` contact for push services |
| `TRANSFORM_DATA_DIR` | SQLite directory, default `/data` on Railway, `./data` locally |
| `TZ` | `Asia/Kolkata`; all schedule logic is IST |
| `PORT` | Default 8000 |

Generate VAPID keys:

```bash
python -c "from py_vapid import Vapid,b64urlencode;from cryptography.hazmat.primitives import serialization as s;v=Vapid();v.generate_keys();print('VAPID_PRIVATE_KEY='+b64urlencode(v.private_key.private_numbers().private_value.to_bytes(32,'big')));print('VAPID_PUBLIC_KEY='+b64urlencode(v.public_key.public_bytes(s.Encoding.X962,s.PublicFormat.UncompressedPoint)))"
```

## Layout

```
transform/
  __main__.py   entry: python -m transform → uvicorn
  app.py        FastAPI factory, static mount, scheduler start
  config.py     Settings from env
  plan.py       plan.yaml → DayPlan for a date (mode, grains by calorie level, block variants)
  scoring.py    pure daily score (meals 40, protein 15, rules 15, training 20, sleep 5, supplements 5; travel remap)
  timeline.py   corridor between checkpoints, MA7, goal projection
  db.py         SQLAlchemy models + Store
  auth.py       PIN → HMAC token, rate limiter
  guardrails.py midnight close, textless-swap revert, strength/sleep calorie bumps, catch-up, progression prompts
  reports.py    weekly scorecard, history
  push.py       pywebpush send, dead-subscription cleanup
  scheduler.py  APScheduler jobs in IST
  api/          routes: auth, today/day/check/lift/rule/weight, plan/history/week/settings/travel/export/push
static/         PWA (no build step): index.html, app.js (router, API client, offline queue), views/*.js, sw.js
plan/plan.yaml  ALL programme and meal content, checkpoints, notification times
tests/          pytest, in-memory SQLite
```

## Scoring (spec §6)

| Category | Points | Rule |
|---|---|---|
| Meals | 40 | 6 slots; ate = full, swapped with text = half, skipped/untouched = 0 |
| Protein | 15 | 15 at ≥185 g, linear to 0 at 130 g |
| Rules | 15 | 5 × 3, default kept; tap to confess a break |
| Training | 20 | badminton 8 + court block 12 (M/W/F) or court block 6 + gym 6 (T/T/S); Sunday rest logged = 20 |
| Sleep + supplements | 10 | in bed by 22:30 = 5; all four supplements = 5 |

Travel day: protein 30 (150 g target), rules 30, hotel circuit 25, sleep 8, supplements 7.
Grades: ≥90 green, 75–89 amber, <75 red. No checks at all = 0. Days lock for scoring at midnight
IST, stay editable 48 h, then freeze (writes return 409).

## Schedule (IST)

5:45 wake · 8:15 shake · 9:00 / 13:00 / 16:30 / 20:15 meals · 18:45 gym (Tue/Thu/Sat) · 22:00 magnesium ·
22:15 log-your-day · 00:05 midnight close + guardrails · Sunday 21:00 weekly scorecard. Each nudge fires
only if its item is still unticked. Boot runs a catch-up close for any unscored past days.

## Changing the plan

Edit `plan/plan.yaml` (exercises, variants per block, meals, grains, checkpoints, notification times),
run `pytest`, commit, `railway up --detach`. The DB stores only item keys, never plan text.
