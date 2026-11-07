"""Chronological forecast planning and data boundaries, independent of model fitting."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Settings
from .providers.openligadb import OpenLigaMatch
from .storage import connect


def matchday_view(matches: list[OpenLigaMatch], matchday: int) -> tuple[list[OpenLigaMatch], datetime]:
    """Erase target/future results before fitting AND season simulation."""
    target = [match for match in matches if match.matchday == matchday]
    if not target:
        raise ValueError(f"No fixtures for matchday {matchday}")
    cutoff = min(datetime.fromisoformat(match.kickoff_utc) for match in target) - timedelta(seconds=1)
    return [
        match if match.matchday < matchday and datetime.fromisoformat(match.kickoff_utc) <= cutoff
        else replace(match, finished=False, score=None)
        for match in matches
    ], cutoff


def next_pending_matchday(settings: Settings, now: datetime) -> int | None:
    """Find the oldest unpublished round; never skip a gap or a missing result."""
    with connect(settings.database_path, readonly=True) as connection:
        meta = connection.execute("SELECT value FROM metadata WHERE key = 'current_season'").fetchone()
        season = meta["value"] if meta else "2026/27"
        fixtures = connection.execute(
            "SELECT matchday, kickoff_utc, status FROM fixtures WHERE season = ? ORDER BY matchday, kickoff_utc",
            (season,),
        ).fetchall()
        published = {row["matchday"] for row in connection.execute(
            "SELECT matchday FROM published_snapshots WHERE season = ? AND mode = 'live' AND manifest_sha256 IS NOT NULL",
            (season,),
        )}
    rounds = {}
    for fixture in fixtures:
        rounds.setdefault(fixture["matchday"], []).append(fixture)
    zone = ZoneInfo(settings.timezone)
    for matchday in range(1, 35):
        if matchday in published:
            continue
        if len(rounds.get(matchday, [])) != 9:
            return None
        previous = [fixture for day, games in rounds.items() if day < matchday for fixture in games]
        if len(previous) != (matchday - 1) * 9 or any(fixture["status"] != "finished" for fixture in previous):
            return None
        if previous:
            last_kickoff = max(datetime.fromisoformat(fixture["kickoff_utc"]) for fixture in previous).astimezone(zone)
            due = (last_kickoff + timedelta(days=(7 - last_kickoff.weekday()) % 7)).replace(
                hour=settings.model_hour, minute=settings.model_minute, second=0, microsecond=0
            )
            if due <= last_kickoff:
                due += timedelta(days=7)
        else:
            due = min(datetime.fromisoformat(fixture["kickoff_utc"]) for fixture in rounds[1]) - timedelta(days=7)
        return matchday if now >= due else None
    return None
