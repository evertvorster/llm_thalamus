"""Tests for src/controller/peak_pricing.py — pure, no Qt needed."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from controller.peak_pricing import (
    DEFAULT_PEAK_WINDOWS,
    PricingSchedule,
    PricingSlot,
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


def utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 15, hour, minute, tzinfo=UTC)


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
    def test_returns_one_string_per_slot(self):
        out = local_equivalents([PricingSlot(1, 4), PricingSlot(6, 10)])
        assert len(out) == 2
        for s in out:
            assert s.count(":00") == 2
            assert "\u2013" in s


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
        assert loaded[1].models == ["test-model"]
        assert loaded[1].windows == []

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
