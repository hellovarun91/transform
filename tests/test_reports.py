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
        store.upsert_day(d, score=100 if i < 6 else 60, grade="green" if i < 6 else "red", locked_at=__import__("datetime").datetime(2026, 10, 19))
        store.set_weight(d, 91.0 - 0.1 * i)
    for i in range(7):
        store.set_weight(monday - timedelta(days=7) + timedelta(days=i), 92.0)
    store.upsert_lift(date(2026, 10, 6), "bench_press", 1, 8, 60)
    store.upsert_lift(date(2026, 10, 13), "bench_press", 1, 8, 62.5)
    sc = week_scorecard(store, plan, 2026, 42, today=date(2026, 10, 19))
    assert sc["start"] == "2026-10-12" and sc["end"] == "2026-10-18"
    assert sc["avg_score"] == round((600 + 60) / 7, 1)
    assert sc["green_days"] == 6
    assert sc["sessions_done"] == 6 and sc["sessions_target"] == 6
    assert sc["lifts_progressed"] == 1
    assert sc["protein_avg"] == 192.0
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
    assert rows[1]["score"] == 8 + 15  # live score: badminton + rules default-kept


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


def test_history_before_start_date_is_unscored(store, plan):
    rows = history(store, plan, date(2026, 10, 4), date(2026, 10, 6), today=date(2026, 10, 6))
    assert rows[0]["score"] is None and rows[0]["grade"] is None and rows[1]["score"] is None
    assert rows[2]["score"] == 0  # start date itself is scored
