from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

from v2.real_xg import UNDERSTAT_OUTPUT_COLUMNS, fetch_understat_xg


class _Reader:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def read_schedule(self) -> pd.DataFrame:
        return self.frame


class RealXgTests(unittest.TestCase):
    def _fetch(self, frame: pd.DataFrame) -> pd.DataFrame:
        self.reader_kwargs = {}

        def understat(**kwargs):
            self.reader_kwargs = kwargs
            return _Reader(frame)

        fake = types.SimpleNamespace(Understat=understat)
        with patch.dict(sys.modules, {"soccerdata": fake}):
            return fetch_understat_xg([2026], verbose=False)

    def test_unpublished_season_returns_an_empty_typed_frame(self):
        result = self._fetch(pd.DataFrame())
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), UNDERSTAT_OUTPUT_COLUMNS)
        self.assertTrue(self.reader_kwargs["no_cache"])

    def test_schema_without_is_result_uses_rows_with_xg(self):
        frame = pd.DataFrame([
            {
                "date": "2026-08-28",
                "home_team": "Bayern Munich",
                "away_team": "VfB Stuttgart",
                "home_xg": "2.4",
                "away_xg": "0.7",
            },
            {
                "date": "2026-09-04",
                "home_team": "VfB Stuttgart",
                "away_team": "FC Cologne",
                "home_xg": None,
                "away_xg": None,
            },
        ])
        result = self._fetch(frame)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["start_year"], 2026)
        self.assertAlmostEqual(result.iloc[0]["home_xg"], 2.4)


if __name__ == "__main__":
    unittest.main()
