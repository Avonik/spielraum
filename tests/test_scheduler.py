from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spielraum.config import Settings
from spielraum.scheduler import run_job
from spielraum.storage import connect, initialize


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


if __name__ == "__main__":
    unittest.main()
