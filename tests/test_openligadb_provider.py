from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spielraum.providers.openligadb import OpenLigaMatch, next_unfinished_matchday, team_payload
from spielraum.publish import record_results, sync_schedule
from spielraum.seed import seed_preview
from spielraum.storage import connect, initialize


def api_match(*, finished: bool = False, kickoff: str = "2026-08-28T18:30:00Z") -> dict:
    return {
        "matchID": 83156,
        "leagueSeason": 2026,
        "matchDateTimeUTC": kickoff,
        "matchIsFinished": finished,
        "group": {"groupOrderID": 1},
        "team1": {"teamName": "FC Bayern München"},
        "team2": {"teamName": "VfB Stuttgart"},
        "matchResults": ([
            {"resultTypeID": 1, "resultOrderID": 1, "pointsTeam1": 1, "pointsTeam2": 0},
            {"resultTypeID": 2, "resultOrderID": 2, "pointsTeam1": 2, "pointsTeam2": 1},
        ] if finished else []),
    }


class OpenLigaProviderTests(unittest.TestCase):
    def test_scheduled_match_maps_to_stable_portable_fixture(self):
        match = OpenLigaMatch.from_api(api_match())
        self.assertEqual(match.fixture_id, "2627-01-fcb-vfb")
        self.assertEqual(match.provider_id, 83156)
        self.assertEqual(match.home_fd, "Bayern Munich")
        self.assertEqual(match.kickoff_utc, "2026-08-28T18:30:00+00:00")
        self.assertIsNone(match.score)
        self.assertEqual(match.fixture_payload()["season"], "2026/27")

    def test_finished_match_uses_end_result_not_halftime(self):
        match = OpenLigaMatch.from_api(api_match(finished=True))
        self.assertEqual(match.score, (2, 1))
        result = match.result_payload("2026-08-28T21:00:00+00:00")
        self.assertEqual((result["home_goals"], result["away_goals"]), (2, 1))

    def test_next_unfinished_matchday(self):
        finished = OpenLigaMatch.from_api(api_match(finished=True))
        pending = OpenLigaMatch.from_api({
            **api_match(), "matchID": 90000,
            "group": {"groupOrderID": 2},
            "team1": {"teamName": "Borussia Dortmund"},
            "team2": {"teamName": "Hamburger SV"},
        })
        self.assertEqual(next_unfinished_matchday([finished, pending]), 2)

    def test_schedule_sync_coexists_with_seeded_preview_and_records_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "spielraum.sqlite3"
            initialize(database)
            seed_preview(database)
            match = OpenLigaMatch.from_api(api_match(finished=True))
            teams = [team_payload("bayern"), team_payload("stuttgart")]
            self.assertEqual(sync_schedule(database, teams, [match.fixture_payload()]), 1)
            self.assertEqual(record_results(database, [match.result_payload()], "OpenLigaDB (ODbL)"), 1)
            with connect(database, readonly=True) as connection:
                fixture = connection.execute(
                    "SELECT kickoff_utc, status FROM fixtures WHERE id = ?", (match.fixture_id,)
                ).fetchone()
                result = connection.execute(
                    "SELECT home_goals, away_goals FROM results WHERE fixture_id = ?", (match.fixture_id,)
                ).fetchone()
            self.assertEqual(tuple(fixture), ("2026-08-28T18:30:00+00:00", "finished"))
            self.assertEqual(tuple(result), (2, 1))


if __name__ == "__main__":
    unittest.main()
