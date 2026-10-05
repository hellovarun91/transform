from __future__ import annotations


def rescore(store, plan, d):
    from .api.deps import resolve_day
    from .scoring import score_day
    dp = resolve_day(store, plan, d)
    r = score_day(dp, store.get_checks(d), store.get_rule_breaks(d))
    store.upsert_day(d, mode=dp.mode, score=r.total, grade=r.grade)
    return r


def progression_prompts(store, dp):
    return []
