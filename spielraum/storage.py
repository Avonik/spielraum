from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class ClosingConnection(sqlite3.Connection):
    """sqlite3 context manager that also releases Windows file handles."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(path: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    db_path = Path(path).resolve()
    if readonly:
        connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, factory=ClosingConnection)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if not readonly:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
    return connection


def initialize(path: str | Path) -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with connect(path) as connection:
        connection.executescript(schema)


@contextmanager
def transaction(path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _club(row: sqlite3.Row, prefix: str) -> dict[str, str]:
    return {
        "name": row[f"{prefix}_name"],
        "short": row[f"{prefix}_short"],
        "code": row[f"{prefix}_code"],
        "primary": row[f"{prefix}_primary"],
        "secondary": row[f"{prefix}_secondary"],
        "variant": row[f"{prefix}_variant"],
    }


_TEAM_JOIN = """
JOIN teams home ON home.id = f.home_team_id
JOIN teams away ON away.id = f.away_team_id
"""
_TEAM_SELECT = """
home.display_name AS home_name, home.short_name AS home_short,
home.code AS home_code, home.primary_color AS home_primary,
home.secondary_color AS home_secondary, home.badge_variant AS home_variant,
away.display_name AS away_name, away.short_name AS away_short,
away.code AS away_code, away.primary_color AS away_primary,
away.secondary_color AS away_secondary, away.badge_variant AS away_variant
"""


def read_dashboard(path: str | Path) -> dict[str, Any]:
    with connect(path, readonly=True) as connection:
        meta = {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM metadata")}
        season = meta.get("current_season", "2026/27")
        matchday = int(meta.get("current_matchday", "1"))
        snapshot = connection.execute(
            "SELECT id, published_at, mode FROM published_snapshots WHERE season = ? ORDER BY published_at DESC LIMIT 1",
            (season,),
        ).fetchone()

        fixtures = [] if snapshot is None else connection.execute(
            f"""
            SELECT f.id, f.kickoff_utc, {_TEAM_SELECT}, p.p_home, p.p_draw, p.p_away
            FROM fixtures f {_TEAM_JOIN}
            JOIN predictions p ON p.fixture_id = f.id AND p.snapshot_id = ?
            WHERE f.season = ? AND f.matchday = ?
            ORDER BY f.kickoff_utc, f.id
            """,
            (snapshot["id"], season, matchday),
        ).fetchall()
        fixture_payload = [
            {
                "id": row["id"],
                "kickoff": row["kickoff_utc"],
                "home": _club(row, "home"),
                "away": _club(row, "away"),
                "probabilities": [row["p_home"], row["p_draw"], row["p_away"]],
            }
            for row in fixtures
            if row["p_home"] is not None
        ]

        include_demo = snapshot is not None and snapshot["mode"] == "preview"
        history = connection.execute(
            f"""
            SELECT f.id, f.season, f.matchday, f.kickoff_utc, {_TEAM_SELECT},
                   p.p_home, p.p_draw, p.p_away, r.home_goals, r.away_goals
            FROM fixtures f {_TEAM_JOIN}
            JOIN results r ON r.fixture_id = f.id AND r.status = 'finished'
            JOIN predictions p ON p.id = (
                SELECT p2.id FROM predictions p2
                JOIN published_snapshots ps2 ON ps2.id = p2.snapshot_id
                WHERE p2.fixture_id = f.id AND datetime(p2.published_at) < datetime(f.kickoff_utc)
                  AND (? = 1 OR (ps2.mode = 'live' AND ps2.manifest_sha256 IS NOT NULL))
                ORDER BY p2.published_at DESC LIMIT 1
            )
            ORDER BY f.kickoff_utc DESC LIMIT 60
            """,
            (1 if include_demo else 0,),
        ).fetchall()
        history_payload = []
        for row in history:
            actual = "H" if row["home_goals"] > row["away_goals"] else "A" if row["away_goals"] > row["home_goals"] else "D"
            probs = [row["p_home"], row["p_draw"], row["p_away"]]
            predicted = ("H", "D", "A")[max(range(3), key=probs.__getitem__)]
            history_payload.append({
                "id": row["id"], "season": row["season"], "matchday": row["matchday"],
                "kickoff": row["kickoff_utc"],
                "home": _club(row, "home"), "away": _club(row, "away"),
                "probabilities": probs,
                "score": [row["home_goals"], row["away_goals"]],
                "outcome": actual, "hit": actual == predicted,
            })

        strengths_payload: list[dict[str, Any]] = []
        for team in connection.execute("SELECT * FROM teams ORDER BY display_name"):
            if include_demo and snapshot is not None:
                points = connection.execute(
                    """SELECT matchday, attack_index, defense_index FROM team_strengths
                       WHERE snapshot_id = ? AND team_id = ? ORDER BY matchday""",
                    (snapshot["id"], team["id"]),
                ).fetchall()
            else:
                candidates = connection.execute(
                    """SELECT ts.matchday, ts.attack_index, ts.defense_index, ps.published_at
                       FROM team_strengths ts
                       JOIN published_snapshots ps ON ps.id = ts.snapshot_id
                       WHERE ts.season = ? AND ts.team_id = ? AND ps.mode = 'live'
                         AND ps.manifest_sha256 IS NOT NULL
                       ORDER BY ps.published_at DESC""",
                    (season, team["id"]),
                ).fetchall()
                latest_by_matchday = {}
                for point in candidates:
                    latest_by_matchday.setdefault(int(point["matchday"]), point)
                points = [latest_by_matchday[key] for key in sorted(latest_by_matchday)[-8:]]
            if points:
                strengths_payload.append({
                    "club": {
                        "name": team["display_name"], "short": team["short_name"], "code": team["code"],
                        "primary": team["primary_color"], "secondary": team["secondary_color"],
                        "variant": team["badge_variant"],
                    },
                    "matchdays": [p["matchday"] for p in points],
                    "attack": [p["attack_index"] for p in points],
                    "defense": [p["defense_index"] for p in points],
                })

        placements_payload: list[dict[str, Any]] = []
        if snapshot:
            rows = connection.execute(
                """SELECT pf.*, t.display_name, t.short_name, t.code, t.primary_color,
                          t.secondary_color, t.badge_variant
                   FROM placement_forecasts pf JOIN teams t ON t.id = pf.team_id
                   WHERE pf.snapshot_id = ? ORDER BY pf.median_rank""",
                (snapshot["id"],),
            ).fetchall()
            placements_payload = [{
                "club": {"name": r["display_name"], "short": r["short_name"], "code": r["code"],
                         "primary": r["primary_color"], "secondary": r["secondary_color"],
                         "variant": r["badge_variant"]},
                "median": r["median_rank"], "range": [r["low_rank"], r["high_rank"]],
                "title": r["p_title"], "top4": r["p_top4"], "relegation": r["p_relegation"],
            } for r in rows]

        return {
            "mode": snapshot["mode"] if snapshot else "preview",
            "generatedAt": snapshot["published_at"] if snapshot else meta.get("generated_at", "noch nicht veröffentlicht"),
            "season": season,
            "matchday": matchday,
            "fixtures": fixture_payload,
            "history": history_payload,
            "strengths": strengths_payload,
            "placements": placements_payload,
        }


def start_run(path: str | Path, job: str, started_at: str) -> int:
    with transaction(path) as connection:
        cursor = connection.execute(
            "INSERT INTO pipeline_runs(job, started_at, status) VALUES (?, ?, 'running')",
            (job, started_at),
        )
        return int(cursor.lastrowid)


def finish_run(path: str | Path, run_id: int, finished_at: str, status: str, details: dict[str, Any]) -> None:
    with transaction(path) as connection:
        connection.execute(
            "UPDATE pipeline_runs SET finished_at = ?, status = ?, details_json = ? WHERE id = ?",
            (finished_at, status, json.dumps(details, ensure_ascii=False), run_id),
        )
