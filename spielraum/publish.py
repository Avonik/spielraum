from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .artifacts import write_json_atomic
from .storage import transaction


REQUIRED_CLUB_FIELDS = {"slug", "name", "short", "code", "primary", "secondary", "variant"}


def _require(payload: dict[str, Any], field: str) -> Any:
    if field not in payload:
        raise ValueError(f"snapshot field missing: {field}")
    return payload[field]


def _validate_timestamp(value: str, field: str) -> None:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")


def validate_snapshot(payload: dict[str, Any]) -> None:
    for field in ("snapshot_id", "season", "matchday", "published_at", "model", "teams", "fixtures"):
        _require(payload, field)
    if payload.get("mode") not in {"preview", "live"}:
        raise ValueError("mode must be preview or live")
    _validate_timestamp(payload["published_at"], "published_at")
    if not 1 <= int(payload["matchday"]) <= 34:
        raise ValueError("matchday must be between 1 and 34")
    model = payload["model"]
    for field in ("id", "created_at", "config"):
        _require(model, field)
    _validate_timestamp(model["created_at"], "model.created_at")
    slugs = set()
    for team in payload["teams"]:
        missing = REQUIRED_CLUB_FIELDS - set(team)
        if missing:
            raise ValueError(f"team fields missing: {sorted(missing)}")
        if team["variant"] not in {"circle", "diamond", "oval", "shield"}:
            raise ValueError(f"invalid badge variant for {team['slug']}")
        slugs.add(team["slug"])
    for fixture in payload["fixtures"]:
        for field in ("id", "kickoff_utc", "home", "away", "probabilities"):
            _require(fixture, field)
        _validate_timestamp(fixture["kickoff_utc"], f"fixture {fixture['id']} kickoff_utc")
        if fixture["home"] not in slugs or fixture["away"] not in slugs:
            raise ValueError(f"unknown team in fixture {fixture['id']}")
        probabilities = [float(value) for value in fixture["probabilities"]]
        if len(probabilities) != 3 or any(value < 0 or value > 1 for value in probabilities):
            raise ValueError(f"invalid probabilities for fixture {fixture['id']}")
        if abs(sum(probabilities) - 1.0) >= 0.00001:
            raise ValueError(f"probabilities do not sum to one for fixture {fixture['id']}")


def publish_snapshot(database_path: str | Path, data_dir: str | Path, payload: dict[str, Any]) -> Path:
    """Validate, hash and publish one immutable model snapshot atomically."""
    validate_snapshot(payload)
    snapshot_id = payload["snapshot_id"]
    artifact_path = Path(data_dir).resolve() / "artifacts" / snapshot_id / "snapshot.json"
    artifact_sha = write_json_atomic(artifact_path, payload)
    model = payload["model"]

    try:
        with transaction(database_path) as connection:
            for team in payload["teams"]:
                connection.execute(
                    """INSERT INTO teams
                       (slug, display_name, short_name, code, primary_color, secondary_color, badge_variant)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(slug) DO UPDATE SET display_name=excluded.display_name,
                       short_name=excluded.short_name, code=excluded.code,
                       primary_color=excluded.primary_color, secondary_color=excluded.secondary_color,
                       badge_variant=excluded.badge_variant""",
                    (team["slug"], team["name"], team["short"], team["code"], team["primary"], team["secondary"], team["variant"]),
                )
            team_ids = {r["slug"]: r["id"] for r in connection.execute("SELECT id, slug FROM teams")}
            connection.execute(
                """INSERT INTO model_versions(id, created_at, git_sha, config_json, artifact_sha256)
                   VALUES (?, ?, ?, ?, ?)""",
                (model["id"], model["created_at"], model.get("git_sha"), json.dumps(model["config"], ensure_ascii=False, sort_keys=True), artifact_sha),
            )
            connection.execute(
                """INSERT INTO published_snapshots
                   (id, model_version_id, season, matchday, published_at, manifest_path, manifest_sha256, mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot_id, model["id"], payload["season"], int(payload["matchday"]), payload["published_at"], str(artifact_path), artifact_sha, payload["mode"]),
            )
            for fixture in payload["fixtures"]:
                connection.execute(
                    """INSERT OR IGNORE INTO fixtures
                       (id, season, matchday, kickoff_utc, home_team_id, away_team_id, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (fixture["id"], payload["season"], int(payload["matchday"]), fixture["kickoff_utc"],
                     team_ids[fixture["home"]], team_ids[fixture["away"]], fixture.get("status", "scheduled")),
                )
                stored = connection.execute(
                    "SELECT season, matchday, kickoff_utc, home_team_id, away_team_id FROM fixtures WHERE id = ?",
                    (fixture["id"],),
                ).fetchone()
                identity = (payload["season"], int(payload["matchday"]), fixture["kickoff_utc"], team_ids[fixture["home"]], team_ids[fixture["away"]])
                if tuple(stored) != identity:
                    raise ValueError(f"fixture identity changed after first publication: {fixture['id']}")
                connection.execute(
                    """INSERT INTO predictions
                       (fixture_id, snapshot_id, model_version_id, published_at, p_home, p_draw, p_away)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (fixture["id"], snapshot_id, model["id"], payload["published_at"], *fixture["probabilities"]),
                )
            for strength in payload.get("strengths", []):
                connection.execute(
                    """INSERT INTO team_strengths
                       (snapshot_id, team_id, season, matchday, attack_index, defense_index)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (snapshot_id, team_ids[strength["team"]], payload["season"], int(strength.get("matchday", payload["matchday"])),
                     float(strength["attack"]), float(strength["defense"])),
                )
            for placement in payload.get("placements", []):
                connection.execute(
                    """INSERT INTO placement_forecasts
                       (snapshot_id, team_id, median_rank, low_rank, high_rank, p_title, p_top4, p_relegation, simulations)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (snapshot_id, team_ids[placement["team"]], float(placement["median"]), int(placement["low"]), int(placement["high"]),
                     float(placement["title"]), float(placement["top4"]), float(placement["relegation"]), int(placement["simulations"])),
                )
            connection.executemany(
                """INSERT INTO metadata(key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                [("current_season", payload["season"]), ("current_matchday", str(payload["matchday"])), ("data_mode", payload["mode"])],
            )
    except Exception:
        artifact_path.unlink(missing_ok=True)
        try:
            artifact_path.parent.rmdir()
        except OSError:
            pass
        raise
    return artifact_path


def publish_file(database_path: str | Path, data_dir: str | Path, snapshot_path: str | Path) -> Path:
    payload = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    return publish_snapshot(database_path, data_dir, payload)


def sync_schedule(
    database_path: str | Path,
    teams: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
) -> int:
    """Upsert provider fixtures without changing an already-published identity."""
    for team in teams:
        missing = REQUIRED_CLUB_FIELDS - set(team)
        if missing:
            raise ValueError(f"team fields missing: {sorted(missing)}")
    with transaction(database_path) as connection:
        for team in teams:
            connection.execute(
                """INSERT INTO teams
                   (slug, display_name, short_name, code, primary_color, secondary_color, badge_variant)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(slug) DO UPDATE SET display_name=excluded.display_name,
                   short_name=excluded.short_name, code=excluded.code,
                   primary_color=excluded.primary_color, secondary_color=excluded.secondary_color,
                   badge_variant=excluded.badge_variant""",
                (team["slug"], team["name"], team["short"], team["code"], team["primary"], team["secondary"], team["variant"]),
            )
        team_ids = {row["slug"]: row["id"] for row in connection.execute("SELECT id, slug FROM teams")}
        for fixture in fixtures:
            for field in ("id", "season", "matchday", "kickoff_utc", "home", "away"):
                _require(fixture, field)
            _validate_timestamp(fixture["kickoff_utc"], f"fixture {fixture['id']} kickoff_utc")
            if fixture["home"] not in team_ids or fixture["away"] not in team_ids:
                raise ValueError(f"unknown team in fixture {fixture['id']}")
            status = fixture.get("status", "scheduled")
            if status not in {"scheduled", "live", "finished", "postponed"}:
                raise ValueError(f"invalid fixture status for {fixture['id']}")
            identity = (
                fixture["season"], int(fixture["matchday"]), fixture["kickoff_utc"],
                team_ids[fixture["home"]], team_ids[fixture["away"]],
            )
            stored = connection.execute(
                "SELECT season, matchday, kickoff_utc, home_team_id, away_team_id FROM fixtures WHERE id = ?",
                (fixture["id"],),
            ).fetchone()
            if stored is None:
                connection.execute(
                    """INSERT INTO fixtures
                       (id, season, matchday, kickoff_utc, home_team_id, away_team_id, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (fixture["id"], *identity, status),
                )
                continue
            if tuple(stored) != identity:
                has_prediction = connection.execute(
                    "SELECT 1 FROM predictions WHERE fixture_id = ? LIMIT 1", (fixture["id"],)
                ).fetchone()
                if has_prediction:
                    continue
                connection.execute(
                    """UPDATE fixtures SET season = ?, matchday = ?, kickoff_utc = ?,
                       home_team_id = ?, away_team_id = ?, status = ? WHERE id = ?""",
                    (*identity, status, fixture["id"]),
                )
            elif status != "finished":
                connection.execute("UPDATE fixtures SET status = ? WHERE id = ?", (status, fixture["id"]))
    return len(fixtures)


def record_results(database_path: str | Path, payload: list[dict[str, Any]], source: str) -> int:
    """Attach results separately; finished rows cannot later be rewritten."""
    with transaction(database_path) as connection:
        for result in payload:
            status = result.get("status", "finished")
            existing = connection.execute(
                "SELECT home_goals, away_goals, status FROM results WHERE fixture_id = ?",
                (result["fixture_id"],),
            ).fetchone()
            incoming_score = (int(result["home_goals"]), int(result["away_goals"]))
            if existing and existing["status"] == "finished":
                if (existing["home_goals"], existing["away_goals"]) != incoming_score:
                    raise ValueError(f"finished result changed for {result['fixture_id']}")
                continue
            connection.execute(
                """INSERT INTO results(fixture_id, home_goals, away_goals, status, observed_at, source)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(fixture_id) DO UPDATE SET home_goals=excluded.home_goals,
                   away_goals=excluded.away_goals, status=excluded.status,
                   observed_at=excluded.observed_at, source=excluded.source""",
                (result["fixture_id"], *incoming_score, status, result["observed_at"], source),
            )
            connection.execute("UPDATE fixtures SET status = ? WHERE id = ?", ("finished" if status == "finished" else "live", result["fixture_id"]))
    return len(payload)
