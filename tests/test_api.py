from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

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
    client.put("/api/check", headers=auth, json={"date": yesterday.isoformat(), "item_key": "sleep", "state": "done", "value_text": "22:00"})
    assert store.get_day(yesterday).score == 5  # sleep scores 5 on any day type


def test_travel_and_level_applied_in_resolve(client, auth, store, plan):
    today = deps.today_ist(client.app.state.settings)
    store.set_travel(today, today, True)
    assert client.get("/api/today", headers=auth).json()["plan"]["mode"] == "travel"
    store.set_travel(today, today, False)
    store.set_calorie_level(today, 1, "test")
    assert client.get("/api/today", headers=auth).json()["plan"]["calorie_level"] in ("level1", "maintenance")
    store.set_setting("protein_target", "190")
    assert client.get("/api/today", headers=auth).json()["plan"]["protein_target"] == 190
