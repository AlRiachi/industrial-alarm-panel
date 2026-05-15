import unittest

from custom_components.industrial_alarm_panel.alarm_models import AlarmPriority
from custom_components.industrial_alarm_panel.alarm_sound import AlarmSoundManager


class AlarmSoundTests(unittest.IsolatedAsyncioTestCase):
    async def test_silence_stops_horn_but_new_alarm_resounds(self) -> None:
        manager = AlarmSoundManager(sound_mode="browser_only")

        await manager.on_alarm_requires_sound("alarm-a", AlarmPriority.CRITICAL)
        self.assertTrue(manager.horn_active)

        await manager.silence(duration_seconds=60)
        self.assertFalse(manager.horn_active)
        self.assertTrue(manager.silenced)

        await manager.on_alarm_requires_sound("alarm-b", AlarmPriority.HIGH)
        self.assertTrue(manager.horn_active)
        self.assertFalse(manager.silenced)

    async def test_acknowledging_all_audible_alarms_stops_horn(self) -> None:
        manager = AlarmSoundManager(sound_mode="browser_only")

        await manager.on_alarm_requires_sound("alarm-a", AlarmPriority.CRITICAL)
        await manager.on_alarm_acknowledged("alarm-a")

        self.assertFalse(manager.horn_active)


if __name__ == "__main__":
    unittest.main()
