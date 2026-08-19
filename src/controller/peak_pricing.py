"""Peak/off-peak pricing schedules — timezone-aware peak-window tracking.

Peak windows are defined in UTC (matching DeepSeek's published schedule).
The "now" check is timezone-aware: the current local instant is converted
to UTC for membership testing, so a non-UTC machine is handled correctly.

A *schedule* groups several affected models under one set of peak windows.
Anything outside a peak window is off-peak. A model may belong to at most
one schedule (first match wins if misconfigured).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# DeepSeek's published peak windows, in UTC hours (half-open ranges).
DEFAULT_PEAK_WINDOWS: tuple[tuple[int, int], ...] = ((1, 4), (6, 10))


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
    """A set of affected model ids sharing one list of peak windows."""

    models: list[str] = field(default_factory=list)
    windows: list[PricingSlot] = field(default_factory=list)


def now_utc() -> datetime:
    """Return the current instant as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def slot_active(slot: PricingSlot, dt_utc: datetime) -> bool:
    """Whether the UTC hour-of-day of *dt_utc* is inside *slot*."""
    hour = dt_utc.astimezone(timezone.utc).hour
    return slot.start <= hour < slot.end


def is_peak(schedule: PricingSchedule, dt_utc: datetime) -> bool:
    """True when *dt_utc* falls in any of the schedule's peak windows."""
    return any(slot_active(w, dt_utc) for w in schedule.windows)


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


def local_equivalents(slots: list[PricingSlot]) -> list[str]:
    """Render each UTC peak window in the machine's local timezone.

    Uses the current UTC offset so DST is respected for display.
    """
    local_tz = datetime.now().astimezone().tzinfo
    ref = datetime.now(timezone.utc)
    out: list[str] = []
    for s in slots:
        start_local = ref.replace(
            hour=s.start, minute=0, second=0, microsecond=0
        ).astimezone(local_tz).hour
        end_local = ref.replace(
            hour=s.end, minute=0, second=0, microsecond=0
        ).astimezone(local_tz).hour
        out.append(f"{start_local:02d}:00–{end_local:02d}:00")
    return out


# ── QSettings persistence ────────────────────────────────────────

_KEY = "pricing/schedules"


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
        schedules.append(PricingSchedule(models, windows))
    return schedules


def save_schedules(settings, schedules: list[PricingSchedule]) -> None:
    """Write *schedules* back to the ``pricing/schedules`` key."""
    data = [
        {
            "models": s.models,
            "windows": [{"start": w.start, "end": w.end} for w in s.windows],
        }
        for s in schedules
    ]
    settings.setValue(_KEY, data)
