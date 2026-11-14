import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import daily_submit as daily


class DailySubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state.json"
        self.legacy = Path(self.temp.name) / "legacy.txt"
        for name, value in [("STATE_PATH", self.state), ("LEGACY_STATE_PATH", self.legacy)]:
            patcher = patch.object(daily, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.now = datetime(2026, 11, 15, 9, tzinfo=daily.LOCAL_TIMEZONE)

    def execute(self, delay=1800, code=0, dry_run=False, oversleep=0, timeout=False):
        def advance(seconds):
            self.now += timedelta(seconds=seconds + oversleep)
        with patch.object(daily, "local_now", side_effect=lambda: self.now), \
             patch.object(daily, "choose_delay", return_value=delay), \
             patch.object(daily.time, "sleep", side_effect=advance) as sleep, \
             patch.object(daily.subprocess, "run", return_value=Mock(returncode=code)) as upload:
            if timeout:
                upload.side_effect = subprocess.TimeoutExpired("main.py", 300)
            result = daily.run(dry_run)
        return result, upload, sleep

    def test_window_is_utc_plus_eight_and_excludes_18(self):
        for hour, minute, allowed in [(7, 59, False), (8, 0, True), (17, 59, True), (18, 0, False)]:
            now = self.now.replace(hour=hour, minute=minute)
            self.assertEqual(daily.within_window(now), allowed)
            self.assertEqual(daily.within_window(now.astimezone(timezone.utc)), allowed)

    def test_normal_wait_range_and_late_shortening(self):
        cases = [(9, 0, 1200, 2400), (17, 40, 0, 900), (17, 55, 0, 0), (17, 59, 0, 0)]
        for hour, minute, lower, upper in cases:
            chooser = Mock(return_value=upper)
            self.assertEqual(daily.choose_delay(self.now.replace(hour=hour, minute=minute), chooser), upper)
            chooser.assert_called_once_with(lower, upper)

    def test_wait_then_upload_and_persist_success(self):
        result, upload, sleep = self.execute()
        self.assertEqual(result, 0)
        self.assertEqual(self.now.minute, 30)
        upload.assert_called_once()
        self.assertTrue(sleep.called)
        self.assertEqual(upload.call_args.kwargs["env"]["DAILY_AUTOMATIC"], "true")
        self.assertEqual(json.loads(self.state.read_text())["submitted_date"], "2026-11-15")
        _, second_upload, second_sleep = self.execute()
        second_upload.assert_not_called()
        second_sleep.assert_not_called()

    def test_previous_day_does_not_block_new_day(self):
        daily.record_success("2026-11-14", self.now)
        _, upload, _ = self.execute(delay=0)
        upload.assert_called_once()

    def test_migration_preserves_today_success(self):
        self.legacy.write_text("scheduled date: 2026-11-15\nsubmitted date: 2026-11-15\n")
        _, upload, sleep = self.execute()
        upload.assert_not_called()
        sleep.assert_not_called()

    def test_outside_window_never_uploads(self):
        for hour in (7, 18, 23):
            self.now = self.now.replace(hour=hour)
            _, upload, sleep = self.execute()
            upload.assert_not_called()
            sleep.assert_not_called()

    def test_oversleep_past_close_never_uploads(self):
        self.now = self.now.replace(hour=17, minute=50)
        _, upload, _ = self.execute(delay=300, oversleep=3600)
        upload.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_crossing_midnight_never_uploads(self):
        _, upload, _ = self.execute(oversleep=24 * 3600)
        upload.assert_not_called()

    def test_failure_allows_a_later_retry(self):
        result, _, _ = self.execute(delay=0, code=1)
        self.assertEqual(result, 1)
        self.assertFalse(self.state.exists())
        result, upload, _ = self.execute(delay=0)
        self.assertEqual(result, 0)
        upload.assert_called_once()

    def test_timeout_does_not_record_success(self):
        result, _, _ = self.execute(delay=0, timeout=True)
        self.assertEqual(result, 1)
        self.assertFalse(self.state.exists())

    def test_dry_run_never_waits_uploads_or_changes_state(self):
        result, upload, sleep = self.execute(dry_run=True)
        self.assertEqual(result, 0)
        upload.assert_not_called()
        sleep.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_corrupt_state_fails_closed(self):
        self.state.write_text("not json")
        with self.assertRaises(json.JSONDecodeError):
            self.execute()


if __name__ == "__main__":
    unittest.main()
