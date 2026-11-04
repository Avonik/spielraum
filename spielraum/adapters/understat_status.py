"""Check the same live data feed used by the model without storing a cache."""
from __future__ import annotations

import json
from datetime import UTC, datetime


def check_availability() -> dict[str, bool | str]:
    import soccerdata as sd

    now = datetime.now(UTC)
    year = now.year if now.month >= 7 else now.year - 1
    season = f"{year % 100:02d}{(year + 1) % 100:02d}"
    try:
        reader = sd.Understat(
            leagues="GER-Bundesliga", seasons=[season], no_cache=True, no_store=True
        )
        schedule = reader.read_schedule()
        # HTTP 200 alone is insufficient: holding pages are also served as 200.
        if not {"home_xg", "away_xg"}.issubset(schedule.columns):
            raise ValueError("Understat did not return the expected xG data")
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    return {"available": True}


if __name__ == "__main__":
    print(json.dumps(check_availability(), ensure_ascii=False))
