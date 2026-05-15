"""Alarm sound and horn state manager."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from .alarm_models import AlarmPriority

_LOGGER = logging.getLogger(__name__)

MediaCall = Callable[[str, AlarmPriority], Awaitable[None]]


class AlarmSoundManager:
    """Manage audible alarm state for browser and media-player sound."""

    def __init__(
        self,
        *,
        sound_mode: str = "browser_only",
        repeat_interval_seconds: int = 30,
        media_players: list[str] | None = None,
        media_call: MediaCall | None = None,
    ) -> None:
        self.sound_mode = sound_mode
        self.repeat_interval_seconds = repeat_interval_seconds
        self.media_players = media_players or []
        self._media_call = media_call
        self.active_audible_alarms: dict[str, AlarmPriority] = {}
        self.horn_active = False
        self.silenced = False
        self.silenced_until: datetime | None = None
        self.last_sound_at: datetime | None = None

    @property
    def browser_enabled(self) -> bool:
        """Return whether browser panel sound should be active."""

        return self.sound_mode in {"browser_only", "browser_and_media_player"}

    @property
    def media_player_enabled(self) -> bool:
        """Return whether media player sound should be active."""

        return self.sound_mode in {"media_player_only", "browser_and_media_player"}

    async def on_alarm_requires_sound(
        self, rule_id: str, priority: AlarmPriority
    ) -> None:
        """Start or re-start sound for a new unacknowledged audible alarm."""

        new_alarm = rule_id not in self.active_audible_alarms
        self.active_audible_alarms[rule_id] = priority
        if self.sound_mode == "none":
            return
        if new_alarm:
            self.silenced = False
            self.silenced_until = None
        if not self.silenced:
            self.horn_active = True
            self.last_sound_at = datetime.now(UTC)
            await self._play_media_if_needed(rule_id, priority)

    async def on_alarm_acknowledged(self, rule_id: str) -> None:
        """Remove an alarm from the audible set."""

        self.active_audible_alarms.pop(rule_id, None)
        if not self.active_audible_alarms:
            self.horn_active = False

    async def silence(self, duration_seconds: int | None = None) -> None:
        """Silence the horn without acknowledging alarms."""

        self.horn_active = False
        self.silenced = True
        self.silenced_until = (
            datetime.now(UTC) + timedelta(seconds=duration_seconds)
            if duration_seconds
            else None
        )

    async def unsilence(self) -> None:
        """Unsilence the horn."""

        self.silenced = False
        self.silenced_until = None
        self.horn_active = bool(self.active_audible_alarms) and self.sound_mode != "none"

    async def test_sound(self, priority: AlarmPriority = AlarmPriority.CRITICAL) -> None:
        """Play a one-shot test sound."""

        if self.sound_mode != "none":
            self.horn_active = True
            self.last_sound_at = datetime.now(UTC)
        await self._play_media_if_needed("__test__", priority)

    async def _play_media_if_needed(
        self, rule_id: str, priority: AlarmPriority
    ) -> None:
        if not self.media_player_enabled or not self._media_call:
            return
        try:
            await self._media_call(rule_id, priority)
        except Exception:  # pragma: no cover - defensive around HA service calls
            _LOGGER.exception("Failed to play alarm sound through media players")

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
        }
