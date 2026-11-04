from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from spielraum.config import Settings
from spielraum.scheduler import run_job, tick
from spielraum.storage import connect, finish_run, initialize, read_dashboard, start_run


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        data_dir = Path(self.temporary.name)
        self.settings = Settings(data_dir=data_dir, database_path=data_dir / "spielraum.sqlite3")
        self.settings.ensure_directories()
        initialize(self.settings.database_path)

    def tearDown(self):
        self.temporary.cleanup()

    def _run_with_payload(self, payload: dict) -> str:
        completed = subprocess.CompletedProcess(
            args=["adapter"], returncode=0, stdout=json.dumps(payload) + "\n", stderr=""
        )
        with patch.dict(os.environ, {"SPIELRAUM_MODEL_COMMAND": "adapter"}), patch(
            "spielraum.scheduler.subprocess.run", return_value=completed
        ):
            return run_job(self.settings, "model")

    def test_model_waits_for_market_value_cutoff(self):
        status = self._run_with_payload({
            "matchday_complete": True,
            "xg_complete": True,
            "market_values_complete": False,
            "reason": "cutoff not reached",
        })
        self.assertEqual(status, "deferred")
        with connect(self.settings.database_path, readonly=True) as connection:
            row = connection.execute("SELECT status FROM pipeline_runs ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row["status"], "deferred")

    def test_completed_season_needs_no_snapshot(self):
        status = self._run_with_payload({
            "matchday_complete": True,
            "xg_complete": True,
            "market_values_complete": True,
            "season_complete": True,
        })
        self.assertEqual(status, "success")

    def test_understat_outage_persists_until_data_recovers(self):
        self.assertIsNone(read_dashboard(self.settings.database_path)["understatStatus"])
        with patch.dict(os.environ, {"SPIELRAUM_UNDERSTAT_COMMAND": ""}):
            for available in (False, True, False):
                # Ignore logs before the adapter's final JSON line.
                completed = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout='fetching data\n' + json.dumps({"available": available}), stderr=""
                )
                with patch("spielraum.scheduler.subprocess.run", return_value=completed) as run:
                    self.assertEqual(run_job(self.settings, "understat"), "success" if available else "failed")
                self.assertEqual(run.call_args.args[0][-1], "spielraum.adapters.understat_status")
                self.assertEqual(run.call_args.kwargs["timeout"], 180)
                status = read_dashboard(self.settings.database_path)["understatStatus"]
                self.assertEqual(status["available"], available)
                self.assertIsNotNone(status["checkedAt"])
                # An in-flight check and unrelated model errors must not hide an outage
                # or falsely label a working provider as unavailable.
                start_run(self.settings.database_path, "understat", "2026-11-04T00:00:00+00:00")
                model = start_run(self.settings.database_path, "model", "2026-11-04T00:00:00+00:00")
                finish_run(self.settings.database_path, model, "2026-11-04T00:01:00+00:00", "failed", {"error": "model error"})
                self.assertEqual(read_dashboard(self.settings.database_path)["understatStatus"], status)

    def test_understat_checks_continue_outside_weekly_model_window(self):
        thursday = datetime(2026, 11, 5, 12, tzinfo=UTC)
        with patch("spielraum.scheduler._now", return_value=thursday) as now, patch(
            "spielraum.scheduler.run_job", return_value="success"
        ) as run:
            tick(self.settings)
            run.assert_any_call(self.settings, "understat")
            self.assertNotIn("model", [call.args[1] for call in run.call_args_list])
            run.reset_mock()
            now.return_value = thursday + timedelta(minutes=29)
            tick(self.settings)
            run.assert_not_called()
            now.return_value = thursday + timedelta(minutes=30)
            tick(self.settings)
            run.assert_called_once_with(self.settings, "understat")


if __name__ == "__main__":
    unittest.main()
