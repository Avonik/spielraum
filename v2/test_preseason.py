from __future__ import annotations

import unittest
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from model import build_league, compose_initial_prior_means
from market_value import DEFAULT_CSV
from preseason import (
    PreseasonState,
    predict_preseason_fixtures,
    previous_season_label,
    standardized_market_value_signal,
    shrunk_goal_levels,
)
from preseason_backtest import cosine_taper_weights
from season_transition_v2 import (
    EndpointPosterior,
    build_fresh_and_carry_priors,
    cosine_goal_level_prior,
    recommended_carry_weight,
    recommended_transition_probabilities,
)


class PreseasonTests(unittest.TestCase):
    def test_previous_season_label(self):
        self.assertEqual(previous_season_label("2026/27"), "2025/26")

    def test_composed_priors_are_centered_and_separate(self):
        attack, defense, _ = compose_initial_prior_means(
            ["A", "B"],
            team_strength_priors={"A": (0.4, 0.1), "B": (-0.2, -0.1)},
            carry_weight=0.75,
        )
        self.assertAlmostEqual(float(attack.sum() + defense.sum()), 0.0)
        self.assertNotAlmostEqual(float(attack[0]), float(defense[0]))

    def test_market_value_change_signal_is_centered(self):
        signal = standardized_market_value_signal(
            {"A": 120.0, "B": 80.0, "C": 100.0}, ["A", "B", "C"],
            previous_values={"A": 100.0, "B": 100.0, "C": 100.0},
        )
        self.assertGreater(signal["A"], signal["C"])
        self.assertGreater(signal["C"], signal["B"])
        self.assertAlmostEqual(sum(signal.values()), 0.0, places=12)

    def test_market_value_default_cache_is_module_relative(self):
        self.assertTrue(DEFAULT_CSV.is_file())

    def test_goal_level_shrinkage_uses_historical_pseudo_matches(self):
        frame = pd.DataFrame({
            "Season": ["2022/23", "2022/23", "2023/24"],
            "FTHG": [2, 2, 0], "FTAG": [1, 1, 4],
        })
        prefix = frame[frame["Season"] == "2023/24"]
        c_home, c_away = shrunk_goal_levels(
            frame, "2023/24", prefix, use_xg=False, prior_matches=3.0,
            n_seasons=1)
        self.assertAlmostEqual(float(np.exp(c_home)), 1.5)
        self.assertAlmostEqual(float(np.exp(c_away)), 1.75)

    def test_zero_goal_level_prior_reproduces_current_prefix(self):
        frame = pd.DataFrame({
            "Season": ["2022/23", "2023/24"],
            "FTHG": [2, 1], "FTAG": [1, 3],
        })
        prefix = frame[frame["Season"] == "2023/24"]
        c_home, c_away = shrunk_goal_levels(
            frame, "2023/24", prefix, use_xg=False, prior_matches=0.0,
            n_seasons=1)
        self.assertAlmostEqual(float(np.exp(c_home)), 1.0)
        self.assertAlmostEqual(float(np.exp(c_away)), 3.0)

    def test_goal_level_prior_cosine_fade_reaches_zero(self):
        self.assertAlmostEqual(cosine_goal_level_prior(144.0, 0, 90.0), 144.0)
        self.assertAlmostEqual(cosine_goal_level_prior(144.0, 45, 90.0), 72.0)
        self.assertEqual(cosine_goal_level_prior(144.0, 90, 90.0), 0.0)
        self.assertEqual(cosine_goal_level_prior(144.0, 120, 90.0), 0.0)

    def test_recommended_carry_weight_fades_from_md12_to_md18(self):
        weights = recommended_carry_weight(np.array([1, 12, 15, 18, 34]))
        np.testing.assert_allclose(weights, [1.0, 1.0, 0.5, 0.0, 0.0])

    def test_recommended_transition_blends_probability_streams(self):
        frame = pd.DataFrame({
            "matchday": [12, 15, 18],
            "p_home_fresh_v2": [0.2, 0.2, 0.2],
            "p_draw_fresh_v2": [0.3, 0.3, 0.3],
            "p_away_fresh_v2": [0.5, 0.5, 0.5],
            "p_home_carry_v2": [0.6, 0.6, 0.6],
            "p_draw_carry_v2": [0.3, 0.3, 0.3],
            "p_away_carry_v2": [0.1, 0.1, 0.1],
        })
        probabilities = recommended_transition_probabilities(frame)
        np.testing.assert_allclose(probabilities, [
            [0.6, 0.3, 0.1], [0.4, 0.3, 0.3], [0.2, 0.3, 0.5],
        ])

    def test_cosine_taper_reaches_zero_without_jump(self):
        weights = cosine_taper_weights(np.arange(1, 35), 30)
        self.assertAlmostEqual(float(weights[0]), 1.0)
        self.assertGreater(float(weights[28]), 0.0)
        self.assertTrue(np.all(weights[29:] == 0.0))
        self.assertTrue(np.all(np.diff(weights) <= 0.0))

    def test_build_league_uses_overrides_and_team_variances(self):
        frame = pd.DataFrame({
            "Date": pd.to_datetime(["2024-08-01", "2024-08-02"]),
            "HomeTeam": ["A", "B"], "AwayTeam": ["B", "A"],
            "FTHG": [1, 0], "FTAG": [0, 2],
        })
        league = build_league(
            frame,
            team_strength_priors={"A": (0.3, 0.2), "B": (-0.1, -0.2)},
            carry_weight=0.5,
            initial_prior_var={"A": 0.1, "B": 0.2},
            c_x_override=0.25,
            c_y_override=-0.10,
            early_process_multiplier=2.0,
            early_process_half_life=6.0,
        )
        self.assertAlmostEqual(league.c_x, 0.25)
        self.assertAlmostEqual(league.c_y, -0.10)
        np.testing.assert_allclose(league.init_prior_var, [0.1, 0.2])
        self.assertEqual(league.early_process_multiplier, 2.0)

    def test_separate_attack_and_defense_prior_variances(self):
        frame = pd.DataFrame({
            "Date": pd.to_datetime(["2024-08-01"]),
            "HomeTeam": ["A"], "AwayTeam": ["B"],
            "FTHG": [1], "FTAG": [1],
        })
        league = build_league(
            frame,
            initial_prior_var=0.5,
            initial_attack_prior_var={"A": 0.1, "B": 0.2},
            initial_defense_prior_var={"A": 0.3, "B": 0.4},
        )
        np.testing.assert_allclose(league.init_attack_prior_var, [0.1, 0.2])
        np.testing.assert_allclose(league.init_defense_prior_var, [0.3, 0.4])

    def test_promoted_team_has_identical_fresh_and_carry_prior(self):
        endpoint = EndpointPosterior(
            source_season="2024/25",
            moments={"A": (0.4, 0.02, -0.2, 0.03)},
            last_match_dates={"A": pd.Timestamp("2025-05-17")},
        )
        priors = build_fresh_and_carry_priors(
            ["A", "B"],
            {"A": pd.Timestamp("2025-08-23"),
             "B": pd.Timestamp("2025-08-24")},
            endpoint,
            {"A": 200.0, "B": 100.0},
        )
        self.assertEqual(priors["fresh"]["means"]["B"],
                         priors["carry"]["means"]["B"])
        self.assertEqual(priors["fresh"]["attack_var"]["B"],
                         priors["carry"]["attack_var"]["B"])
        self.assertNotEqual(priors["fresh"]["means"]["A"],
                            priors["carry"]["means"]["A"])

    def test_preseason_prediction_is_a_probability_vector(self):
        state = PreseasonState(
            target_season="2026/27", source_season="2025/26",
            teams=["A", "B"],
            source_strengths={"A": (0.3, 0.2), "B": (-0.2, -0.1)},
            carried_teams=["A", "B"], new_teams=[], c_x=0.3, c_y=0.0,
        )
        pred = predict_preseason_fixtures(
            pd.DataFrame({"HomeTeam": ["A"], "AwayTeam": ["B"]}), state)
        self.assertAlmostEqual(float(pred.loc[0, ["p_home", "p_draw", "p_away"]].sum()),
                               1.0, places=10)


if __name__ == "__main__":
    unittest.main()
