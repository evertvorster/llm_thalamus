"""Peak/off-peak pricing schedules — timezone-aware peak-window tracking.

Peak windows are defined in UTC (matching DeepSeek's published schedule),
on a chosen set of weekdays.  Both hours and days are UTC: pairing local
days with UTC hours would make "Saturday 01:00" meaningless.  The "now"
check is timezone-aware — the current instant is converted to UTC for
membership testing, so a non-UTC machine is handled correctly.

A *schedule* groups several affected models under one set of peak days and
windows.  Anything outside a peak window, or on a day not listed, is
off-peak.  A model may belong to at most one schedule (first match wins if
misconfigured).

Days are per schedule, not per window: all of a schedule's days share one
set of hours.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# DeepSeek's published peak windows, in UTC hours (half-open ranges).
DEFAULT_PEAK_WINDOWS: tuple[tuple[int, int], ...] = ((1, 4), (6, 10))

# ISO weekdays, Monday = 0.
ALL_DAYS: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
_DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# A Monday, used as the anchor for weekday arithmetic in local_equivalents.
_REF_MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


@dataclass
class PricingSlot:
    """A single peak window ``[start, end)`` in UTC hours (half-open)."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if not (0 <= self.start < self.end <= 24):
            raise ValueError(f"invalid peak window {self.start}-{self.end}")


@dataclass
class PricingSchedule:
    """Affected model ids sharing one set of peak days and windows."""

    models: list[str] = field(default_factory=list)
    windows: list[PricingSlot] = field(default_factory=list)
    days: list[int] = field(default_factory=lambda: list(ALL_DAYS))


def now_utc() -> datetime:
    """Return the current instant as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def slot_active(slot: PricingSlot, dt_utc: datetime) -> bool:
    """Whether the UTC hour-of-day of *dt_utc* is inside *slot*."""
    hour = dt_utc.astimezone(timezone.utc).hour
    return slot.start <= hour < slot.end


def is_peak(schedule: PricingSchedule, dt_utc: datetime) -> bool:
    """True when *dt_utc* falls on a peak day inside a peak window."""
    utc = dt_utc.astimezone(timezone.utc)
    if utc.weekday() not in schedule.days:
        return False
    return any(slot_active(w, utc) for w in schedule.windows)


def schedule_for(schedules: list[PricingSchedule], model_id: str):
    """Return the first schedule that affects *model_id*, else None."""
    return next((s for s in schedules if model_id in s.models), None)


def status_for(
    schedules: list[PricingSchedule], model_id: str, dt_utc: datetime
) -> str | None:
    """Peak status for *model_id* at *dt_utc*.

    "peak"    → in a peak window.
    "off-peak"→ configured (in a schedule) but currently off-peak.
    None      → model is in no schedule (caller hides the indicator).
    """
    schedule = schedule_for(schedules, model_id)
    if schedule is None:
        return None
    return "peak" if is_peak(schedule, dt_utc) else "off-peak"


# ── window text helpers ──────────────────────────────────────────


def parse_windows(text: str) -> list[PricingSlot]:
    """Parse ``"01-04, 06-10"`` into slots.  Raises ValueError on bad input."""
    slots: list[PricingSlot] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" not in part:
            raise ValueError(f"expected HH-HH, got {part!r}")
        a, b = part.split("-", 1)
        try:
            start, end = int(a), int(b)
        except ValueError:
            raise ValueError(f"invalid hours in {part!r}") from None
        slots.append(PricingSlot(start, end))
    if not slots:
        raise ValueError("no peak windows given")
    return slots


def format_windows(slots: list[PricingSlot]) -> str:
    """Render slots as ``"01-04, 06-10"``."""
    return ", ".join(f"{s.start:02d}-{s.end:02d}" for s in slots)


def format_days(days) -> str:
    """Render weekday ints run-compressed: ``"Mon–Fri"``, ``"every day"``."""
    uniq = sorted({d for d in days if d in ALL_DAYS})
    if not uniq:
        return "no days"
    if len(uniq) == len(ALL_DAYS):
        return "every day"
    runs: list[tuple[int, int]] = []
    start = prev = uniq[0]
    for day in uniq[1:]:
        if day == prev + 1:
            prev = day
        else:
            runs.append((start, prev))
            start = prev = day
    runs.append((start, prev))
    return ", ".join(
        _DAY_NAMES[a] if a == b else f"{_DAY_NAMES[a]}–{_DAY_NAMES[b]}"
        for a, b in runs
    )


def _local_window(
    utc_day: int, window: PricingSlot, tz
) -> tuple[int, tuple[str, str]]:
    """Map a UTC weekday + window to a local weekday and a (start, end) label."""
    base = _REF_MONDAY + timedelta(days=utc_day)
    start = (base + timedelta(hours=window.start)).astimezone(tz)
    end = (base + timedelta(hours=window.end)).astimezone(tz)
    # An exclusive end at local midnight is a boundary, not a wrap.
    end_label = (
        "24:00"
        if end.date() > start.date() and (end.hour, end.minute) == (0, 0)
        else f"{end:%H:%M}"
    )
    return start.weekday(), (f"{start:%H:%M}", end_label)


def local_equivalents(schedule: PricingSchedule, local_tz=None) -> list[str]:
    """Render the schedule's peak days and windows in the machine's timezone.

    Days are UTC, so a window can land on a different local day.  Local days
    sharing the same windows are grouped and run-compressed, e.g.
    ``"Mon–Fri 03:00–06:00, 08:00–12:00"``.

    Uses the current UTC offset so DST is respected for display.
    """
    days = [d for d in schedule.days if d in ALL_DAYS]
    if not schedule.windows or not days:
        return []
    local_tz = local_tz or datetime.now().astimezone().tzinfo

    labels_by_local_day: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for utc_day in sorted(set(days)):
        for window in schedule.windows:
            local_day, label = _local_window(utc_day, window, local_tz)
            labels_by_local_day[local_day].add(label)

    days_by_labels: dict[tuple, list[int]] = defaultdict(list)
    for local_day, labels in labels_by_local_day.items():
        days_by_labels[tuple(sorted(labels))].append(local_day)

    return [
        f"{format_days(days)} " + ", ".join(f"{a}–{b}" for a, b in labels)
        for labels, days in days_by_labels.items()
    ]


# ── QSettings persistence ────────────────────────────────────────

_KEY = "pricing/schedules"


def _clean_days(raw) -> list[int]:
    """Weekday ints from stored data; a missing field means every day.

    An explicit empty list is kept — the UI can produce it deliberately, and
    it means "never peak".
    """
    if raw is None:
        return list(ALL_DAYS)
    days: list[int] = []
    for value in raw if isinstance(raw, (list, tuple)) else []:
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if day in ALL_DAYS and day not in days:
            days.append(day)
    return sorted(days)


def load_schedules(settings) -> list[PricingSchedule]:
    """Read the ``pricing/schedules`` list from *settings* (QSettings-like)."""
    schedules: list[PricingSchedule] = []
    raw = settings.value(_KEY, [])
    if not isinstance(raw, list):
        return schedules
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        models = [str(m) for m in entry.get("models") or [] if m]
        windows: list[PricingSlot] = []
        for s in entry.get("windows") or []:
            try:
                windows.append(PricingSlot(int(s["start"]), int(s["end"])))
            except (TypeError, ValueError, KeyError):
                continue
        schedules.append(
            PricingSchedule(models, windows, _clean_days(entry.get("days")))
        )
    return schedules


def save_schedules(settings, schedules: list[PricingSchedule]) -> None:
    """Write *schedules* back to the ``pricing/schedules`` key."""
    data = [
        {
            "models": s.models,
            "days": list(s.days),
            "windows": [{"start": w.start, "end": w.end} for w in s.windows],
        }
        for s in schedules
    ]
    settings.setValue(_KEY, data)
