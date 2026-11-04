from __future__ import annotations

import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from spielraum.adapters.understat_status import check_availability


class UnderstatStatusTests(unittest.TestCase):
    def check_with(self, reader):
        factory = Mock(return_value=reader)
        with patch.dict(sys.modules, {"soccerdata": SimpleNamespace(Understat=factory)}):
            result = check_availability()
        factory.assert_called_once()
        self.assertTrue(factory.call_args.kwargs["no_cache"])
        self.assertTrue(factory.call_args.kwargs["no_store"])
        return result

    def test_valid_xg_feed_is_available(self):
        reader = Mock()
        reader.read_schedule.return_value = SimpleNamespace(columns=["home_xg", "away_xg"])
        self.assertEqual(self.check_with(reader), {"available": True})

    def test_http_200_holding_page_is_unavailable(self):
        reader = Mock()
        reader.read_schedule.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
        self.assertFalse(self.check_with(reader)["available"])

    def test_network_outage_is_unavailable(self):
        reader = Mock()
        reader.read_schedule.side_effect = TimeoutError("connection timed out")
        self.assertFalse(self.check_with(reader)["available"])

    def test_feed_without_xg_is_unavailable(self):
        reader = Mock()
        reader.read_schedule.return_value = SimpleNamespace(columns=["home_team", "away_team"])
        self.assertFalse(self.check_with(reader)["available"])
