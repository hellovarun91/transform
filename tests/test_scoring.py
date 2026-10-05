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
    assert r.protein == 185


def test_protein_needs_override_to_hit_target(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["meal:bedtime"] = Check("done")  # +7 → 192
    assert score_day(dp, c, set()).protein == 192


def test_protein_linear_between_130_and_target(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["meal:dinner"] = Check("skipped")  # 185-48 = 137 → (137-130)/(185-130)*15 = 1.9 → 2
    r = score_day(dp, c, set())
    assert r.breakdown["protein"] == 2
    assert r.breakdown["meals"] == 33  # 5/6 of 40 = 33.3 → 33


def test_swapped_with_text_is_half_and_uses_entered_protein(plan):
    dp = plan.resolve(date(2026, 10, 5))
    c = perfect_checks(dp)
    c["meal:lunch"] = Check("swapped", value_num=30, value_text="dal rice at airport")
    r = score_day(dp, c, set())
    assert r.breakdown["meals"] == 37  # 5 full + 1 half = 5.5/6*40 = 36.67 → 37
    assert r.protein == 185 - 45 + 30


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
