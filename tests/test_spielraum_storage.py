from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from spielraum.seed import CLUBS, seed_preview
from spielraum.publish import publish_snapshot
from spielraum.storage import connect, initialize, read_dashboard


class SpielraumStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "test.sqlite3"
        initialize(self.database)
        seed_preview(self.database)

    def tearDown(self):
        self.temporary.cleanup()

    def test_preview_dashboard_round_trip(self):
        payload = read_dashboard(self.database)
        self.assertEqual(payload["mode"], "preview")
        self.assertEqual(payload["season"], "2026/27")
        self.assertEqual(len(payload["fixtures"]), 9)
        self.assertEqual(len(payload["history"]), 6)
        self.assertTrue(all(item["season"] == "2025/26" for item in payload["history"]))
        self.assertTrue(all(item["matchday"] == 34 for item in payload["history"]))
        self.assertEqual(len(payload["placements"]), 18)

    def test_predictions_are_immutable_and_cannot_be_backfilled(self):
        with connect(self.database) as connection:
            prediction_id = connection.execute("SELECT id FROM predictions LIMIT 1").fetchone()[0]
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("UPDATE predictions SET p_home = p_home WHERE id = ?", (prediction_id,))
            fixture = connection.execute("SELECT id FROM fixtures WHERE season = '2026/27' LIMIT 1").fetchone()[0]
            with self.assertRaisesRegex(sqlite3.IntegrityError, "before kickoff"):
                connection.execute(
                    """INSERT INTO predictions
                       (fixture_id, snapshot_id, model_version_id, published_at, p_home, p_draw, p_away)
                       VALUES (?, 'preview-md1', 'preview-2026-07-29', '2027-01-01T00:00:00+00:00', .4, .3, .3)""",
                    (fixture,),
                )

    def test_two_pre_kickoff_snapshots_can_publish_without_rewriting_history(self):
        fresh_database = Path(self.temporary.name) / "publish.sqlite3"
        initialize(fresh_database)
        teams = [
            {"slug": "home", "name": "Home", "short": "Home", "code": "HOM", "primary": "#111111", "secondary": "#eeeeee", "variant": "circle"},
            {"slug": "away", "name": "Away", "short": "Away", "code": "AWY", "primary": "#eeeeee", "secondary": "#111111", "variant": "shield"},
        ]
        base = {
            "season": "2026/27", "matchday": 1, "mode": "live", "teams": teams,
            "fixtures": [{"id": "game", "kickoff_utc": "2026-08-28T18:30:00+00:00", "home": "home", "away": "away", "probabilities": [.5, .3, .2]}],
        }
        first = {**base, "snapshot_id": "snap-1", "published_at": "2026-08-20T12:00:00+00:00",
                 "model": {"id": "model-1", "created_at": "2026-08-20T11:00:00+00:00", "config": {"carry": True}}}
        second = {**base, "snapshot_id": "snap-2", "published_at": "2026-08-24T12:00:00+00:00",
                  "model": {"id": "model-2", "created_at": "2026-08-24T11:00:00+00:00", "config": {"carry": True}}}
        publish_snapshot(fresh_database, self.temporary.name, first)
        publish_snapshot(fresh_database, self.temporary.name, second)
        with connect(fresh_database, readonly=True) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0], 2)

    def test_live_dashboard_never_mixes_preview_strengths_or_history(self):
        teams = [
            {
                "slug": slug, "name": values[0], "short": values[1], "code": values[2],
                "primary": values[3], "secondary": values[4], "variant": values[5],
            }
            for slug, values in CLUBS.items()
            if slug not in {"heidenheim", "stpauli", "wolfsburg"}
        ]
        snapshot = {
            "snapshot_id": "live-md1-test",
            "season": "2026/27",
            "matchday": 1,
            "published_at": "2026-07-29T17:00:00+00:00",
            "mode": "live",
            "model": {
                "id": "live-model-test",
                "created_at": "2026-07-29T16:00:00+00:00",
                "config": {"policy": "carry"},
            },
            "teams": teams,
            "fixtures": [{
                "id": "2627-01-fcb-vfb",
                "kickoff_utc": "2026-08-28T18:30:00+00:00",
                "home": "bayern",
                "away": "stuttgart",
                "probabilities": [.55, .25, .20],
            }],
            "strengths": [
                {"team": team["slug"], "matchday": 1, "attack": 40.123456789, "defense": 50.987654321}
                for team in teams
            ],
        }
        publish_snapshot(self.database, self.temporary.name, snapshot)

        payload = read_dashboard(self.database)
        self.assertEqual(payload["mode"], "live")
        self.assertEqual(len(payload["fixtures"]), 1)
        self.assertEqual(payload["history"], [])
        self.assertEqual(len(payload["strengths"]), 18)
        self.assertTrue(all(item["matchdays"] == [1] for item in payload["strengths"]))
        self.assertTrue(all(len(item["attack"]) == 1 for item in payload["strengths"]))


if __name__ == "__main__":
    unittest.main()
