"""Tests for src/controller/peak_pricing.py — pure, no Qt needed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from controller.peak_pricing import (
    ALL_DAYS,
    DEFAULT_PEAK_WINDOWS,
    PricingSchedule,
    PricingSlot,
    format_days,
    format_windows,
    is_peak,
    load_schedules,
    local_equivalents,
    parse_windows,
    save_schedules,
    schedule_for,
    slot_active,
    status_for,
)

UTC = timezone.utc


def utc(hour: int, minute: int = 0, weekday: int = 0) -> datetime:
    """A UTC instant in the week of Monday 2026-01-05 (weekday: 0=Mon)."""
    return datetime(2026, 1, 5 + weekday, hour, minute, tzinfo=UTC)


def tz(hours: float):
    """A fixed-offset timezone, for deterministic local-time tests."""
    return timezone(timedelta(hours=hours))


def ds_schedule(*models: str) -> PricingSchedule:
    return PricingSchedule(
        list(models), [PricingSlot(1, 4), PricingSlot(6, 10)]
    )


# ── PricingSlot ───────────────────────────────────────────────────


class TestPricingSlotValidation:
    def test_valid(self):
        assert (PricingSlot(1, 4).start, PricingSlot(1, 4).end) == (1, 4)

    @pytest.mark.parametrize("start,end", [
        (4, 1), (0, 0), (24, 25), (-1, 5), (0, 25), (12, 12),
    ])
    def test_invalid(self, start, end):
        with pytest.raises(ValueError):
            PricingSlot(start, end)


# ── slot_active / is_peak ─────────────────────────────────────────


class TestSlotActive:
    def test_inside(self):
        assert slot_active(PricingSlot(1, 4), utc(2)) is True

    def test_inclusive_start(self):
        assert slot_active(PricingSlot(1, 4), utc(1)) is True

    def test_exclusive_end(self):
        assert slot_active(PricingSlot(1, 4), utc(4)) is False

    def test_outside(self):
        assert slot_active(PricingSlot(1, 4), utc(6)) is False


class TestIsPeak:
    def test_peak(self):
        s = ds_schedule()
        assert is_peak(s, utc(2)) is True
        assert is_peak(s, utc(7)) is True

    def test_off_peak(self):
        s = ds_schedule()
        assert is_peak(s, utc(5)) is False   # between windows
        assert is_peak(s, utc(22)) is False  # after windows

    def test_no_windows(self):
        assert is_peak(PricingSchedule(), utc(2)) is False


# ── weekdays ──────────────────────────────────────────────────────


class TestWeekdays:
    def test_default_is_every_day(self):
        assert PricingSchedule().days == list(ALL_DAYS)

    def test_all_days_peaks_all_week(self):
        """The default reproduces the pre-weekday behaviour."""
        s = ds_schedule("m")
        assert all(is_peak(s, utc(2, weekday=d)) for d in ALL_DAYS)

    def test_peak_only_inside_listed_days(self):
        s = PricingSchedule(
            ["m"], [PricingSlot(1, 4)], days=[0, 1, 2, 3, 4]
        )
        assert is_peak(s, utc(2, weekday=0)) is True    # Monday
        assert is_peak(s, utc(2, weekday=4)) is True    # Friday
        assert is_peak(s, utc(2, weekday=5)) is False   # Saturday
        assert is_peak(s, utc(2, weekday=6)) is False   # Sunday

    def test_deepseek_weekend_is_off_peak(self):
        """The case this feature exists for: peak hours on a weekend day."""
        s = PricingSchedule(
            ["deepseek"], [PricingSlot(1, 4), PricingSlot(6, 10)],
            days=[0, 1, 2, 3, 4],
        )
        assert status_for([s], "deepseek", utc(2, weekday=0)) == "peak"
        assert status_for([s], "deepseek", utc(2, weekday=5)) == "off-peak"
        assert status_for([s], "deepseek", utc(7, weekday=6)) == "off-peak"

    def test_no_days_never_peaks(self):
        s = PricingSchedule(
            ["m"], [PricingSlot(1, 4)], days=[]
        )
        assert status_for([s], "m", utc(2)) == "off-peak"


class TestFormatDays:
    def test_every_day(self):
        assert format_days(ALL_DAYS) == "every day"

    def test_weekdays(self):
        assert format_days([0, 1, 2, 3, 4]) == "Mon–Fri"

    def test_weekend(self):
        assert format_days([5, 6]) == "Sat–Sun"

    def test_single_day(self):
        assert format_days([3]) == "Thu"

    def test_disjoint_runs(self):
        assert format_days([0, 2, 4, 5, 6]) == "Mon, Wed, Fri–Sun"

    def test_unsorted_and_duplicated(self):
        assert format_days([4, 0, 1, 4]) == "Mon–Tue, Fri"

    def test_empty(self):
        assert format_days([]) == "no days"

    def test_ignores_out_of_range(self):
        assert format_days([-1, 0, 7, 99]) == "Mon"


# ── schedule_for / status_for ─────────────────────────────────────


class TestScheduleFor:
    def test_finds_model(self):
        s1 = ds_schedule("a")
        s2 = ds_schedule("b", "c")
        assert schedule_for([s1, s2], "c") is s2

    def test_not_found(self):
        assert schedule_for([ds_schedule("a")], "x") is None

    def test_first_match_wins(self):
        s1 = ds_schedule("a")
        s2 = ds_schedule("a")
        assert schedule_for([s1, s2], "a") is s1


class TestStatusFor:
    def test_peak(self):
        s = ds_schedule("deepseek-pro", "deepseek-flash")
        assert status_for([s], "deepseek-pro", utc(2)) == "peak"

    def test_off_peak(self):
        assert status_for([ds_schedule("m")], "m", utc(12)) == "off-peak"

    def test_unconfigured(self):
        assert status_for([ds_schedule("m")], "other", utc(2)) is None


# ── parse / format ────────────────────────────────────────────────


class TestParseFormatWindows:
    def test_parse(self):
        slots = parse_windows("01-04, 06-10")
        assert [(s.start, s.end) for s in slots] == [(1, 4), (6, 10)]

    def test_parse_spaces(self):
        assert [(s.start, s.end) for s in parse_windows("1-4 ,6-10")] == [(1, 4), (6, 10)]

    @pytest.mark.parametrize("bad", ["", "01", "01-", "-04", "x-y", "5-2", "ab-cd"])
    def test_parse_invalid(self, bad):
        with pytest.raises(ValueError):
            parse_windows(bad)

    def test_format(self):
        assert format_windows([PricingSlot(1, 4), PricingSlot(6, 10)]) == "01-04, 06-10"

    def test_defaults_match_deepseek(self):
        assert DEFAULT_PEAK_WINDOWS == ((1, 4), (6, 10))


# ── local_equivalents ─────────────────────────────────────────────


class TestLocalEquivalents:
    def _schedule(self, days, windows=((1, 4), (6, 10))):
        return PricingSchedule(
            [], [PricingSlot(*w) for w in windows], list(days)
        )

    def test_utc_unchanged(self):
        s = self._schedule(range(5))
        assert local_equivalents(s, tz(0)) == [
            "Mon–Fri 01:00–04:00, 06:00–10:00"
        ]

    def test_hours_shift_days_preserved(self):
        s = self._schedule(range(5))
        assert local_equivalents(s, tz(2)) == [
            "Mon–Fri 03:00–06:00, 08:00–12:00"
        ]

    def test_half_hour_offset(self):
        s = self._schedule([0], [(1, 4)])
        assert local_equivalents(s, tz(5.5)) == ["Mon 06:30–09:30"]

    def test_negative_offset_moves_the_day_back(self):
        # Mon 01:00–04:00 UTC is Sunday evening at UTC-5.
        s = self._schedule([0], [(1, 4)])
        assert local_equivalents(s, tz(-5)) == ["Sun 20:00–23:00"]

    def test_positive_offset_moves_the_day_forward(self):
        # Mon 20:00–24:00 UTC is Tuesday morning at UTC+4.
        s = self._schedule([0], [(20, 24)])
        assert local_equivalents(s, tz(4)) == ["Tue 00:00–04:00"]

    def test_whole_week_shifts_together(self):
        s = self._schedule(range(5), [(20, 24)])
        assert local_equivalents(s, tz(4)) == ["Tue–Sat 00:00–04:00"]

    def test_exclusive_end_at_local_midnight_reads_2400(self):
        s = self._schedule([0], [(20, 24)])
        assert local_equivalents(s, tz(0)) == ["Mon 20:00–24:00"]

    def test_one_utc_day_splitting_two_local_days(self):
        s = self._schedule([0], [(1, 4), (23, 24)])
        assert local_equivalents(s, tz(2)) == [
            "Mon 03:00–06:00", "Tue 01:00–02:00"
        ]

    def test_no_days_gives_nothing(self):
        assert local_equivalents(self._schedule([]), tz(0)) == []

    def test_no_windows_gives_nothing(self):
        s = PricingSchedule([], [], list(ALL_DAYS))
        assert local_equivalents(s, tz(0)) == []

    def test_defaults_to_machine_timezone(self):
        s = self._schedule(range(5))
        out = local_equivalents(s)
        assert len(out) == 1
        assert out[0].startswith("Mon–Fri ")
        assert out[0].count(":00") == 4


# ── QSettings persistence ─────────────────────────────────────────


class _FakeSettings:
    def __init__(self):
        self.store = {}

    def value(self, key, default=None):
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value


class TestPersistence:
    def test_round_trip(self):
        s = _FakeSettings()
        schedules = [
            PricingSchedule(
                ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"],
                [PricingSlot(1, 4), PricingSlot(6, 10)],
                [0, 1, 2, 3, 4],
            ),
            PricingSchedule(["test-model"]),
        ]
        save_schedules(s, schedules)
        loaded = load_schedules(s)
        assert len(loaded) == 2
        assert loaded[0].models == [
            "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash",
        ]
        assert [(x.start, x.end) for x in loaded[0].windows] == [(1, 4), (6, 10)]
        assert loaded[0].days == [0, 1, 2, 3, 4]
        assert loaded[1].models == ["test-model"]
        assert loaded[1].windows == []
        assert loaded[1].days == list(ALL_DAYS)

    def test_missing_days_means_every_day(self):
        """A schedule stored before weekday support keeps its behaviour."""
        s = _FakeSettings()
        s.store["pricing/schedules"] = [
            {"models": ["a"], "windows": [{"start": 1, "end": 4}]},
        ]
        assert load_schedules(s)[0].days == list(ALL_DAYS)

    def test_explicitly_empty_days_stays_empty(self):
        s = _FakeSettings()
        s.store["pricing/schedules"] = [
            {"models": ["a"], "windows": [], "days": []},
        ]
        assert load_schedules(s)[0].days == []

    def test_invalid_days_dropped(self):
        s = _FakeSettings()
        s.store["pricing/schedules"] = [
            {"models": ["a"], "windows": [], "days": [6, 9, "x", 0, 6]},
        ]
        assert load_schedules(s)[0].days == [0, 6]

    def test_empty(self):
        s = _FakeSettings()
        assert load_schedules(s) == []

    def test_ignores_malformed(self):
        s = _FakeSettings()
        s.store["pricing/schedules"] = [
            {"models": ["a"], "windows": [{"start": 1, "end": 4}]},
            {"windows": [{"start": 1, "end": 4}]},        # no models → still kept
            "garbage",                                     # dropped
            {"models": ["bad"], "windows": [{"start": 9, "end": 2}]},  # bad slot dropped
        ]
        loaded = load_schedules(s)
        assert len(loaded) == 3
        assert loaded[2].models == ["bad"]
        assert loaded[2].windows == []
