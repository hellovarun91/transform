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
    assert date(2026, 10, 7) in dates and date(2026, 10, 9) in dates and date(2026, 10, 6) in dates
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
