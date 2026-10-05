from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..guardrails import apply_sleep_guardrail, progression_prompts, rescore
from ..timeline import corridor_band, moving_average, projection
from . import deps

router = APIRouter(dependencies=[Depends(deps.require_auth)])


class CheckIn(BaseModel):
    date: date
    item_key: str
    state: Literal["done", "swapped", "skipped", "untouched"]
    value_num: float | None = Field(default=None, ge=0, le=500)
    value_text: str | None = Field(default=None, max_length=300)


class LiftIn(BaseModel):
    date: date
    exercise_key: str
    set_no: int = Field(ge=1, le=10)
    reps: int = Field(ge=0, le=100)
    weight_kg: float = Field(ge=0, le=500)


class RuleIn(BaseModel):
    date: date
    rule_key: str
    broken: bool


class WeightIn(BaseModel):
    date: date
    kg: float = Field(ge=40, le=200)


def _payload(store, plan, settings, d: date) -> dict:
    dp = deps.resolve_day(store, plan, d)
    return deps.build_day_payload(store, plan, d, settings, progression=progression_prompts(store, dp))


def _after_write(store, plan, settings, d: date) -> dict:
    if d < deps.today_ist(settings):
        rescore(store, plan, d)
    return _payload(store, plan, settings, d)


@router.get("/today")
def today(store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    return _payload(store, plan, settings, deps.today_ist(settings))


@router.get("/day/{d}")
def day(d: str, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    return _payload(store, plan, settings, deps.parse_date(d))


@router.put("/check")
def put_check(body: CheckIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    deps.assert_writable(body.date, settings)
    dp = deps.resolve_day(store, plan, body.date)
    if body.item_key not in deps.valid_item_keys(dp):
        raise HTTPException(400, f"unknown item {body.item_key}")
    if body.state == "untouched":
        store.delete_check(body.date, body.item_key)
    else:
        store.upsert_check(body.date, body.item_key, body.state, body.value_num, body.value_text)
    if body.item_key == "sleep" and body.date < deps.today_ist(settings):
        apply_sleep_guardrail(store, body.date)  # bedtimes are usually logged the next morning, after the close
    return _after_write(store, plan, settings, body.date)


@router.put("/lift")
def put_lift(body: LiftIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    deps.assert_writable(body.date, settings)
    store.upsert_lift(body.date, body.exercise_key, body.set_no, body.reps, body.weight_kg)
    return _after_write(store, plan, settings, body.date)


@router.put("/rule")
def put_rule(body: RuleIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    deps.assert_writable(body.date, settings)
    if body.rule_key not in {r["key"] for r in plan.rules}:
        raise HTTPException(400, "unknown rule")
    store.set_rule_break(body.date, body.rule_key, body.broken)
    return _after_write(store, plan, settings, body.date)


@router.put("/weight")
def put_weight(body: WeightIn, store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    if body.date > deps.today_ist(settings):
        raise HTTPException(400, "cannot log a future day")
    store.set_weight(body.date, body.kg)
    return _payload(store, plan, settings, body.date)


@router.get("/weight")
def get_weight(from_: str | None = Query(default=None, alias="from"), to: str | None = None,
               store=Depends(deps.get_store), plan=Depends(deps.get_plan), settings=Depends(deps.get_settings)):
    today = deps.today_ist(settings)
    start = deps.parse_date(from_) if from_ else plan.start_date
    end = deps.parse_date(to) if to else today
    series = store.get_weights(start, end)
    all_series = store.all_weights()
    ma = moving_average(series, 7)
    corridor = []
    d = start
    while d <= end:
        band = corridor_band(plan.checkpoints, d, plan.band_kg)
        if band:
            corridor.append({"date": d.isoformat(), "lo": band[0], "hi": band[1], "mid": round((band[0] + band[1]) / 2, 3)})
        d += timedelta(days=1)
    proj = projection(all_series, float(plan.meta["goal_weight"]))
    flag = None
    recent = store.get_weights(today - timedelta(days=13), today)
    passed = [(cd, kg) for cd, kg in plan.checkpoints if cd <= today]
    if recent and passed:
        ma7_now = moving_average(recent, 7)[-1][1]
        cp_date, cp_kg = passed[-1]
        over_by = round(ma7_now - (cp_kg + plan.band_kg), 2)
        if over_by > 0:
            flag = {"date": cp_date.isoformat(), "target": cp_kg, "ma7": ma7_now, "over_by": over_by}
    return {
        "checkpoint_flag": flag,
        "series": [{"date": d.isoformat(), "kg": kg} for d, kg in series],
        "ma7": [{"date": d.isoformat(), "kg": kg} for d, kg in ma],
        "corridor": corridor,
        "projection": proj.isoformat() if proj else None,
        "goal": float(plan.meta["goal_weight"]),
        "start_weight": float(plan.meta["start_weight"]),
        "checkpoints": [{"date": d.isoformat(), "kg": kg} for d, kg in plan.checkpoints],
        "creatine_loading_until": (plan.start_date + timedelta(days=14)).isoformat(),
    }
