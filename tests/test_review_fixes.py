"""Tests pinned to the final-review findings (Important 1, 4, 5, 6)."""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from transform.api import deps
from transform.auth import mint_token, verify_token
from transform.config import load_settings
from transform.reports import block_review


def test_token_depends_on_pin_so_pin_change_revokes():
    assert mint_token("s", "1111") != mint_token("s", "2222")
    assert verify_token("s", "1111", mint_token("s", "1111"))
    assert not verify_token("s", "2222", mint_token("s", "1111"))


def test_load_settings_refuses_default_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSFORM_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TRANSFORM_PIN", raising=False)
    monkeypatch.delenv("TRANSFORM_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        load_settings()
    monkeypatch.setenv("TRANSFORM_PIN", "1234")
    monkeypatch.setenv("TRANSFORM_SECRET", "change-me")
    with pytest.raises(RuntimeError):
        load_settings()
    monkeypatch.setenv("TRANSFORM_SECRET", "x" * 32)
    assert load_settings().pin == "1234"


def test_past_sleep_write_runs_sleep_guardrail(client, auth, store):
    today = deps.today_ist(client.app.state.settings)
    for i in (3, 2):
        store.upsert_check(today - timedelta(days=i), "sleep", "done", value_text="00:50")
    d1 = (today - timedelta(days=1)).isoformat()
    r = client.put("/api/check", headers=auth, json={"date": d1, "item_key": "sleep", "state": "done", "value_text": "00:40"})
    assert r.status_code == 200
    assert store.get_calorie_level(today) == 1
    assert store.get_calorie_level(today + timedelta(days=6)) == 1


def test_travel_toggle_rescores_past_days(client, auth, store):
    today = deps.today_ist(client.app.state.settings)
    y = today - timedelta(days=1)
    store.upsert_check(y, "badminton", "done")
    store.upsert_day(y, mode="normal", score=23, grade="red")
    r = client.put("/api/travel", headers=auth, json={"start": y.isoformat(), "end": y.isoformat(), "on": True})
    assert r.status_code == 200
    row = store.get_day(y)
    assert row.mode == "travel" and row.score == 30  # travel: rules default-kept 30, badminton not scored


def test_weight_checkpoint_flag(client, auth, store, plan):
    today = deps.today_ist(client.app.state.settings)
    # 7 heavy weigh-ins ending today → MA7 far above every corridor
    for i in range(7):
        store.set_weight(today - timedelta(days=i), 99.0)
    body = client.get("/api/weight", headers=auth).json()
    flag = body["checkpoint_flag"]
    if any(d <= today for d, _ in plan.checkpoints):
        assert flag is not None and flag["ma7"] == 99.0 and flag["over_by"] > 1.0
    else:
        assert flag is None


def test_block_review_aggregates_four_weeks(store, plan):
    start = plan.start_date
    for i in range(28):
        d = start + timedelta(days=i)
        store.upsert_day(d, score=90, grade="green", mode="normal", locked_at=datetime.now(timezone.utc))
        store.set_weight(d, 92 - 0.1 * i)
    br = block_review(store, plan, 0, today=start + timedelta(days=28))
    assert br["block"] == 0 and br["start"] == start.isoformat() and br["end"] == (start + timedelta(days=27)).isoformat()
    assert br["avg_score"] == 90.0 and br["green_days"] == 28 and br["complete"] is True
    assert br["weight_change"] is not None and br["weight_change"] < 0


def test_blocks_route_lists_completed_blocks(client, auth):
    r = client.get("/api/blocks", headers=auth)
    assert r.status_code == 200 and isinstance(r.json()["blocks"], list)


def test_tzdata_pinned_in_requirements():
    req = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "requirements.txt")).read()
    assert "tzdata" in req


def test_today_flags_missing_yesterday_sleep(client, auth, store, plan):
    today = deps.today_ist(client.app.state.settings)
    body = client.get("/api/today", headers=auth).json()
    assert body["yesterday_sleep_missing"] is (today > plan.start_date)
    store.upsert_check(today - timedelta(days=1), "sleep", "done", value_text="22:00")
    assert client.get("/api/today", headers=auth).json()["yesterday_sleep_missing"] is False
