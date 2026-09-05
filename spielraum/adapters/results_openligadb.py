from __future__ import annotations

import argparse
import json

from spielraum.providers.openligadb import fetch_season, team_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch finished Bundesliga results from OpenLigaDB")
    parser.add_argument("--season", type=int, default=2026, help="season start year")
    args = parser.parse_args()
    matches = fetch_season(args.season)
    slugs = sorted({match.home_slug for match in matches} | {match.away_slug for match in matches})
    results = [match.result_payload() for match in matches if match.finished]
    print(json.dumps({
        "source": "OpenLigaDB (ODbL)",
        "teams": [team_payload(slug) for slug in slugs],
        "fixtures": [match.fixture_payload() for match in matches],
        "results": results,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
