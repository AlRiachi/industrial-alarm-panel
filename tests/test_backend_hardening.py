"""Regression tests for the v1.1.0 backend hardening pass."""

import asyncio
import importlib.util
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from custom_components.industrial_alarm_panel.alarm_engine import AlarmEngine
from custom_components.industrial_alarm_panel.alarm_models import (
    AlarmEvent,
    AlarmLifecycleState,
    AlarmPriority,
    AlarmRule,
    AlarmRuleNotFoundError,
    AlarmRuntimeState,
    AlarmValidationError,
)
from custom_components.industrial_alarm_panel.alarm_sound import AlarmSoundManager
from custom_components.industrial_alarm_panel.alarm_store import (
    RETENTION_INTERVAL,
    InMemoryHistoryStore,
    MemoryRuleStore,
    schedule_history_retention,
)
from custom_components.industrial_alarm_panel.const import (
    DISPLAY_OPTION_KEYS,
    display_options,
)

COMPONENT = Path("custom_components/industrial_alarm_panel")
HAS_HA = importlib.util.find_spec("homeassistant") is not None


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


def make_rule(rule_id: str = "temp_high", **overrides) -> AlarmRule:
    data = {
        "id": rule_id,
        "entity_id": f"sensor.{rule_id}",
        "name": rule_id.replace("_", " ").title(),
        "condition": "above",
        "threshold": 75,
        "priority": "critical",
    }
    data.update(overrides)
    return AlarmRule.from_dict(data)


class Recorder:
    """Counts saves and notifications of an engine."""

    def __init__(self) -> None:
        self.saves = 0
        self.notifications = 0

    async def persist(self, _states) -> None:
        self.saves += 1

    def listener(self) -> None:
        self.notifications += 1


class EngineChangeTrackingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.clock = Clock()
        self.recorder = Recorder()

    def engine(self, rules, **kwargs) -> AlarmEngine:
        engine = AlarmEngine(
            rules,
            InMemoryHistoryStore(),
            now=self.clock.now,
            persist_states=self.recorder.persist,
            **kwargs,
        )
        engine.add_listener(self.recorder.listener)
        return engine

    async def test_unchanged_readings_do_not_save_or_notify(self) -> None:
        engine = self.engine([make_rule()])

        await engine.process_state("sensor.temp_high", "80")
        self.assertEqual((self.recorder.saves, self.recorder.notifications), (1, 1))
        self.assertEqual(engine.last_changed_rule_ids, ["temp_high"])

        for value in ("81", "82.5", "90", "79"):
            await engine.process_state("sensor.temp_high", value)
        self.assertEqual((self.recorder.saves, self.recorder.notifications), (1, 1))
        # The cached reading is still current for the panel/next flush.
        self.assertEqual(engine.get_alarm("temp_high").last_value, 79.0)

        await engine.process_state("sensor.temp_high", "70")
        self.assertEqual((self.recorder.saves, self.recorder.notifications), (2, 2))

    async def test_normal_readings_do_not_save_or_notify(self) -> None:
        engine = self.engine([make_rule()])
        for value in ("10", "11", "12"):
            await engine.process_state("sensor.temp_high", value)
        self.assertEqual((self.recorder.saves, self.recorder.notifications), (0, 0))

    async def test_state_change_for_unrelated_entity_is_ignored(self) -> None:
        engine = self.engine([make_rule()])
        await engine.process_state("sensor.other", "999")
        self.assertEqual(engine.get_alarm("temp_high").lifecycle_state, AlarmLifecycleState.NORMAL)
        self.assertEqual(self.recorder.notifications, 0)

    async def test_rule_listener_only_fires_for_its_rule(self) -> None:
        engine = self.engine([make_rule("a"), make_rule("b")])
        calls: list[str] = []
        engine.add_rule_listener("a", lambda: calls.append("a"))
        engine.add_rule_listener("b", lambda: calls.append("b"))

        await engine.process_state("sensor.a", "80")

        self.assertEqual(calls, ["a"])

    async def test_acknowledge_all_is_one_save_and_one_notify(self) -> None:
        engine = self.engine([make_rule("a"), make_rule("b"), make_rule("c")])
        for rule_id in ("a", "b", "c"):
            await engine.process_state(f"sensor.{rule_id}", "80")
        self.recorder.saves = self.recorder.notifications = 0

        count = await engine.acknowledge_all(operator="op")

        self.assertEqual(count, 3)
        self.assertEqual((self.recorder.saves, self.recorder.notifications), (1, 1))
        self.assertEqual(engine.last_changed_rule_ids, ["a", "b", "c"])
        for rule_id in ("a", "b", "c"):
            self.assertEqual(
                engine.get_alarm(rule_id).lifecycle_state, AlarmLifecycleState.ACTIVE_ACK
            )

    async def test_acknowledge_all_with_nothing_to_ack_does_not_save(self) -> None:
        engine = self.engine([make_rule()])
        self.assertEqual(await engine.acknowledge_all(), 0)
        self.assertEqual((self.recorder.saves, self.recorder.notifications), (0, 0))

    async def test_update_rule_persists_and_disable_via_enabled_flag(self) -> None:
        engine = self.engine([make_rule()])
        await engine.process_state("sensor.temp_high", "80")
        self.recorder.saves = 0

        await engine.update_rule("temp_high", {"enabled": False})

        self.assertGreaterEqual(self.recorder.saves, 1)
        self.assertEqual(
            engine.get_alarm("temp_high").lifecycle_state, AlarmLifecycleState.DISABLED
        )

        await engine.update_rule("temp_high", {"enabled": True})
        # Re-enabling re-evaluates the cached source reading (80 > 75).
        self.assertEqual(
            engine.get_alarm("temp_high").lifecycle_state,
            AlarmLifecycleState.ACTIVE_UNACK,
        )

    async def test_update_threshold_reevaluates_cached_source(self) -> None:
        engine = self.engine([make_rule()])
        await engine.process_state("sensor.temp_high", "70")
        await engine.update_rule("temp_high", {"threshold": 60})
        self.assertTrue(engine.get_alarm("temp_high").is_active)

    async def test_unknown_rule_raises_not_found(self) -> None:
        engine = self.engine([])
        with self.assertRaises(AlarmRuleNotFoundError):
            await engine.acknowledge_alarm("missing")
        with self.assertRaises(KeyError):
            await engine.update_rule("missing", {})
        with self.assertRaises(AlarmRuleNotFoundError):
            await engine.delete_rule("missing")

    async def test_store_normal_events_records_status_rows_without_saving(self) -> None:
        history = InMemoryHistoryStore()
        engine = AlarmEngine(
            [make_rule()],
            history,
            now=self.clock.now,
            persist_states=self.recorder.persist,
            store_normal_events=True,
        )
        await engine.process_state("sensor.temp_high", "10")
        await engine.process_state("sensor.temp_high", "11")
        await engine.process_state("sensor.temp_high", "11")

        status_rows = [e for e in history.events if e.event_type == "status_changed"]
        self.assertEqual(len(status_rows), 1)
        self.assertEqual(self.recorder.saves, 0)

    async def test_default_delay_and_deadband_apply_to_new_rules_only_when_missing(self) -> None:
        engine = self.engine(
            [],
            default_delay_on_seconds=5,
            default_delay_off_seconds=7,
            default_deadband=2,
        )
        rule = await engine.create_rule(
            {"id": "x", "entity_id": "sensor.x", "name": "X", "condition": "above", "threshold": 1}
        )
        self.assertEqual(
            (rule.delay_on_seconds, rule.delay_off_seconds, rule.deadband), (5, 7, 2.0)
        )
        explicit = await engine.create_rule(
            {
                "id": "y",
                "entity_id": "sensor.y",
                "name": "Y",
                "condition": "above",
                "threshold": 1,
                "delay_on_seconds": 1,
            }
        )
        self.assertEqual(explicit.delay_on_seconds, 1)

    async def test_evaluate_sources_raises_alarms_for_out_of_range_sources(self) -> None:
        engine = self.engine(
            [
                make_rule("hot"),
                make_rule("changed", condition="state_changed", threshold=None),
            ]
        )
        states = {"sensor.hot": "99", "sensor.changed": "on"}

        await engine.async_evaluate_sources(states.get)

        self.assertEqual(engine.get_alarm("hot").lifecycle_state, AlarmLifecycleState.ACTIVE_UNACK)
        self.assertEqual(engine.get_alarm("changed").lifecycle_state, AlarmLifecycleState.NORMAL)


class BadQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_does_not_clear_active_above_alarm(self) -> None:
        engine = AlarmEngine([make_rule()], InMemoryHistoryStore())
        await engine.process_state("sensor.temp_high", "80")

        for bad in ("unavailable", "unknown", "garbage", None):
            await engine.process_state("sensor.temp_high", bad)
            self.assertEqual(
                engine.get_alarm("temp_high").lifecycle_state,
                AlarmLifecycleState.ACTIVE_UNACK,
            )

        await engine.process_state("sensor.temp_high", "10")
        self.assertEqual(
            engine.get_alarm("temp_high").lifecycle_state,
            AlarmLifecycleState.CLEARED_UNACK,
        )

    async def test_unavailable_does_not_clear_active_below_alarm(self) -> None:
        engine = AlarmEngine(
            [make_rule("low", condition="below", threshold=10)], InMemoryHistoryStore()
        )
        await engine.process_state("sensor.low", "5")
        await engine.process_state("sensor.low", "unavailable")
        self.assertTrue(engine.get_alarm("low").is_active)

    async def test_bad_quality_cancels_pending_timers_without_spinning(self) -> None:
        clock = Clock()
        engine = AlarmEngine(
            [make_rule(delay_on_seconds=5)], InMemoryHistoryStore(), now=clock.now
        )
        await engine.process_state("sensor.temp_high", "80")
        self.assertIsNotNone(engine.next_due_transition_at())

        await engine.process_state("sensor.temp_high", "unavailable")

        self.assertIsNone(engine.next_due_transition_at())
        self.assertEqual(engine.get_alarm("temp_high").lifecycle_state, AlarmLifecycleState.NORMAL)

    async def test_unavailable_condition_still_alarms(self) -> None:
        engine = AlarmEngine(
            [make_rule("lost", condition="unavailable", threshold=None)],
            InMemoryHistoryStore(),
        )
        await engine.process_state("sensor.lost", "unavailable")
        self.assertTrue(engine.get_alarm("lost").is_active)


class ShelveExpiryTests(unittest.IsolatedAsyncioTestCase):
    async def test_shelve_expiry_is_a_due_transition_and_reevaluates_source(self) -> None:
        clock = Clock()
        sound = AlarmSoundManager(sound_mode="browser_only", now=clock.now)
        engine = AlarmEngine(
            [make_rule()], InMemoryHistoryStore(), now=clock.now, sound_manager=sound
        )
        await engine.shelve_alarm("temp_high", duration_minutes=10)
        await engine.process_state("sensor.temp_high", "90")
        self.assertEqual(engine.get_alarm("temp_high").lifecycle_state, AlarmLifecycleState.SHELVED)
        self.assertEqual(
            engine.next_due_transition_at(), datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
        )

        clock.advance(9 * 60)
        await engine.process_due_transitions()
        self.assertEqual(engine.get_alarm("temp_high").lifecycle_state, AlarmLifecycleState.SHELVED)

        clock.advance(60)
        await engine.process_due_transitions()  # no source change needed

        runtime = engine.get_alarm("temp_high")
        self.assertEqual(runtime.lifecycle_state, AlarmLifecycleState.ACTIVE_UNACK)
        self.assertIsNone(runtime.shelve_expiry)
        self.assertTrue(sound.horn_active)

    async def test_shelve_expiry_with_normal_source_returns_to_normal(self) -> None:
        clock = Clock()
        engine = AlarmEngine([make_rule()], InMemoryHistoryStore(), now=clock.now)
        await engine.shelve_alarm("temp_high", duration_minutes=1)
        await engine.process_state("sensor.temp_high", "20")
        clock.advance(61)
        await engine.process_due_transitions()
        self.assertEqual(engine.get_alarm("temp_high").lifecycle_state, AlarmLifecycleState.NORMAL)
        self.assertIsNone(engine.next_due_transition_at())


class FlappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_shelved_flapping_alarm_does_not_request_sound(self) -> None:
        clock = Clock()
        requested: list[str] = []

        class SpySound(AlarmSoundManager):
            async def on_alarm_requires_sound(self, rule_id, priority) -> None:
                requested.append(rule_id)
                await super().on_alarm_requires_sound(rule_id, priority)

        sound = SpySound(sound_mode="browser_only", now=clock.now)
        engine = AlarmEngine(
            [make_rule(auto_ack_on_clear=True)],
            InMemoryHistoryStore(),
            now=clock.now,
            sound_manager=sound,
            flapping_threshold=3,
            auto_shelve_flapping=True,
        )

        for _ in range(3):
            await engine.process_state("sensor.temp_high", "80")
            clock.advance(1)
            await engine.process_state("sensor.temp_high", "10")
            clock.advance(1)

        self.assertEqual(engine.get_alarm("temp_high").lifecycle_state, AlarmLifecycleState.SHELVED)
        self.assertEqual(len(requested), 2)
        self.assertFalse(sound.horn_active)


class SoundTimerTests(unittest.IsolatedAsyncioTestCase):
    async def test_timed_silence_expires_server_side(self) -> None:
        clock = Clock()
        sound = AlarmSoundManager(sound_mode="browser_only", now=clock.now)
        await sound.on_alarm_requires_sound("a", AlarmPriority.HIGH)
        await sound.silence(duration_seconds=30)
        self.assertFalse(sound.horn_active)
        self.assertEqual(sound.next_timer_due(), clock.now() + timedelta(seconds=30))

        clock.advance(29)
        self.assertFalse(await sound.async_process_timers())
        clock.advance(1)
        self.assertTrue(await sound.async_process_timers())

        self.assertTrue(sound.horn_active)
        self.assertFalse(sound.silenced)
        self.assertTrue(sound.as_dict()["horn_active"])

    async def test_repeat_until_silenced_replays_media(self) -> None:
        clock = Clock()
        calls: list[str] = []

        async def media_call(rule_id: str, _priority: AlarmPriority) -> None:
            calls.append(rule_id)

        sound = AlarmSoundManager(
            sound_mode="media_player_only",
            repeat_interval_seconds=30,
            repeat_until_silenced=True,
            media_call=media_call,
            now=clock.now,
        )
        await sound.on_alarm_requires_sound("a", AlarmPriority.HIGH)
        self.assertEqual(sound.next_timer_due(), clock.now() + timedelta(seconds=30))
        clock.advance(30)
        await sound.async_process_timers()
        self.assertEqual(calls, ["a", "a"])

        await sound.silence()
        self.assertIsNone(sound.next_timer_due())

    async def test_no_repeat_when_disabled(self) -> None:
        async def media_call(_rule_id: str, _priority: AlarmPriority) -> None:
            return None

        sound = AlarmSoundManager(
            sound_mode="media_player_only",
            repeat_until_silenced=False,
            media_call=media_call,
        )
        await sound.on_alarm_requires_sound("a", AlarmPriority.HIGH)
        self.assertIsNone(sound.next_timer_due())

    async def test_test_sound_horn_drops_back_after_timer(self) -> None:
        clock = Clock()
        sound = AlarmSoundManager(sound_mode="browser_only", now=clock.now)
        await sound.test_sound()
        self.assertTrue(sound.horn_active)
        clock.advance(10)
        await sound.async_process_timers()
        self.assertFalse(sound.horn_active)

    async def test_engine_restores_horn_for_unacknowledged_audible_alarms(self) -> None:
        clock = Clock()
        store = MemoryRuleStore(
            [make_rule("a"), make_rule("b", audible=False)],
            [
                AlarmRuntimeState(rule_id="a", lifecycle_state=AlarmLifecycleState.ACTIVE_UNACK),
                AlarmRuntimeState(rule_id="b", lifecycle_state=AlarmLifecycleState.ACTIVE_UNACK),
            ],
        )
        sound = AlarmSoundManager(sound_mode="browser_only", now=clock.now)
        engine = await AlarmEngine.from_store(
            store, InMemoryHistoryStore(), sound_manager=sound, now=clock.now
        )
        self.assertTrue(sound.horn_active)
        self.assertEqual(list(sound.active_audible_alarms), ["a"])

        await engine.silence_horn(60)
        self.assertEqual(store.sound_state["silenced"], True)

        restored_sound = AlarmSoundManager(sound_mode="browser_only", now=clock.now)
        store.sound_state = dict(store.sound_state)
        await AlarmEngine.from_store(
            store, InMemoryHistoryStore(), sound_manager=restored_sound, now=clock.now
        )
        self.assertTrue(restored_sound.silenced)
        self.assertFalse(restored_sound.horn_active)


class RetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_retention_runs_now_and_is_scheduled_daily(self) -> None:
        history = InMemoryHistoryStore()
        now = datetime.now(UTC)
        await history.add_event(
            AlarmEvent(rule_id="old", entity_id=None, event_type="activated", timestamp=now - timedelta(days=40))
        )
        await history.add_event(
            AlarmEvent(rule_id="new", entity_id=None, event_type="activated", timestamp=now)
        )
        scheduled: list = []
        tasks: list = []

        class FakeHass:
            def async_create_task(self, coro):
                task = asyncio.ensure_future(coro)
                tasks.append(task)
                return task

        def fake_track(hass, action, interval):
            scheduled.append((action, interval))
            return lambda: scheduled.append("cancelled")

        remove = schedule_history_retention(FakeHass(), history, 30, fake_track)
        await asyncio.gather(*tasks)

        self.assertEqual(scheduled[0][1], RETENTION_INTERVAL)
        self.assertEqual(RETENTION_INTERVAL, timedelta(days=1))
        self.assertEqual([event.rule_id for event in history.events], ["new"])

        self.assertEqual(await scheduled[0][0](now), 0)
        remove()
        self.assertEqual(scheduled[-1], "cancelled")


class DisplayOptionTests(unittest.TestCase):
    def test_display_options_expose_ui_only_settings(self) -> None:
        display = display_options({"enable_flashing": False, "group_by": "area"})
        self.assertEqual(set(display), set(DISPLAY_OPTION_KEYS))
        self.assertFalse(display["enable_flashing"])
        self.assertEqual(display["group_by"], "area")
        self.assertEqual(display["default_tab"], "active")


class StaticContractTests(unittest.TestCase):
    def test_translations_mirror_strings(self) -> None:
        strings = json.loads((COMPONENT / "strings.json").read_text())
        translations = json.loads((COMPONENT / "translations/en.json").read_text())
        self.assertEqual(strings, translations)
        self.assertIn("services", translations)
        self.assertIn("data_description", translations["options"]["step"]["init"])

    def test_manifest_declares_service_integration_type(self) -> None:
        manifest = json.loads((COMPONENT / "manifest.json").read_text())
        self.assertEqual(manifest["integration_type"], "service")

    def test_no_hass_data_runtime_lookup_in_platforms(self) -> None:
        for name in ("binary_sensor", "sensor", "button", "switch", "number", "select", "diagnostics"):
            source = (COMPONENT / f"{name}.py").read_text()
            self.assertNotIn("hass.data[DOMAIN]", source, name)
            self.assertIn("runtime_data", source, name)

    def test_rule_changes_do_not_reload_the_config_entry(self) -> None:
        for name in ("websocket_api", "services"):
            source = (COMPONENT / f"{name}.py").read_text()
            self.assertNotIn("async_reload", source, name)

    def test_binary_sensor_excludes_fast_changing_attributes_from_recorder(self) -> None:
        source = (COMPONENT / "binary_sensor.py").read_text()
        self.assertIn("_unrecorded_attributes", source)
        self.assertIn('"last_value"', source)
        self.assertIn('"last_source_state"', source)


class _FakeUser:
    def __init__(self, is_admin: bool) -> None:
        self.id = "user-admin" if is_admin else "user-operator"
        self.is_admin = is_admin


class _FakeConnection:
    def __init__(self, is_admin: bool = False) -> None:
        self.user = _FakeUser(is_admin)
        self.errors: list[tuple] = []
        self.results: list[tuple] = []

    def send_error(self, msg_id, code, message) -> None:
        self.errors.append((msg_id, code, message))

    def send_result(self, msg_id, result=None) -> None:
        self.results.append((msg_id, result))


class _FakeHass:
    def __init__(self) -> None:
        self.scheduled = 0

    def async_create_background_task(self, coro, name, eager_start=True):
        self.scheduled += 1
        coro.close()


@unittest.skipUnless(HAS_HA, "Home Assistant is not installed in this environment")
class WebsocketSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        from custom_components.industrial_alarm_panel import websocket_api as ws

        self.ws = ws

    def test_rule_mutations_require_admin(self) -> None:
        from homeassistant.exceptions import Unauthorized

        handlers = [
            self.ws.websocket_create_rule,
            self.ws.websocket_update_rule,
            self.ws.websocket_delete_rule,
            self.ws.websocket_delete_rules,
            self.ws.websocket_create_suggested_rules,
        ]
        for handler in handlers:
            hass = _FakeHass()
            with self.assertRaises(Unauthorized, msg=handler.__name__):
                handler(hass, _FakeConnection(is_admin=False), {"id": 1})
            self.assertEqual(hass.scheduled, 0)

            hass = _FakeHass()
            handler(hass, _FakeConnection(is_admin=True), {"id": 1})
            self.assertEqual(hass.scheduled, 1, handler.__name__)

    def test_operator_actions_stay_available_to_non_admins(self) -> None:
        handlers = [
            self.ws.websocket_list_alarms,
            self.ws.websocket_list_history,
            self.ws.websocket_list_rules,
            self.ws.websocket_list_suggested_rules,
            self.ws.websocket_acknowledge,
            self.ws.websocket_acknowledge_all,
            self.ws.websocket_silence,
            self.ws.websocket_shelve,
            self.ws.websocket_test_sound,
            self.ws.websocket_export_history,
        ]
        for handler in handlers:
            hass = _FakeHass()
            handler(hass, _FakeConnection(is_admin=False), {"id": 1})
            self.assertEqual(hass.scheduled, 1, handler.__name__)

    def test_command_names_are_unchanged(self) -> None:
        expected = {
            "list_alarms", "list_history", "list_rules", "create_rule", "update_rule",
            "delete_rule", "delete_rules", "list_suggested_rules", "create_suggested_rules",
            "acknowledge", "acknowledge_all", "silence", "shelve", "test_sound",
            "export_history",
        }
        commands = {
            getattr(value, "_ws_command", "").split("/", 1)[-1]
            for value in vars(self.ws).values()
            if getattr(value, "_ws_command", None)
        }
        self.assertEqual(commands, expected)

    def test_export_history_is_capped(self) -> None:
        schema = self.ws.websocket_export_history._ws_schema
        msg = schema({"id": 1, "type": "industrial_alarm_panel/export_history"})
        self.assertEqual(msg["limit"], 10000)
        with self.assertRaises(Exception):
            schema({"id": 1, "type": "industrial_alarm_panel/export_history", "limit": 10001})


@unittest.skipUnless(HAS_HA, "Home Assistant is not installed in this environment")
class WebsocketErrorMappingTests(unittest.IsolatedAsyncioTestCase):
    async def _call(self, exc: BaseException) -> tuple:
        from custom_components.industrial_alarm_panel.websocket_api import handle_errors

        @handle_errors
        async def handler(hass, connection, msg) -> None:
            raise exc

        connection = _FakeConnection()
        await handler(None, connection, {"id": 7})
        self.assertEqual(len(connection.errors), 1)
        return connection.errors[0]

    async def test_unknown_rule_maps_to_not_found(self) -> None:
        self.assertEqual(
            await self._call(AlarmRuleNotFoundError("pump")),
            (7, "not_found", "Unknown alarm rule: pump"),
        )

    async def test_plain_key_error_maps_to_not_found(self) -> None:
        msg_id, code, message = await self._call(KeyError("pump"))
        self.assertEqual((msg_id, code), (7, "not_found"))
        self.assertIn("pump", message)

    async def test_validation_errors_map_to_invalid_format(self) -> None:
        for exc in (AlarmValidationError("threshold must be numeric"), ValueError("bad date")):
            msg_id, code, message = await self._call(exc)
            self.assertEqual((msg_id, code, message), (7, "invalid_format", str(exc)))

    async def test_not_loaded_maps_to_not_found(self) -> None:
        from custom_components.industrial_alarm_panel.runtime import (
            IntegrationNotLoadedError,
        )

        self.assertEqual(
            await self._call(IntegrationNotLoadedError()),
            (7, "not_found", "Industrial Alarm Panel is not loaded"),
        )


@unittest.skipUnless(HAS_HA, "Home Assistant is not installed in this environment")
class ServiceErrorMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_errors_become_service_validation_errors(self) -> None:
        from homeassistant.exceptions import ServiceValidationError

        from custom_components.industrial_alarm_panel import services

        handlers = {}

        class FakeServices:
            def async_register(self, domain, service, handler, schema=None, supports_response=None):
                handlers[service] = handler

        class FakeHassWithServices:
            def __init__(self) -> None:
                self.data = {}
                self.services = FakeServices()

        hass = FakeHassWithServices()
        original_admin = services.async_register_admin_service
        services.async_register_admin_service = (
            lambda hass, domain, service, handler, schema=None: handlers.__setitem__(service, handler)
        )
        original_runtime = services._first_runtime
        try:
            await services.async_setup_services(hass)
            engine = AlarmEngine([], InMemoryHistoryStore())

            class Runtime:
                pass

            runtime = Runtime()
            runtime.engine = engine
            services._first_runtime = lambda _hass: runtime

            class Call:
                service = "acknowledge_alarm"
                data = {"rule_id": "missing"}

                class context:
                    user_id = None

            with self.assertRaisesRegex(ServiceValidationError, "Unknown alarm rule: missing"):
                await handlers["acknowledge_alarm"](Call())
            self.assertEqual(set(handlers), set(services.SERVICE_SCHEMAS))
        finally:
            services.async_register_admin_service = original_admin
            services._first_runtime = original_runtime


if __name__ == "__main__":
    unittest.main()
