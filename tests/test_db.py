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
