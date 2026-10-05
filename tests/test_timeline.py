from datetime import date, timedelta

from transform.timeline import corridor, corridor_band, corridor_status, moving_average, projection

CP = [(date(2026, 10, 5), 92.0), (date(2026, 10, 19), 89.0), (date(2026, 11, 2), 87.0)]


def test_corridor_interpolates_and_bounds():
    assert corridor(CP, date(2026, 10, 5)) == 92.0
    assert corridor(CP, date(2026, 10, 12)) == 90.5
    assert corridor(CP, date(2026, 11, 2)) == 87.0
    assert corridor(CP, date(2026, 10, 4)) is None
    assert corridor(CP, date(2026, 11, 3)) is None
    assert corridor_band(CP, date(2026, 10, 12), 1.0) == (89.5, 91.5)


def test_moving_average_trailing():
    s = [(date(2026, 10, 1) + timedelta(days=i), 90 - i) for i in range(10)]
    ma = moving_average(s, 7)
    assert ma[0] == (date(2026, 10, 1), 90.0)
    assert ma[2][1] == 89.0
    assert round(ma[-1][1], 3) == 84.0  # mean of 87..81


def test_projection_hits_goal_date():
    s = [(date(2026, 10, 1) + timedelta(days=i), 92 - 0.1 * i) for i in range(20)]
    d = projection(s, 90.0)
    assert d is not None
    assert date(2026, 10, 18) <= d <= date(2026, 10, 24)


def test_projection_none_when_flat_or_short():
    flat = [(date(2026, 10, 1) + timedelta(days=i), 90.0) for i in range(20)]
    assert projection(flat, 85.0) is None
    assert projection(flat[:3], 85.0) is None


def test_corridor_status():
    assert corridor_status(90.5, CP, date(2026, 10, 12), 1.0) == "on_pace"
    assert corridor_status(92.0, CP, date(2026, 10, 12), 1.0) == "behind"
    assert corridor_status(89.0, CP, date(2026, 10, 12), 1.0) == "ahead"
    assert corridor_status(89.0, CP, date(2027, 1, 1), 1.0) == "on_pace"  # outside range → neutral
