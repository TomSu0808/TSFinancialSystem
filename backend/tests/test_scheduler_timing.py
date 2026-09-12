from datetime import datetime

import scheduler


def test_interval_after_several_missed_slots_does_not_busy_loop(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 12, 19, 0, tzinfo=tz)
    monkeypatch.setattr(scheduler, 'datetime', Clock)
    assert scheduler._seconds_to_next('08:00', 6, 'Asia/Shanghai') == 3600


def test_daily_schedule_runs_tomorrow_after_cutoff(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 12, 8, 0, tzinfo=tz)
    monkeypatch.setattr(scheduler, 'datetime', Clock)
    assert scheduler._seconds_to_next('07:55', 24, 'Asia/Shanghai') == 23 * 3600 + 55 * 60
