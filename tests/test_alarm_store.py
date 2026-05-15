import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from custom_components.industrial_alarm_panel.alarm_models import AlarmEvent
from custom_components.industrial_alarm_panel.alarm_store import SQLiteHistoryStore


class AlarmStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_history_store_inserts_queries_and_applies_retention(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteHistoryStore(Path(tmpdir) / "history.db")
            await store.async_setup()

            old = datetime(2026, 1, 1, tzinfo=UTC)
            new = old + timedelta(days=10)
            await store.add_event(
                AlarmEvent(
                    rule_id="old",
                    entity_id="sensor.old",
                    event_type="activated",
                    timestamp=old,
                )
            )
            await store.add_event(
                AlarmEvent(
                    rule_id="new",
                    entity_id="sensor.new",
                    event_type="acknowledged",
                    timestamp=new,
                )
            )

            events = await store.query_events()
            self.assertEqual([event.rule_id for event in events], ["new", "old"])

            deleted = await store.cleanup_retention(retention_days=7, now=new)
            self.assertEqual(deleted, 1)
            remaining = await store.query_events()
            self.assertEqual([event.rule_id for event in remaining], ["new"])


if __name__ == "__main__":
    unittest.main()
