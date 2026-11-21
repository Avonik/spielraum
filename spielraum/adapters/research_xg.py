"""Import researched final xG from explicit, reviewed Bundesliga report URLs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from spielraum.artifacts import write_json_atomic
from spielraum.config import Settings
from spielraum.providers.openligadb import FD_NAMES, slug_for_team
from spielraum.storage import connect


REPORTS = {
    "2627-08-elv-m05": "de/bundesliga/news/sv-elversberg-1-fsv-mainz-05-spieltag-8-spielbericht-highlights-39784",
    "2627-08-b04-vfb": "de/bundesliga/news/bayer-04-leverkusen-vfb-stuttgart-spieltag-8-spielbericht-highlights-39803",
    "2627-08-fca-scf": "de/bundesliga/news/fc-augsburg-sport-club-freiburg-spieltag-8-spielbericht-highlights-39798",
    "2627-08-bmg-scp": "de/bundesliga/news/borussia-moenchengladbach-sc-paderborn-07-spieltag-8-spielbericht-highlights-39799",
    "2627-08-svw-tsg": "de/bundesliga/news/sv-werder-bremen-tsg-hoffenheim-spieltag-8-spielbericht-highlights-39797",
    "2627-08-s04-rbl": "de/bundesliga/news/fc-schalke-04-rb-leipzig-spieltag-8-spielbericht-highlights-39801",
    "2627-08-fcb-bvb": "en/bundesliga/news/bayern-munich-borussia-dortmund-match-report-highlights-matchday-8-kane-guirassy-silva-39815",
    "2627-08-fcu-koe": "de/bundesliga/news/1-fc-union-berlin-1-fc-koeln-spieltag-8-spielbericht-highlights-39833",
    "2627-08-sge-hsv": "de/bundesliga/news/eintracht-frankfurt-hamburger-sv-spieltag-8-spielbericht-highlights-39836",
    "2627-09-hsv-bmg": "de/bundesliga/news/hamburger-sv-borussia-moenchengladbach-spieltag-9-spielbericht-highlights-39908",
    "2627-09-bvb-elv": "de/bundesliga/news/borussia-dortmund-sv-elversberg-spieltag-9-spielbericht-highlights-39916",
    "2627-09-rbl-fca": "de/bundesliga/news/rb-leipzig-fc-augsburg-spieltag-9-spielbericht-highlights-39918",
    "2627-09-m05-fcb": "en/bundesliga/news/mainz-bayern-munich-match-report-highlights-matchday-9-39922",
    "2627-09-scp-sge": "de/bundesliga/news/sc-paderborn-07-eintracht-frankfurt-spieltag-9-spielbericht-highlights-39917",
    "2627-09-vfb-svw": "de/bundesliga/news/vfb-stuttgart-sv-werder-bremen-spieltag-9-spielbericht-highlights-39927",
    "2627-09-koe-b04": "de/bundesliga/news/1-fc-koeln-bayer-04-leverkusen-spieltag-9-spielbericht-highlights-39944",
    "2627-09-scf-fcu": "de/bundesliga/news/sport-club-freiburg-1-fc-union-berlin-spieltag-9-spielbericht-highlights-39946",
    "2627-09-tsg-s04": "de/bundesliga/news/tsg-hoffenheim-fc-schalke-04-spieltag-9-spielbericht-highlights-39950",
    "2627-10-fcb-koe": "de/bundesliga/news/fc-bayern-muenchen-1-fc-koeln-spieltag-10-spielbericht-highlights-40057",
    "2627-10-b04-scp": "de/bundesliga/news/bayer-04-leverkusen-sc-paderborn-07-spieltag-10-spielbericht-highlights-40074",
    "2627-10-sge-tsg": "de/bundesliga/news/eintracht-frankfurt-tsg-hoffenheim-spieltag-10-spielbericht-highlights-40078",
    "2627-10-fcu-rbl": "de/bundesliga/news/1-fc-union-berlin-rb-leipzig-spieltag-10-spielbericht-highlights-40075",
    "2627-10-bmg-bvb": "de/bundesliga/news/borussia-moenchengladbach-borussia-dortmund-spieltag-10-spielbericht-highlights-40071",
    "2627-10-elv-scf": "de/bundesliga/news/sv-elversberg-sport-club-freiburg-spieltag-10-spielbericht-highlights-40076",
    "2627-10-s04-vfb": "en/bundesliga/news/schalke-vfb-stuttgart-match-report-highlights-matchday-10-40089",
}


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.collecting = False
        self.buffer = []
        self.articles = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self.collecting = True
            self.buffer = []

    def handle_data(self, data):
        if self.collecting:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.collecting:
            self.collecting = False
            payload = json.loads("".join(self.buffer))
            if isinstance(payload, dict) and "articleBody" in payload:
                self.articles.append(payload)


def parse_report(html: str) -> dict:
    parser = ArticleParser()
    parser.feed(html)
    if len(parser.articles) != 1:
        raise ValueError("Expected exactly one structured match report")
    article = parser.articles[0]
    if "Bundesliga Match Facts" not in article["articleBody"]:
        raise ValueError("No final Match Facts section")
    facts = article["articleBody"].split("Bundesliga Match Facts", 1)[1]
    line = re.search(r"xGoals:[^\t\n]*", facts)
    match = re.fullmatch(r"xGoals:\s*(.+?)\s+(\d+(?:[.,]\d+)?)\s*[-–]\s*(.+?)\s+(\d+(?:[.,]\d+)?)", line[0].strip()) if line else None
    if not match:
        raise ValueError("No final xGoals pair in match report")
    aliases = {"Köln": "1. FC Köln", "Sport-Club Freiburg": "Freiburg", "Union": "Union Berlin"}
    return {
        "home": slug_for_team(aliases.get(match[1], match[1])),
        "away": slug_for_team(aliases.get(match[3], match[3])),
        "home_xg": float(match[2].replace(",", ".")),
        "away_xg": float(match[4].replace(",", ".")),
        "source_published_at": article["datePublished"],
        "evidence": match[0],
    }


def import_reports(settings: Settings, matchday: int, *, seed_cache: bool = False) -> dict:
    path = settings.data_dir / "cache" / "verified-xg-2026-27.json"
    payload = json.loads(path.read_text()) if path.exists() else {"format": 1, "season": "2026/27", "records": []}
    records = {row["fixture_id"]: row for row in payload["records"]}
    with connect(settings.database_path, readonly=True) as connection:
        fixtures = {row["id"]: dict(row) for row in connection.execute(
            """SELECT f.id AS fixture_id, f.id, f.matchday, f.kickoff_utc, h.slug AS home, a.slug AS away,
                      r.home_goals, r.away_goals, r.status
               FROM fixtures f JOIN teams h ON h.id=f.home_team_id JOIN teams a ON a.id=f.away_team_id
               JOIN results r ON r.fixture_id=f.id WHERE f.season='2026/27' AND r.status='finished'"""
        )}
    now = datetime.now(UTC).isoformat()
    if seed_cache:
        from v2.real_xg import _FD_TO_US
        cached_path = Path.home() / "soccerdata/data/Understat/league_3_season_2026.json"
        raw = cached_path.read_bytes()
        cached = json.loads(raw)
        by_pair = {(row["h"]["title"], row["a"]["title"]): row for row in cached["dates"] if row.get("isResult")}
        for fixture in fixtures.values():
            if fixture["matchday"] >= 8 or fixture["fixture_id"] in records:
                continue
            row = by_pair.get((_FD_TO_US[FD_NAMES[fixture["home"]]], _FD_TO_US[FD_NAMES[fixture["away"]]]))
            if row is None:
                raise ValueError(f"Understat cache missing: {fixture['fixture_id']}")
            if (int(row["goals"]["h"]), int(row["goals"]["a"])) != (fixture["home_goals"], fixture["away_goals"]) or row["datetime"][:10] != fixture["kickoff_utc"][:10]:
                raise ValueError(f"Understat cache identity mismatch: {fixture['fixture_id']}")
            records[fixture["fixture_id"]] = {**fixture, "home_xg": float(row["xG"]["h"]), "away_xg": float(row["xG"]["a"]),
                "source": "Understat cached", "source_url": f"https://understat.com/match/{row['id']}",
                "source_sha256": hashlib.sha256(raw).hexdigest(), "retrieved_at": now}
    imported = []
    for fixture_id, relative in REPORTS.items():
        if int(fixture_id.split("-")[1]) != matchday:
            continue
        fixture = fixtures.get(fixture_id)
        if fixture is None:
            raise ValueError(f"No finished result for researched fixture: {fixture_id}")
        url = "https://www.bundesliga.com/" + relative
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Spielraum xG research"}), timeout=30).read()
        row = parse_report(raw.decode("utf-8"))
        if (row["home"], row["away"]) != (fixture["home"], fixture["away"]) or row["source_published_at"][:10] != fixture["kickoff_utc"][:10]:
            raise ValueError(f"Report identity mismatch: {fixture_id}")
        if fixture_id in records and (records[fixture_id]["home_xg"], records[fixture_id]["away_xg"]) != (row["home_xg"], row["away_xg"]):
            raise ValueError(f"Reviewed xG changed, manual review required: {fixture_id}")
        source_sha256 = hashlib.sha256(raw).hexdigest()
        evidence_path = settings.data_dir / "cache" / "xg-evidence" / f"{fixture_id}-{source_sha256}.html"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(raw)
        records[fixture_id] = {**fixture, **row, "source": "Bundesliga Match Facts",
            "source_url": url, "source_sha256": source_sha256,
            "evidence_path": str(evidence_path.relative_to(settings.data_dir)), "retrieved_at": now}
        imported.append({"fixture_id": fixture_id, "home_xg": row["home_xg"], "away_xg": row["away_xg"]})
    payload["records"] = sorted(records.values(), key=lambda row: (row["matchday"], row["fixture_id"]))
    payload["updated_at"] = now
    write_json_atomic(path, payload)
    return {"matchday": matchday, "imported": imported, "total_verified": len(records)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--matchday", type=int, choices=(8, 9, 10), required=True)
    parser.add_argument("--seed-understat-cache", action="store_true")
    args = parser.parse_args()
    print(json.dumps(import_reports(Settings.from_env(), args.matchday, seed_cache=args.seed_understat_cache), ensure_ascii=False))
