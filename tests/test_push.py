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
    assert sent and "06 Oct" in sent[-1][0]


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
