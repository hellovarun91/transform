from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (Date, DateTime, Float, Integer, String, Text, UniqueConstraint, create_engine, delete, event,
                        select)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from .scoring import Check


class Base(DeclarativeBase):
    pass


class DayRow(Base):
    __tablename__ = "days"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    mode: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str | None] = mapped_column(String(8))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class CheckRow(Base):
    __tablename__ = "checks"
    __table_args__ = (UniqueConstraint("date", "item_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    item_key: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    value_num: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LiftRow(Base):
    __tablename__ = "lifts"
    __table_args__ = (UniqueConstraint("date", "exercise_key", "set_no"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    exercise_key: Mapped[str] = mapped_column(String(64), index=True)
    set_no: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[float] = mapped_column(Float)


class WeightRow(Base):
    __tablename__ = "weights"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    kg: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RuleBreakRow(Base):
    __tablename__ = "rule_breaks"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    rule_key: Mapped[str] = mapped_column(String(32), primary_key=True)


class SettingRow(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class PushSubRow(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CalorieRow(Base):
    __tablename__ = "calorie_log"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    level: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)


class TravelRow(Base):
    __tablename__ = "travel_days"
    date: Mapped[date] = mapped_column(Date, primary_key=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path: str):
        if path == ":memory:":
            self.engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                                        poolclass=StaticPool)
        else:
            self.engine = create_engine(f"sqlite+pysqlite:///{path}", connect_args={"check_same_thread": False})

            @event.listens_for(self.engine, "connect")
            def _wal(conn, _):
                conn.execute("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    # ---------- days ----------
    def get_day(self, d: date) -> DayRow | None:
        with self.Session() as s:
            return s.get(DayRow, d)

    def upsert_day(self, d: date, *, mode=None, score=None, grade=None, locked_at=None, notes=None) -> DayRow:
        with self.Session() as s:
            row = s.get(DayRow, d) or DayRow(date=d)
            for k, v in (("mode", mode), ("score", score), ("grade", grade), ("locked_at", locked_at), ("notes", notes)):
                if v is not None:
                    setattr(row, k, v)
            s.add(row)
            s.commit()
            return row

    def days_between(self, start: date, end: date) -> list[DayRow]:
        with self.Session() as s:
            return list(s.scalars(select(DayRow).where(DayRow.date >= start, DayRow.date <= end).order_by(DayRow.date)))

    # ---------- checks ----------
    def upsert_check(self, d: date, item_key: str, state: str, value_num=None, value_text=None) -> None:
        with self.Session() as s:
            row = s.scalar(select(CheckRow).where(CheckRow.date == d, CheckRow.item_key == item_key))
            if row is None:
                row = CheckRow(date=d, item_key=item_key)
            row.state, row.value_num, row.value_text, row.ts = state, value_num, value_text, _now()
            s.add(row)
            s.commit()

    def delete_check(self, d: date, item_key: str) -> None:
        with self.Session() as s:
            s.execute(delete(CheckRow).where(CheckRow.date == d, CheckRow.item_key == item_key))
            s.commit()

    def get_checks(self, d: date) -> dict[str, Check]:
        with self.Session() as s:
            rows = s.scalars(select(CheckRow).where(CheckRow.date == d))
            return {r.item_key: Check(r.state, r.value_num, r.value_text) for r in rows}

    # ---------- lifts ----------
    def upsert_lift(self, d: date, exercise_key: str, set_no: int, reps: int, weight_kg: float) -> None:
        with self.Session() as s:
            row = s.scalar(select(LiftRow).where(LiftRow.date == d, LiftRow.exercise_key == exercise_key,
                                                 LiftRow.set_no == set_no))
            if row is None:
                row = LiftRow(date=d, exercise_key=exercise_key, set_no=set_no)
            row.reps, row.weight_kg = int(reps), float(weight_kg)
            s.add(row)
            s.commit()

    def get_lifts(self, d: date) -> list[LiftRow]:
        with self.Session() as s:
            return list(s.scalars(select(LiftRow).where(LiftRow.date == d).order_by(LiftRow.exercise_key, LiftRow.set_no)))

    def lift_sessions(self, exercise_key: str, on_or_before: date, limit: int = 3) -> list[dict]:
        with self.Session() as s:
            rows = list(s.scalars(select(LiftRow).where(LiftRow.exercise_key == exercise_key, LiftRow.date <= on_or_before)
                                  .order_by(LiftRow.date.desc(), LiftRow.set_no)))
        out: list[dict] = []
        for r in rows:
            if not out or out[-1]["date"] != r.date:
                if len(out) == limit:
                    break
                out.append({"date": r.date, "top_weight": 0.0, "sets": []})
            out[-1]["sets"].append((r.set_no, r.reps, r.weight_kg))
            out[-1]["top_weight"] = max(out[-1]["top_weight"], r.weight_kg)
        return out

    # ---------- weights ----------
    def set_weight(self, d: date, kg: float) -> None:
        with self.Session() as s:
            row = s.get(WeightRow, d) or WeightRow(date=d)
            row.kg, row.ts = float(kg), _now()
            s.add(row)
            s.commit()

    def get_weights(self, start: date, end: date) -> list[tuple[date, float]]:
        with self.Session() as s:
            rows = s.scalars(select(WeightRow).where(WeightRow.date >= start, WeightRow.date <= end).order_by(WeightRow.date))
            return [(r.date, r.kg) for r in rows]

    def all_weights(self) -> list[tuple[date, float]]:
        with self.Session() as s:
            return [(r.date, r.kg) for r in s.scalars(select(WeightRow).order_by(WeightRow.date))]

    # ---------- rules ----------
    def set_rule_break(self, d: date, rule_key: str, broken: bool) -> None:
        with self.Session() as s:
            row = s.get(RuleBreakRow, (d, rule_key))
            if broken and row is None:
                s.add(RuleBreakRow(date=d, rule_key=rule_key))
            elif not broken and row is not None:
                s.delete(row)
            s.commit()

    def get_rule_breaks(self, d: date) -> set[str]:
        with self.Session() as s:
            return {r.rule_key for r in s.scalars(select(RuleBreakRow).where(RuleBreakRow.date == d))}

    # ---------- settings ----------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.Session() as s:
            row = s.get(SettingRow, key)
            return row.value if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.Session() as s:
            row = s.get(SettingRow, key) or SettingRow(key=key)
            row.value = value
            s.add(row)
            s.commit()

    # ---------- push ----------
    def add_subscription(self, endpoint: str, p256dh: str, auth: str) -> None:
        with self.Session() as s:
            row = s.scalar(select(PushSubRow).where(PushSubRow.endpoint == endpoint)) or PushSubRow(endpoint=endpoint, created_at=_now())
            row.p256dh, row.auth = p256dh, auth
            s.add(row)
            s.commit()

    def remove_subscription(self, endpoint: str) -> None:
        with self.Session() as s:
            s.execute(delete(PushSubRow).where(PushSubRow.endpoint == endpoint))
            s.commit()

    def list_subscriptions(self) -> list[dict]:
        with self.Session() as s:
            return [{"endpoint": r.endpoint, "p256dh": r.p256dh, "auth": r.auth}
                    for r in s.scalars(select(PushSubRow).order_by(PushSubRow.id))]

    # ---------- calorie level ----------
    def get_calorie_level(self, d: date) -> int:
        with self.Session() as s:
            row = s.get(CalorieRow, d)
            return int(row.level) if row else 0

    def set_calorie_level(self, d: date, level: int, reason: str) -> None:
        with self.Session() as s:
            row = s.get(CalorieRow, d) or CalorieRow(date=d)
            row.level, row.reason = int(level), reason
            s.add(row)
            s.commit()

    def calorie_entries(self, start: date, end: date) -> list[dict]:
        with self.Session() as s:
            rows = s.scalars(select(CalorieRow).where(CalorieRow.date >= start, CalorieRow.date <= end).order_by(CalorieRow.date))
            return [{"date": r.date, "level": r.level, "reason": r.reason} for r in rows]

    # ---------- travel ----------
    def set_travel(self, start: date, end: date, on: bool) -> None:
        with self.Session() as s:
            d = start
            while d <= end:
                row = s.get(TravelRow, d)
                if on and row is None:
                    s.add(TravelRow(date=d))
                elif not on and row is not None:
                    s.delete(row)
                d += timedelta(days=1)
            s.commit()

    def is_travel(self, d: date) -> bool:
        with self.Session() as s:
            return s.get(TravelRow, d) is not None

    def travel_days(self, start: date, end: date) -> set[date]:
        with self.Session() as s:
            return {r.date for r in s.scalars(select(TravelRow).where(TravelRow.date >= start, TravelRow.date <= end))}

    # ---------- export ----------
    def export_all(self) -> dict:
        def iso(v):
            return v.isoformat() if v is not None else None

        with self.Session() as s:
            return {
                "days": [{"date": iso(r.date), "mode": r.mode, "score": r.score, "grade": r.grade,
                          "locked_at": iso(r.locked_at), "notes": r.notes} for r in s.scalars(select(DayRow).order_by(DayRow.date))],
                "checks": [{"date": iso(r.date), "item_key": r.item_key, "state": r.state, "value_num": r.value_num,
                            "value_text": r.value_text, "ts": iso(r.ts)} for r in s.scalars(select(CheckRow).order_by(CheckRow.date, CheckRow.item_key))],
                "lifts": [{"date": iso(r.date), "exercise_key": r.exercise_key, "set_no": r.set_no, "reps": r.reps,
                           "weight_kg": r.weight_kg} for r in s.scalars(select(LiftRow).order_by(LiftRow.date, LiftRow.exercise_key, LiftRow.set_no))],
                "weights": [{"date": iso(r.date), "kg": r.kg} for r in s.scalars(select(WeightRow).order_by(WeightRow.date))],
                "rule_breaks": [{"date": iso(r.date), "rule_key": r.rule_key} for r in s.scalars(select(RuleBreakRow).order_by(RuleBreakRow.date))],
                "calorie_log": [{"date": iso(r.date), "level": r.level, "reason": r.reason} for r in s.scalars(select(CalorieRow).order_by(CalorieRow.date))],
                "travel_days": [iso(r.date) for r in s.scalars(select(TravelRow).order_by(TravelRow.date))],
                "settings": {r.key: r.value for r in s.scalars(select(SettingRow)) if r.key != "pin_hash"},
            }
