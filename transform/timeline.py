from __future__ import annotations

from datetime import date, timedelta


def corridor(checkpoints: list[tuple[date, float]], d: date) -> float | None:
    cps = sorted(checkpoints)
    if not cps or d < cps[0][0] or d > cps[-1][0]:
        return None
    for (d0, k0), (d1, k1) in zip(cps, cps[1:]):
        if d0 <= d <= d1:
            span = (d1 - d0).days
            if span == 0:
                return k1
            return round(k0 + (k1 - k0) * (d - d0).days / span, 3)
    return cps[-1][1]


def corridor_band(checkpoints, d: date, band_kg: float) -> tuple[float, float] | None:
    c = corridor(checkpoints, d)
    if c is None:
        return None
    return (round(c - band_kg, 3), round(c + band_kg, 3))


def corridor_status(ma7_kg: float, checkpoints, d: date, band_kg: float) -> str:
    band = corridor_band(checkpoints, d, band_kg)
    if band is None:
        return "on_pace"
    lo, hi = band
    if ma7_kg > hi:
        return "behind"
    if ma7_kg < lo:
        return "ahead"
    return "on_pace"


def moving_average(series: list[tuple[date, float]], n: int = 7) -> list[tuple[date, float]]:
    s = sorted(series)
    out: list[tuple[date, float]] = []
    for i in range(len(s)):
        window = [v for _, v in s[max(0, i - n + 1): i + 1]]
        out.append((s[i][0], round(sum(window) / len(window), 3)))
    return out


def projection(series: list[tuple[date, float]], goal_kg: float, lookback: int = 14) -> date | None:
    ma = moving_average(series, 7)[-lookback:]
    if len(ma) < 5:
        return None
    x0 = ma[0][0]
    xs = [(d - x0).days for d, _ in ma]
    ys = [v for _, v in ma]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if slope >= -1e-6:
        return None
    intercept = my - slope * mx
    days_to_goal = (goal_kg - intercept) / slope
    if days_to_goal < 0:
        return ma[-1][0]
    return x0 + timedelta(days=round(days_to_goal))
