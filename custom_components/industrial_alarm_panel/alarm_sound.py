"""Alarm sound and horn state manager."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from .alarm_models import PRIORITY_PROFILES, AlarmPriority

_LOGGER = logging.getLogger(__name__)

MediaCall = Callable[[str, AlarmPriority], Awaitable[None]]

#: How long ``horn_active`` stays on after a test sound with no real alarm.
TEST_SOUND_SECONDS = 5


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


class AlarmSoundManager:
    """Manage audible alarm state for browser and media-player sound.

    The manager is a pure state machine. Time-based behaviour (timed silence
    expiry, repeat-until-silenced and the end of a test sound) is driven by the
    integration, which schedules a timer at ``next_timer_due()`` and then calls
    ``async_process_timers()``.
    """

    def __init__(
        self,
        *,
        sound_mode: str = "browser_only",
        repeat_interval_seconds: int = 30,
        repeat_until_silenced: bool = True,
        media_players: list[str] | None = None,
        media_call: MediaCall | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.sound_mode = sound_mode
        self.repeat_interval_seconds = repeat_interval_seconds
        self.repeat_until_silenced = repeat_until_silenced
        self.media_players = media_players or []
        self._media_call = media_call
        self._now = now or (lambda: datetime.now(UTC))
        self.active_audible_alarms: dict[str, AlarmPriority] = {}
        self.horn_active = False
        self.silenced = False
        self.silenced_until: datetime | None = None
        self.last_sound_at: datetime | None = None
        self.test_until: datetime | None = None

    @property
    def browser_enabled(self) -> bool:
        """Return whether browser panel sound should be active."""

        return self.sound_mode in {"browser_only", "browser_and_media_player"}

    @property
    def media_player_enabled(self) -> bool:
        """Return whether media player sound should be active."""

        return self.sound_mode in {"media_player_only", "browser_and_media_player"}

    def _horn_should_be_active(self) -> bool:
        return (
            self.sound_mode != "none"
            and not self.silenced
            and bool(self.active_audible_alarms)
        )

    def _refresh_horn(self) -> None:
        self.horn_active = self._horn_should_be_active() or self.test_until is not None

    async def on_alarm_requires_sound(
        self, rule_id: str, priority: AlarmPriority
    ) -> None:
        """Start or re-start sound for a new unacknowledged audible alarm."""

        new_alarm = rule_id not in self.active_audible_alarms
        force_sound = new_alarm and (self.silenced or not self.horn_active)
        self.active_audible_alarms[rule_id] = priority
        if self.sound_mode == "none":
            return
        if new_alarm:
            self.silenced = False
            self.silenced_until = None
        if not self.silenced:
            self.horn_active = True
            if force_sound or self._sound_cooldown_elapsed():
                self.last_sound_at = self._now()
                await self._play_media_if_needed(rule_id, priority)

    async def on_alarm_acknowledged(self, rule_id: str) -> None:
        """Remove an alarm from the audible set."""

        self.active_audible_alarms.pop(rule_id, None)
        if not self.active_audible_alarms:
            self.horn_active = self.test_until is not None

    async def silence(self, duration_seconds: int | None = None) -> None:
        """Silence the horn without acknowledging alarms."""

        self.horn_active = False
        self.test_until = None
        self.silenced = True
        self.silenced_until = (
            self._now() + timedelta(seconds=duration_seconds)
            if duration_seconds
            else None
        )

    async def unsilence(self) -> None:
        """Unsilence the horn."""

        self.silenced = False
        self.silenced_until = None
        self._refresh_horn()

    async def test_sound(self, priority: AlarmPriority = AlarmPriority.CRITICAL) -> None:
        """Play a one-shot test sound.

        ``horn_active`` is raised for ``TEST_SOUND_SECONDS`` so a browser panel can
        play its tone, then drops back to the real horn state on the next timer.
        """

        if self.sound_mode != "none":
            now = self._now()
            self.horn_active = True
            self.last_sound_at = now
            self.test_until = now + timedelta(seconds=TEST_SOUND_SECONDS)
        await self._play_media_if_needed("__test__", priority)

    def next_timer_due(self) -> datetime | None:
        """Return when ``async_process_timers`` should next run, if ever."""

        due: list[datetime] = []
        if self.silenced and self.silenced_until is not None:
            due.append(self.silenced_until)
        if self.test_until is not None:
            due.append(self.test_until)
        if self._repeat_enabled():
            base = self.last_sound_at or self._now()
            due.append(base + timedelta(seconds=self.repeat_interval_seconds))
        return min(due) if due else None

    async def async_process_timers(self, now: datetime | None = None) -> bool:
        """Apply due timed behaviour; return True if the horn state changed."""

        now = now or self._now()
        before = (self.horn_active, self.silenced, self.silenced_until)

        if self.test_until is not None and self.test_until <= now:
            self.test_until = None
            self._refresh_horn()

        if (
            self.silenced
            and self.silenced_until is not None
            and self.silenced_until <= now
        ):
            self.silenced = False
            self.silenced_until = None
            self._refresh_horn()
            if self.horn_active and self.active_audible_alarms:
                await self._resound(now)
        elif self._repeat_enabled():
            base = self.last_sound_at or now
            if base + timedelta(seconds=self.repeat_interval_seconds) <= now:
                await self._resound(now)

        return before != (self.horn_active, self.silenced, self.silenced_until)

    def _repeat_enabled(self) -> bool:
        return (
            self.repeat_until_silenced
            and self.repeat_interval_seconds > 0
            and self._horn_should_be_active()
            and self.media_player_enabled
            and self._media_call is not None
        )

    async def _resound(self, now: datetime) -> None:
        rule_id, priority = self._highest_priority_alarm()
        self.last_sound_at = now
        if rule_id is not None and priority is not None:
            await self._play_media_if_needed(rule_id, priority)

    def _highest_priority_alarm(self) -> tuple[str | None, AlarmPriority | None]:
        if not self.active_audible_alarms:
            return None, None
        return max(
            self.active_audible_alarms.items(),
            key=lambda item: int(PRIORITY_PROFILES[item[1]]["severity"]),
        )

    async def _play_media_if_needed(
        self, rule_id: str, priority: AlarmPriority
    ) -> None:
        if not self.media_player_enabled or not self._media_call:
            return
        try:
            await self._media_call(rule_id, priority)
        except Exception:  # pragma: no cover - defensive around HA service calls
            _LOGGER.exception("Failed to play alarm sound through media players")

    def _sound_cooldown_elapsed(self) -> bool:
        if self.last_sound_at is None or self.repeat_interval_seconds <= 0:
            return True
        return self._now() - self.last_sound_at >= timedelta(
            seconds=self.repeat_interval_seconds
        )

    def to_state(self) -> dict[str, Any]:
        """Return the persistent part of the horn state."""

        return {
            "silenced": self.silenced,
            "silenced_until": self.silenced_until.isoformat()
            if self.silenced_until
            else None,
            "last_sound_at": self.last_sound_at.isoformat()
            if self.last_sound_at
            else None,
        }

    def restore(
        self,
        audible_alarms: dict[str, AlarmPriority],
        state: dict[str, Any] | None = None,
    ) -> None:
        """Restore horn state after a restart without re-playing media."""

        state = state or {}
        self.active_audible_alarms = dict(audible_alarms)
        self.silenced = bool(state.get("silenced", False))
        self.silenced_until = _parse_datetime(state.get("silenced_until"))
        self.last_sound_at = _parse_datetime(state.get("last_sound_at"))
        if (
            self.silenced
            and self.silenced_until is not None
            and self.silenced_until <= self._now()
        ):
            self.silenced = False
            self.silenced_until = None
        self.test_until = None
        self._refresh_horn()

    def as_dict(self) -> dict[str, Any]:
        """Return API status."""

        return {
            "sound_mode": self.sound_mode,
            "browser_enabled": self.browser_enabled,
            "media_player_enabled": self.media_player_enabled,
            "media_players": self.media_players,
            "horn_active": self.horn_active,
            "silenced": self.silenced,
            "silenced_until": self.silenced_until.isoformat()
            if self.silenced_until
            else None,
            "active_audible_alarms": list(self.active_audible_alarms),
            "last_sound_at": self.last_sound_at.isoformat()
            if self.last_sound_at
            else None,
            "repeat_until_silenced": self.repeat_until_silenced,
            "repeat_interval_seconds": self.repeat_interval_seconds,
            "test_until": self.test_until.isoformat() if self.test_until else None,
        }
