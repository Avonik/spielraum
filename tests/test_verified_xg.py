from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from spielraum.adapters.research_xg import parse_report
from spielraum.config import Settings
from spielraum.verified_xg import read_verified_xg


class VerifiedXgTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "cache").mkdir()
        self.settings = Settings(data_dir=self.root, database_path=self.root / "test.sqlite3")
        self.match = SimpleNamespace(fixture_id="past", finished=True, score=(2, 1),
            home_slug="bayern", away_slug="stuttgart", home_fd="Bayern Munich", away_fd="Stuttgart",
            kickoff_utc="2026-10-31T14:30:00+00:00")
        self.record = {"fixture_id": "past", "home": "bayern", "away": "stuttgart",
            "kickoff_utc": self.match.kickoff_utc, "home_goals": 2, "away_goals": 1,
            "home_xg": 1.7, "away_xg": 0.8, "source": "Bundesliga Match Facts",
            "source_url": "https://www.bundesliga.com/report", "source_sha256": "abc"}

    def write(self, records):
        (self.root / "cache/verified-xg-2026-27.json").write_text(json.dumps({
            "format": 1, "season": "2026/27", "records": records}))

    def test_target_and_future_records_do_not_enter_the_training_inputs(self):
        self.write([self.record, {"fixture_id": "future", "home_xg": 999}])
        self.assertEqual(list(read_verified_xg(self.root, [self.match])), ["past"])
        self.match.finished = False
        self.assertEqual(read_verified_xg(self.root, [self.match]), {})

    def test_wrong_identity_score_and_invalid_values_are_rejected(self):
        for changed in [{"home": "stuttgart"}, {"home_goals": 3}, {"home_xg": -1},
                        {"home_xg": float("nan")}, {"source_url": ""}, {"source_sha256": ""}]:
            self.write([{**self.record, **changed}])
            with self.assertRaises(ValueError):
                read_verified_xg(self.root, [self.match])

    def test_complete_verified_data_works_without_contacting_understat(self):
        from spielraum.adapters import model_v2
        self.write([self.record])
        with patch.object(model_v2, "fetch_understat_xg", side_effect=TimeoutError) as fetch:
            frame, missing = model_v2._current_xg([self.match], self.settings)
        fetch.assert_not_called()
        self.assertEqual(missing, [])
        self.assertEqual(frame.iloc[0]["xG_home"], 1.7)
        self.assertEqual(frame.iloc[0]["xg_source"], "Bundesliga Match Facts")

    def test_partial_verified_data_never_substitutes_missing_xg(self):
        from spielraum.adapters import model_v2
        self.write([self.record])
        missing_match = SimpleNamespace(**{**vars(self.match), "fixture_id": "missing"})
        with patch.object(model_v2, "fetch_understat_xg", side_effect=TimeoutError):
            frame, missing = model_v2._current_xg([self.match, missing_match], self.settings)
        self.assertEqual(len(frame), 1)
        self.assertEqual(missing, ["missing"])

    def test_parser_uses_final_facts_and_accepts_decimal_comma(self):
        article = {"datePublished": "2026-10-31T18:00:00Z", "articleBody":
            "At half time xGoals: Bayern Munich 0.4 - Stuttgart 0.2. "
            "Bundesliga Match Facts\txGoals: Bayern Munich 1,70 - VfB Stuttgart 0,80\tFastest player: someone"}
        html = '<script type="application/ld+json">' + json.dumps(article) + '</script>'
        result = parse_report(html)
        self.assertEqual((result["home"], result["away"]), ("bayern", "stuttgart"))
        self.assertEqual((result["home_xg"], result["away_xg"]), (1.7, 0.8))

    def test_parser_rejects_holding_pages_and_half_time_only_reports(self):
        for html in ['<html>We will come back soon</html>', '<script type="application/ld+json">' + json.dumps({
            "articleBody": "xGoals: Bayern Munich 1.0 - Stuttgart 0.4", "datePublished": "2026-10-31"}) + '</script>']:
            with self.assertRaises(ValueError):
                parse_report(html)

    def test_club_number_is_never_parsed_as_xg(self):
        article = {"datePublished": "2026-10-31T18:00:00Z", "articleBody":
            "Bundesliga Match Facts\txGoals: Borussia Mönchengladbach 1,20 - SC Paderborn 07 0,78\tFastest player: someone"}
        html = '<script type="application/ld+json">' + json.dumps(article) + '</script>'
        result = parse_report(html)
        self.assertEqual(result["away"], "paderborn")
        self.assertEqual(result["away_xg"], 0.78)
