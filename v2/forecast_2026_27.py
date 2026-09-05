"""Create a versioned preseason state and optional fixture predictions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from data import load_bundesliga
from market_value import team_market_values
from preseason import fit_preseason_state, predict_preseason_fixtures
from xg import add_xg_columns, fit_xg_weights


DEFAULT_2026_27_TEAMS = [
    "Augsburg", "Bayern Munich", "Dortmund", "Ein Frankfurt", "Elversberg",
    "FC Koln", "Freiburg", "Hamburg", "Hoffenheim", "Leverkusen",
    "M'gladbach", "Mainz", "Paderborn", "RB Leipzig", "Schalke 04",
    "Stuttgart", "Union Berlin", "Werder Bremen",
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-season", default="2026/27")
    parser.add_argument("--fixtures", type=Path,
                        help="CSV with at least HomeTeam and AwayTeam columns")
    parser.add_argument("--carry-weight", type=float, default=0.75)
    parser.add_argument("--market-kappa", type=float, default=0.10)
    parser.add_argument("--n-iter", type=int, default=5000)
    parser.add_argument("--burnin", type=int, default=1000)
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    return parser


def main() -> None:
    args = _parser().parse_args()
    target_start = int(args.target_season.split("/")[0])
    df = load_bundesliga(1993, target_start, with_extras=True)

    # Proxy-xG weights are fitted strictly before the source season.
    source_start = target_start - 1
    source_label = f"{source_start}/{source_start % 100 + 1:02d}"
    xg_train = df[df["Season"] < source_label]
    beta_off, beta_on = fit_xg_weights(xg_train, force=True, cache=False)
    df = add_xg_columns(df, beta_off, beta_on)

    fixtures = None
    target_teams = None
    if args.fixtures:
        fixtures = pd.read_csv(args.fixtures)
        target_teams = sorted(set(fixtures["HomeTeam"]) | set(fixtures["AwayTeam"]))
    elif args.target_season == "2026/27":
        target_teams = DEFAULT_2026_27_TEAMS

    state = fit_preseason_state(
        df,
        args.target_season,
        target_teams=target_teams,
        carry_weight=args.carry_weight,
        market_kappa=args.market_kappa,
        n_iter=args.n_iter,
        burnin=args.burnin,
        verbose=True,
    )
    try:
        market_values = team_market_values(args.target_season)
    except (FileNotFoundError, ValueError):
        market_values = {}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = args.output_root / f"forecast_{args.target_season.replace('/', '_')}_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    state_path = state.save_json(report_dir / "preseason_state.json")

    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_season": args.target_season,
        "source_season": state.source_season,
        "xg_source": "football-data shot proxy",
        "xg_weights": {"off_target": beta_off, "on_target": beta_on},
        "market_values_available": len(market_values),
        "fixtures_file": str(args.fixtures) if args.fixtures else None,
    }
    (report_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Preseason state: {state_path.resolve()}")
    print(f"Carried teams: {len(state.carried_teams)}, new teams: {state.new_teams}")
    if fixtures is not None:
        predictions = predict_preseason_fixtures(
            fixtures, state, market_values=market_values or None)
        predictions.to_json(report_dir / "predictions.json", orient="records",
                            indent=2, force_ascii=False, date_format="iso")
        predictions.to_csv(report_dir / "predictions.csv", index=False)
        print(f"Predictions: {(report_dir / 'predictions.json').resolve()}")
    else:
        print("No fixtures supplied; wrote the reusable state only.")


if __name__ == "__main__":
    main()
