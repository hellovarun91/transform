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
    assert sum(m.protein for m in dp.meals if not m.optional) == 185
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
    assert plan.resolve(date(2026, 10, 6)).adaptation is True
    assert plan.resolve(date(2026, 10, 19)).adaptation is True
    assert plan.resolve(date(2026, 10, 20)).adaptation is False
    assert plan.resolve(date(2026, 10, 20)).block_index == 0
    assert plan.resolve(date(2026, 11, 3)).block_index == 1


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
    assert plan.checkpoints[0] == (date(2026, 10, 6), 92.0)
    assert plan.checkpoints[-1] == (date(2027, 1, 16), 81.5)


def test_weekday_plan_helper(plan):
    assert plan.weekday_plan(3).gym_title == "Lower"
