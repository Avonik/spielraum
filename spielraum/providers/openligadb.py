from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from ..seed import CLUBS


API_ROOT = "https://api.openligadb.de"
DEFAULT_LEAGUE = "bl1"


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", value)


_ALIASES = {
    "bayern": ["FC Bayern München", "Bayern München", "Bayern Munich"],
    "stuttgart": ["VfB Stuttgart", "Stuttgart"],
    "elversberg": ["SV 07 Elversberg", "SV Elversberg", "Elversberg"],
    "leverkusen": ["Bayer 04 Leverkusen", "Bayer Leverkusen", "Leverkusen"],
    "koeln": ["1. FC Köln", "FC Köln", "FC Koln"],
    "hoffenheim": ["TSG Hoffenheim", "TSG 1899 Hoffenheim", "Hoffenheim"],
    "union": ["1. FC Union Berlin", "Union Berlin"],
    "frankfurt": ["Eintracht Frankfurt", "Ein Frankfurt", "Frankfurt"],
    "mainz": ["1. FSV Mainz 05", "Mainz 05", "Mainz"],
    "paderborn": ["SC Paderborn 07", "SC Paderborn", "Paderborn"],
    "leipzig": ["RB Leipzig", "RasenBallsport Leipzig", "Leipzig"],
    "gladbach": ["Borussia Mönchengladbach", "Borussia M'gladbach", "M'gladbach", "Gladbach"],
    "dortmund": ["Borussia Dortmund", "Dortmund"],
    "hamburg": ["Hamburger SV", "Hamburg", "HSV"],
    "freiburg": ["SC Freiburg", "Freiburg"],
    "bremen": ["SV Werder Bremen", "Werder Bremen", "Bremen"],
    "augsburg": ["FC Augsburg", "Augsburg"],
    "schalke": ["FC Schalke 04", "Schalke 04", "Schalke"],
    "heidenheim": ["1. FC Heidenheim 1846", "1. FC Heidenheim", "Heidenheim"],
    "stpauli": ["FC St. Pauli", "St. Pauli", "St Pauli"],
    "wolfsburg": ["VfL Wolfsburg", "Wolfsburg"],
}

FD_NAMES = {
    "bayern": "Bayern Munich", "stuttgart": "Stuttgart", "elversberg": "Elversberg",
    "leverkusen": "Leverkusen", "koeln": "FC Koln", "hoffenheim": "Hoffenheim",
    "union": "Union Berlin", "frankfurt": "Ein Frankfurt", "mainz": "Mainz",
    "paderborn": "Paderborn", "leipzig": "RB Leipzig", "gladbach": "M'gladbach",
    "dortmund": "Dortmund", "hamburg": "Hamburg", "freiburg": "Freiburg",
    "bremen": "Werder Bremen", "augsburg": "Augsburg", "schalke": "Schalke 04",
    "heidenheim": "Heidenheim", "stpauli": "St Pauli", "wolfsburg": "Wolfsburg",
}

_ALIAS_TO_SLUG = {
    _normalise(alias): slug
    for slug, aliases in _ALIASES.items()
    for alias in aliases
}


def slug_for_team(name: str) -> str:
    try:
        return _ALIAS_TO_SLUG[_normalise(name)]
    except KeyError as exc:
        raise ValueError(f"OpenLigaDB team is not mapped: {name!r}") from exc


def fd_name_for_team(name: str) -> str:
    return FD_NAMES[slug_for_team(name)]


def team_payload(slug: str) -> dict[str, str]:
    try:
        name, short, code, primary, secondary, variant = CLUBS[slug]
    except KeyError as exc:
        raise ValueError(f"Missing Spielraum club metadata for {slug!r}") from exc
    return {
        "slug": slug,
        "name": name,
        "short": short,
        "code": code,
        "primary": primary,
        "secondary": secondary,
        "variant": variant,
    }


def fixture_id_for(season_start: int, matchday: int, home_slug: str, away_slug: str) -> str:
    home_code = CLUBS[home_slug][2].lower()
    away_code = CLUBS[away_slug][2].lower()
    season_code = f"{season_start % 100:02d}{(season_start + 1) % 100:02d}"
    return f"{season_code}-{matchday:02d}-{home_code}-{away_code}"


def _utc_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"OpenLigaDB timestamp has no timezone: {value!r}")
    return parsed.astimezone(UTC).isoformat()


def _final_score(raw: dict[str, Any]) -> tuple[int, int] | None:
    if not raw.get("matchIsFinished"):
        return None
    results = raw.get("matchResults") or []
    final = next((item for item in results if int(item.get("resultTypeID", -1)) == 2), None)
    if final is None and results:
        final = max(results, key=lambda item: int(item.get("resultOrderID", 0)))
    if final is None:
        raise ValueError(f"Finished OpenLigaDB match {raw.get('matchID')} has no final score")
    return int(final["pointsTeam1"]), int(final["pointsTeam2"])


@dataclass(frozen=True)
class OpenLigaMatch:
    fixture_id: str
    provider_id: int
    season_start: int
    matchday: int
    kickoff_utc: str
    home_slug: str
    away_slug: str
    home_fd: str
    away_fd: str
    finished: bool
    score: tuple[int, int] | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "OpenLigaMatch":
        provider_id = int(raw["matchID"])
        home_name = str(raw["team1"]["teamName"])
        away_name = str(raw["team2"]["teamName"])
        home_slug = slug_for_team(home_name)
        away_slug = slug_for_team(away_name)
        season_start = int(raw["leagueSeason"])
        matchday = int(raw["group"]["groupOrderID"])
        score = _final_score(raw)
        return cls(
            fixture_id=fixture_id_for(season_start, matchday, home_slug, away_slug),
            provider_id=provider_id,
            season_start=season_start,
            matchday=matchday,
            kickoff_utc=_utc_timestamp(str(raw["matchDateTimeUTC"])),
            home_slug=home_slug,
            away_slug=away_slug,
            home_fd=FD_NAMES[home_slug],
            away_fd=FD_NAMES[away_slug],
            finished=bool(raw.get("matchIsFinished")),
            score=score,
        )

    def result_payload(self, observed_at: str | None = None) -> dict[str, Any]:
        if not self.finished or self.score is None:
            raise ValueError(f"Match {self.fixture_id} is not finished")
        return {
            "fixture_id": self.fixture_id,
            "home_goals": self.score[0],
            "away_goals": self.score[1],
            "status": "finished",
            "observed_at": observed_at or datetime.now(UTC).isoformat(),
        }

    def fixture_payload(self) -> dict[str, Any]:
        return {
            "id": self.fixture_id,
            "season": f"{self.season_start}/{str(self.season_start + 1)[-2:]}",
            "matchday": self.matchday,
            "kickoff_utc": self.kickoff_utc,
            "home": self.home_slug,
            "away": self.away_slug,
            "status": "finished" if self.finished else "scheduled",
        }


def parse_matches(payload: Iterable[dict[str, Any]]) -> list[OpenLigaMatch]:
    matches = [OpenLigaMatch.from_api(item) for item in payload]
    matches.sort(key=lambda item: (item.matchday, item.kickoff_utc, item.provider_id))
    return matches


def fetch_json(path: str, *, timeout: float = 20.0) -> Any:
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={"User-Agent": "Spielraum-Forecast-Lab/0.1 (+portfolio project)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_season(season_start: int, *, league: str = DEFAULT_LEAGUE) -> list[OpenLigaMatch]:
    payload = fetch_json(f"/getmatchdata/{league}/{int(season_start)}")
    if not isinstance(payload, list):
        raise ValueError("OpenLigaDB season response is not a list")
    return parse_matches(payload)


def fetch_matchday(season_start: int, matchday: int, *, league: str = DEFAULT_LEAGUE) -> list[OpenLigaMatch]:
    payload = fetch_json(f"/getmatchdata/{league}/{int(season_start)}/{int(matchday)}")
    if not isinstance(payload, list):
        raise ValueError("OpenLigaDB matchday response is not a list")
    return parse_matches(payload)


def next_unfinished_matchday(matches: Iterable[OpenLigaMatch]) -> int | None:
    pending = [match.matchday for match in matches if not match.finished]
    return min(pending) if pending else None
