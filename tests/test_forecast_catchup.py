from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from spielraum.config import Settings
from spielraum.forecasting import matchday_view, next_pending_matchday
from spielraum.providers.openligadb import FD_NAMES, OpenLigaMatch, team_payload
from spielraum.publish import publish_snapshot, record_results, sync_schedule
from spielraum.scheduler import _mark_attempt, tick
from spielraum.storage import connect, initialize, read_dashboard, transaction


def season_matches(completed=8):
    slugs = [slug for slug in FD_NAMES if slug not in {"heidenheim", "stpauli", "wolfsburg"}]
    rotation = slugs[:]
    matches = []
    for day in range(1, 35):
        for index in range(9):
            home, away = rotation[index], rotation[-index - 1]
            kickoff = datetime(2026, 11, 6, 19, 30, tzinfo=UTC) + timedelta(weeks=day - 9, hours=index)
            matches.append(OpenLigaMatch(
                fixture_id=f"test-{day}-{index}", provider_id=day * 10 + index,
                season_start=2026, matchday=day, kickoff_utc=kickoff.isoformat(),
                home_slug=home, away_slug=away, home_fd=FD_NAMES[home], away_fd=FD_NAMES[away],
                finished=day <= completed, score=(2, 1) if day <= completed else None,
            ))
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    return matches


class ForecastCatchupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.settings = Settings(data_dir=root, database_path=root / "test.sqlite3")
        initialize(self.settings.database_path)

    def prepare_queue(self, completed=8):
        matches = season_matches(completed)
        slugs = sorted({match.home_slug for match in matches})
        sync_schedule(self.settings.database_path, [team_payload(slug) for slug in slugs], [match.fixture_payload() for match in matches])
        for day in range(1, 9):
            self.publish_round(day)

    def publish_round(self, day):
        with transaction(self.settings.database_path) as c:
            c.execute("INSERT INTO model_versions(id, created_at, config_json) VALUES (?, ?, '{}')", (f"model-{day}", "2026-10-01T00:00:00+00:00"))
            c.execute("""INSERT INTO published_snapshots(id, model_version_id, season, matchday, published_at, mode, manifest_sha256)
                         VALUES (?, ?, '2026/27', ?, ?, 'live', 'verified')""",
                      (f"snapshot-{day}", f"model-{day}", day, "2026-10-01T00:00:00+00:00"))

    def test_saturday_outage_still_has_a_pending_forecast(self):
        self.prepare_queue()
        self.assertEqual(next_pending_matchday(self.settings, datetime(2026, 11, 7, 11, tzinfo=UTC)), 9)

    def test_monday_must_process_missed_round_before_new_round(self):
        self.prepare_queue(completed=9)
        now = datetime(2026, 11, 9, 12, tzinfo=UTC)
        self.assertEqual(next_pending_matchday(self.settings, now), 9)
        self.publish_round(9)
        self.assertEqual(next_pending_matchday(self.settings, now), 10)
        self.publish_round(10)
        self.assertIsNone(next_pending_matchday(self.settings, now))

    def test_queue_catches_up_in_order_in_one_tick(self):
        self.prepare_queue(completed=9)
        now = datetime(2026, 11, 9, 12, tzinfo=UTC)
        with patch("spielraum.scheduler._now", return_value=now):
            _mark_attempt(self.settings, "understat", "success")
            _mark_attempt(self.settings, "results", "success")
            def run(settings, job, *, matchday):
                self.publish_round(matchday)
                return "success"
            with patch("spielraum.scheduler.run_job", side_effect=run) as job:
                tick(self.settings)
            self.assertEqual([call.kwargs["matchday"] for call in job.call_args_list], [9, 10])

    def test_missing_xg_blocks_later_round_and_retries_on_saturday(self):
        self.prepare_queue(completed=9)
        now = datetime(2026, 11, 14, 12, tzinfo=UTC)
        with patch("spielraum.scheduler._now", return_value=now):
            _mark_attempt(self.settings, "understat", "success")
            _mark_attempt(self.settings, "results", "success")
            with patch("spielraum.scheduler.run_job", return_value="deferred") as job:
                tick(self.settings)
                job.assert_called_once_with(self.settings, "model", matchday=9)
                job.reset_mock()
                tick(self.settings)
                job.assert_not_called()

    def test_recovery_triggers_immediate_retry_before_two_hours(self):
        self.prepare_queue()
        now = datetime(2026, 11, 7, 12, tzinfo=UTC)
        with patch("spielraum.scheduler._now", return_value=now - timedelta(minutes=31)):
            _mark_attempt(self.settings, "understat", "failed")
            _mark_attempt(self.settings, "model", "failed")
        with patch("spielraum.scheduler._now", return_value=now):
            _mark_attempt(self.settings, "results", "success")
            with patch("spielraum.scheduler.run_job", side_effect=["success", "deferred"]) as job:
                tick(self.settings)
                self.assertEqual(job.call_args_list[-1].kwargs, {"matchday": 9})

    def test_target_and_future_scores_are_removed_even_when_known(self):
        matches = season_matches(completed=10)
        view, cutoff = matchday_view(matches, 9)
        self.assertEqual(sum(match.finished for match in view), 72)
        self.assertTrue(all(not match.finished and match.score is None for match in view if match.matchday >= 9))
        self.assertTrue(all(datetime.fromisoformat(match.kickoff_utc) <= cutoff for match in view if match.finished))
        self.assertTrue(next(match for match in matches if match.matchday == 9).finished)

    def test_delayed_prior_fixture_cannot_leak_across_the_cutoff(self):
        matches = season_matches(completed=10)
        target_kickoff = next(match.kickoff_utc for match in matches if match.matchday == 9)
        matches[0] = replace(matches[0], kickoff_utc=target_kickoff)
        view, _ = matchday_view(matches, 9)
        self.assertFalse(view[0].finished)
        self.assertIsNone(view[0].score)

    def test_model_training_and_placement_simulation_share_the_boundary(self):
        from spielraum.adapters import model_v2
        matches = season_matches(completed=10)
        xg = pd.DataFrame([
            {"home_team": model_v2._FD_TO_US[match.home_fd], "away_team": model_v2._FD_TO_US[match.away_fd],
             "home_xg": 1.5 if match.matchday < 9 else 99.0, "away_xg": 0.7 if match.matchday < 9 else 99.0}
            for match in matches if match.finished
        ])
        teams = {match.home_fd for match in matches}
        streams = {stream: {team: (0.0, 0.0) for team in teams} for stream in ("fresh", "carry")}
        with patch.object(model_v2, "fetch_understat_xg", return_value=xg), \
             patch.object(model_v2, "_target_market_values", return_value=({}, "2026-08-15")), \
             patch.object(model_v2, "_load_history", return_value=pd.DataFrame()), \
             patch.object(model_v2, "_load_or_fit_endpoint", return_value=None), \
             patch.object(model_v2, "_fit_streams", return_value=(streams, 1.4, 1.1)) as fit, \
             patch.object(model_v2, "_probabilities", return_value=(0.5, 0.3, 0.2)), \
             patch.object(model_v2, "simulate_placements", return_value=[]) as simulate:
            snapshot, status = model_v2.build_snapshot(matches, settings=self.settings, simulations=100,
                n_iter=10, burnin=2, thin=1, target_matchday=9)
            prefix = fit.call_args.args[1].copy()
            simulated = simulate.call_args.args[0]
            later, _ = model_v2.build_snapshot(matches, settings=self.settings, simulations=100,
                n_iter=10, burnin=2, thin=1, target_matchday=10)
            later_prefix = fit.call_args.args[1]
        self.assertTrue(status["xg_complete"])
        self.assertEqual(len(prefix), 72)
        self.assertTrue((prefix["xG_home"] == 1.5).all())
        self.assertEqual(len(snapshot["fixtures"]), 9)
        self.assertEqual(snapshot["model"]["config"]["training_matchday_max"], 8)
        self.assertTrue(all(not match.finished and match.score is None for match in simulated if match.matchday >= 9))
        self.assertEqual(len(later_prefix), 81)
        self.assertEqual(later["model"]["config"]["training_matchday_max"], 9)
        self.assertEqual(int((later_prefix["xG_home"] == 99.0).sum()), 9)

    def late_snapshot(self):
        return {
            "snapshot_id": "late-nine", "model": {"id": "late-model", "created_at": "2026-11-07T11:00:00+00:00",
                "config": {"training_matchday_max": 8, "data_cutoff": "2026-11-06T19:29:59+00:00"}},
            "season": "2026/27", "matchday": 9, "published_at": "2026-11-07T11:00:00+00:00", "mode": "live",
            "teams": [team_payload("bayern"), team_payload("dortmund")],
            "fixtures": [
                {"id": "friday", "kickoff_utc": "2026-11-06T19:30:00+00:00", "home": "bayern", "away": "dortmund", "probabilities": [0.5, 0.3, 0.2]},
                {"id": "saturday", "kickoff_utc": "2026-11-07T14:30:00+00:00", "home": "dortmund", "away": "bayern", "probabilities": [0.3, 0.3, 0.4]},
            ],
        }

    def test_mixed_round_publishes_atomically_with_real_timestamps(self):
        snapshot = self.late_snapshot()
        publish_snapshot(self.settings.database_path, self.settings.data_dir, snapshot)
        record_results(self.settings.database_path, [{"fixture_id": "friday", "home_goals": 2, "away_goals": 1,
            "status": "finished", "observed_at": "2026-11-06T21:30:00+00:00"}], "test")
        dashboard = read_dashboard(self.settings.database_path)
        self.assertEqual(len(dashboard["fixtures"]), 2)
        self.assertEqual(dashboard["history"][0]["probabilities"], [0.5, 0.3, 0.2])
        with connect(self.settings.database_path, readonly=True) as c:
            self.assertEqual(c.execute("SELECT fixture_id FROM predictions").fetchone()[0], "saturday")
            late = c.execute("SELECT * FROM reconstructed_predictions").fetchone()
            self.assertEqual(late["fixture_id"], "friday")
            self.assertEqual(late["computed_at"], snapshot["published_at"])

    def test_reconstructed_forecasts_cannot_be_modified(self):
        publish_snapshot(self.settings.database_path, self.settings.data_dir, self.late_snapshot())
        with connect(self.settings.database_path) as c:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                c.execute("UPDATE reconstructed_predictions SET p_home = p_home")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                c.execute("DELETE FROM reconstructed_predictions")

    def test_original_forecasts_take_precedence_over_later_recomputations(self):
        earlier = copy.deepcopy(self.late_snapshot())
        earlier.update(snapshot_id="early-nine", published_at="2026-11-05T10:00:00+00:00")
        earlier["model"]["id"] = "early-model"
        earlier["fixtures"][0]["probabilities"] = [0.2, 0.3, 0.5]
        publish_snapshot(self.settings.database_path, self.settings.data_dir, earlier)
        publish_snapshot(self.settings.database_path, self.settings.data_dir, self.late_snapshot())
        record_results(self.settings.database_path, [{"fixture_id": "friday", "home_goals": 2, "away_goals": 1,
            "status": "finished", "observed_at": "2026-11-06T21:30:00+00:00"}], "test")
        self.assertEqual(read_dashboard(self.settings.database_path)["history"][0]["probabilities"], [0.2, 0.3, 0.5])

    def test_unsafe_late_snapshot_is_rejected(self):
        for cutoff in (None, "2026-11-07T10:00:00+00:00"):
            snapshot = self.late_snapshot()
            snapshot["model"]["config"]["data_cutoff"] = cutoff
            with self.assertRaisesRegex(ValueError, "training"):
                publish_snapshot(self.settings.database_path, self.settings.data_dir, snapshot)
        with connect(self.settings.database_path, readonly=True) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM published_snapshots").fetchone()[0], 0)
