"""Ink reserve, persistent consumption and resets must not invent ink."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"commun"))
from inkora.printer import Snapshot
from inkora.store import Store


class ReserveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/"ink.sqlite3"
        self.store = Store(self.path)
        self.base = Snapshot("printer-A", "192.168.1.55", datetime.now(timezone.utc).isoformat(),
                             "Prête", True, 100, 60, 2, {"cyan": 100}, True)
        self.store.observe(self.base)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_default_standard_cartridge_and_precautionary_reserve(self):
        self.store.calibrate(self.base, ["cyan"])
        full = self.store.estimates(self.base)["cyan"]
        self.assertEqual((full["profile"], full["pages"], full["usable_pages"]), ("604", 130, 104))
        reserve = replace(self.base, color_pages=204)
        self.store.observe(reserve)
        estimate = self.store.estimates(reserve)["cyan"]
        self.assertEqual((estimate["state"], estimate["usable_pages"]), ("reserve", 0))
        self.assertAlmostEqual(estimate["percent"], 20)
        self.assertGreater(estimate["pages"], 0)

    def test_external_reset_keeps_consumption_and_does_not_refill(self):
        self.store.calibrate(self.base, ["cyan", "magenta"], "604", 35)
        later = replace(self.base, color_pages=110, reported_ink={"cyan": 100, "magenta": 100})
        self.store.observe(later)
        before = self.store.estimates(later)
        self.store.record_chip_reset(later, ["cyan"])
        self.assertEqual(self.store.estimates(later), before)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.estimates(later), before)

    def test_reported_full_never_refills_the_local_tracking(self):
        self.store.calibrate(self.base, ["cyan"], start=12)
        after_reset = replace(self.base, reported_ink={"cyan": 100})
        self.store.observe(after_reset)
        self.assertAlmostEqual(self.store.estimates(after_reset)["cyan"]["percent"], 12)

    def test_reset_without_a_known_baseline_cannot_create_ink(self):
        with self.assertRaises(ValueError):
            self.store.record_chip_reset(self.base, ["cyan"])
        self.assertIsNone(self.store.estimates(self.base)["cyan"])

    def test_usage_changes_only_affect_new_pages(self):
        self.store.calibrate(self.base, ["black"])
        first = replace(self.base, color_pages=110)
        self.store.observe(first)
        self.store.set_setting("coverage", 5.0)
        self.assertEqual(self.store.estimates(first)["black"]["used"], 10)
        second = replace(first, color_pages=115)
        self.store.observe(second)
        self.assertEqual(self.store.estimates(second)["black"]["used"], 35)
        before = self.store.estimates(second)["black"]["percent"]
        self.store.set_setting("coverage", 1.0)
        self.assertEqual(self.store.estimates(second)["black"]["percent"], before)
        self.store.observe(replace(second, color_pages=116))
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.estimates(self.store.latest())["black"]["used"], 36)

    def test_alerts_once_per_threshold_survive_restart_and_reset(self):
        self.store.calibrate(self.base, ["cyan"], start=40)
        low = replace(self.base, color_pages=113)
        alerts = self.store.observe(low)
        self.assertEqual([a["state"] for a in alerts], ["low"])
        self.assertEqual(self.store.observe(low), [])
        self.store.record_chip_reset(low, ["cyan"])
        self.assertEqual(self.store.observe(low), [])
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.observe(low), [])
        reserve = replace(self.base, color_pages=126)
        self.assertEqual([a["state"] for a in self.store.observe(reserve)], ["reserve"])
        self.assertEqual(self.store.observe(reserve), [])

    def test_real_refill_only_changes_selected_color(self):
        self.store.calibrate(self.base, ["cyan", "magenta"], start=20)
        self.store.observe(self.base)
        magenta = self.store.estimates(self.base)["magenta"]
        self.store.calibrate(self.base, ["cyan"], start=100)
        self.assertEqual(self.store.estimates(self.base)["magenta"], magenta)
        self.assertEqual(self.store.estimates(self.base)["cyan"]["percent"], 100)
        self.assertEqual(self.store.check_alerts(self.base), [])

    def test_missing_counters_or_baselines_do_not_estimate_a_level(self):
        self.assertEqual(self.store.alerts(self.base), [])
        self.store.calibrate(self.base, ["cyan"])
        self.assertIsNone(self.store.estimates(replace(self.base, color_pages=None))["cyan"])

    def test_rollback_after_a_missing_reading_never_revives_old_ink(self):
        self.store.calibrate(self.base, ["cyan"])
        self.store.observe(replace(self.base, color_pages=110))
        self.store.observe(replace(self.base, color_pages=None, mono_pages=None))
        self.store.observe(replace(self.base, color_pages=3, mono_pages=2))
        self.store.observe(replace(self.base, color_pages=120, mono_pages=65))
        self.assertIsNone(self.store.estimates(self.store.latest())["cyan"])

    def test_invalid_safety_settings_do_not_change_saved_thresholds(self):
        self.store.set_safety(35, 15, False)
        for warning, reserve in [(20, 30), (30, 0), (30, float("nan")), (float("inf"), 20), (90, 20)]:
            with self.subTest(warning=warning, reserve=reserve):
                with self.assertRaises(ValueError):
                    self.store.set_safety(warning, reserve)
        self.assertEqual(self.store.setting("warning_percent"), 35)
        self.assertEqual(self.store.setting("reserve_percent"), 15)
        self.assertFalse(self.store.setting("notifications"))

    def test_invalid_usage_does_not_change_saved_consumption(self):
        self.store.calibrate(self.base, ["cyan"])
        for value in [0, -1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                self.store.set_setting("coverage", value)
        self.assertEqual(self.store.estimates(self.base)["cyan"]["percent"], 100)


class LegacyMigrationTests(unittest.TestCase):
    def test_old_database_consumption_is_carried_once_without_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"legacy.sqlite3"
            base = Snapshot("legacy", "192.168.1.55", datetime.now(timezone.utc).isoformat(),
                            "Prête", True, 110, 60)
            with sqlite3.connect(path) as db:
                db.executescript("""
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE readings(id INTEGER PRIMARY KEY,printer TEXT,at TEXT,payload TEXT);
                CREATE TABLE cartridges(printer TEXT,color TEXT,at TEXT,profile TEXT,capacity INTEGER,
                  start REAL,color_baseline INTEGER,mono_baseline INTEGER,PRIMARY KEY(printer,color));
                """)
                db.execute("INSERT INTO settings VALUES('coverage','1.8')")
                db.execute("INSERT INTO readings VALUES(1,?,?,?)", (base.printer_id, base.observed_at, json.dumps(base.to_dict())))
                db.execute("INSERT INTO cartridges VALUES(?,?,?,?,?,?,?,?)", (base.printer_id,"cyan",base.observed_at,"604",130,100,100,60))
            db.close()
            store = Store(path)
            self.assertEqual(store.estimates(base)["cyan"]["used"], 18)
            store.set_setting("coverage", 1.0)
            self.assertEqual(store.estimates(base)["cyan"]["used"], 18)
            next_page = replace(base, color_pages=111)
            store.observe(next_page)
            store.close()
            store = Store(path)
            self.assertEqual(store.estimates(next_page)["cyan"]["used"], 19)
            store.close()


if __name__ == "__main__":
    unittest.main()
