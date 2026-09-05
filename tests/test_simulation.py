from __future__ import annotations

import unittest
from types import SimpleNamespace

from spielraum.simulation import simulate_placements


class PlacementSimulationTests(unittest.TestCase):
    def test_outputs_valid_probabilities_for_all_teams(self):
        teams = [f"team-{index:02d}" for index in range(18)]
        matches = [
            SimpleNamespace(
                fixture_id=f"game-{index}", home_fd=teams[index], away_fd=teams[index + 1],
                finished=False, score=None,
            )
            for index in range(0, 18, 2)
        ]

        def lambdas(match):
            if match.home_fd == "team-00":
                return 10.0, 0.01, 10.0, 0.01, 0.75
            return 1.3, 1.1, 1.4, 1.0, 0.75

        result = simulate_placements(matches, teams=teams, lambdas_for_match=lambdas, simulations=2_000)
        self.assertEqual(len(result), 18)
        by_team = {row["team"]: row for row in result}
        self.assertGreater(by_team["team-00"]["title"], 0.90)
        for row in result:
            self.assertLessEqual(row["low"], row["high"])
            for field in ("title", "top4", "relegation"):
                self.assertGreaterEqual(row[field], 0.0)
                self.assertLessEqual(row[field], 1.0)


if __name__ == "__main__":
    unittest.main()
