"""Locally verified match xG, with fixture identity and source provenance."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .providers.openligadb import OpenLigaMatch


def read_verified_xg(data_dir: Path, matches: list[OpenLigaMatch]) -> dict[str, dict]:
    path = data_dir / "cache" / "verified-xg-2026-27.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("season") != "2026/27" or payload.get("format") != 1:
        raise ValueError("Invalid verified xG file format or season")
    needed = {match.fixture_id: match for match in matches if match.finished}
    records = {}
    for record in payload["records"]:
        fixture_id = record["fixture_id"]
        # Future/target records are deliberately not read into model inputs.
        if fixture_id not in needed:
            continue
        if fixture_id in records:
            raise ValueError(f"Duplicate verified xG: {fixture_id}")
        match = needed[fixture_id]
        if (record["home"], record["away"], record["kickoff_utc"]) != (match.home_slug, match.away_slug, match.kickoff_utc):
            raise ValueError(f"Verified xG fixture identity mismatch: {fixture_id}")
        if (record["home_goals"], record["away_goals"]) != match.score:
            raise ValueError(f"Verified xG result mismatch: {fixture_id}")
        for field in ("home_xg", "away_xg"):
            value = float(record[field])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid verified xG: {fixture_id}")
        if not record.get("source") or not record.get("source_url", "").startswith("https://") or not record.get("source_sha256"):
            raise ValueError(f"Missing verified xG provenance: {fixture_id}")
        records[fixture_id] = record
    return records
