"""Focused real-xG tests for stable global goal levels on matchdays 1-5."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data import extract_bookmaker_probs, load_bundesliga
from evaluation import bookmaker_probs_from_df
from mcmc import warmup_jit
from real_xg import add_real_xg_columns
from season_transition_v2 import fit_previous_v2, run_dual_v2_season
from xg import add_xg_columns, fit_xg_weights


BUDGETS = {
    "screen": dict(prior_iter=5_000, prior_burnin=1_000,
                   base_iter=3_000, base_burnin=600,
                   warm_iter=1_500, warm_burnin=250, thin=10),
    "confirm": dict(prior_iter=15_000, prior_burnin=3_000,
                    base_iter=10_000, base_burnin=2_000,
                    warm_iter=5_000, warm_burnin=800, thin=10),
}


_WORKER_DF: pd.DataFrame | None = None


def _init_worker(df: pd.DataFrame) -> None:
    global _WORKER_DF
    _WORKER_DF = df
    warmup_jit()


def _tag(value: float) -> str:
    if np.isinf(value):
        return "fixed"
    return f"n{value:g}".replace(".", "p")


def _bookmaker_for_result(df: pd.DataFrame, season: str,
                          result: pd.DataFrame) -> np.ndarray:
    season_df = (df[df["Season"] == season]
                 .sort_values("Date").reset_index(drop=True))
    probabilities = bookmaker_probs_from_df(season_df)
    lookup = season_df[["Date", "HomeTeam", "AwayTeam"]].copy()
    lookup["p_home_bookmaker"] = probabilities[:, 0]
    lookup["p_draw_bookmaker"] = probabilities[:, 1]
    lookup["p_away_bookmaker"] = probabilities[:, 2]
    matched = result[["Date", "HomeTeam", "AwayTeam"]].merge(
        lookup, on=["Date", "HomeTeam", "AwayTeam"], how="left",
        validate="one_to_one")
    columns = ["p_home_bookmaker", "p_draw_bookmaker", "p_away_bookmaker"]
    if matched[columns].isna().any().any():
        raise RuntimeError(f"Bookmaker merge failed for {season}.")
    return matched[columns].to_numpy(float)


def _rps(probabilities: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    first = probabilities[:, 0] - (outcomes == 0)
    second = probabilities[:, 0] + probabilities[:, 1] - (outcomes <= 1)
    return 0.5 * (first * first + second * second)


def _run_season(task: tuple[int, str, dict, list[float]]) -> list[pd.DataFrame]:
    season_i, season, budget, level_priors = task
    if _WORKER_DF is None:
        raise RuntimeError("Worker data is missing.")
    df = _WORKER_DF
    print(f"{season}: previous-season endpoint", flush=True)
    endpoint = fit_previous_v2(
        df, season, n_iter=budget["prior_iter"],
        burnin=budget["prior_burnin"], thin=budget["thin"],
        seed=42 + season_i * 10_000)
    frames = []
    for prior_matches in level_priors:
        print(f"{season}: level prior {_tag(prior_matches)}", flush=True)
        result = run_dual_v2_season(
            df, season, endpoint,
            base_iter=budget["base_iter"],
            base_burnin=budget["base_burnin"],
            warm_iter=budget["warm_iter"],
            warm_burnin=budget["warm_burnin"],
            thin=budget["thin"], seed=42 + season_i * 10_000,
            summer_variance_scale=1.0,
            goal_level_prior_matches=prior_matches,
            max_matchday=5)
        bookmaker = _bookmaker_for_result(df, season, result)
        result["rps_bookmaker"] = _rps(
            bookmaker, result["outcome"].to_numpy(int))
        result["goal_level_prior_matches"] = prior_matches
        frames.append(result)
    return frames


def _scores(raw: pd.DataFrame, level_priors: list[float]) -> pd.DataFrame:
    rows = []
    for season, season_df in raw.groupby("season", sort=False):
        first = season_df[
            season_df["goal_level_prior_matches"].eq(level_priors[0])]
        rows.append(pd.DataFrame({
            "season": season, "candidate": "bookmaker",
            "rps": first["rps_bookmaker"].to_numpy(float),
        }))
        for prior_matches in level_priors:
            frame = season_df[
                season_df["goal_level_prior_matches"].eq(prior_matches)]
            for stream in ("fresh_v2", "carry_v2"):
                rows.append(pd.DataFrame({
                    "season": season,
                    "candidate": f"{_tag(prior_matches)}_{stream}",
                    "rps": frame[f"rps_{stream}"].to_numpy(float),
                }))
    return pd.concat(rows, ignore_index=True)


def _rolling_origin(scores: pd.DataFrame, min_train_seasons: int = 3
                    ) -> pd.DataFrame:
    seasons = sorted(scores["season"].unique())
    rows = []
    for i in range(min_train_seasons, len(seasons)):
        test_season = seasons[i]
        train = scores[(scores["season"].isin(seasons[:i]))
                       & ~scores["candidate"].eq("bookmaker")]
        ranking = train.groupby("candidate")["rps"].mean().sort_values()
        selected = str(ranking.index[0])
        test = scores[scores["season"] == test_season]
        rows.append({
            "test_season": test_season,
            "selected_candidate": selected,
            "train_rps": float(ranking.iloc[0]),
            "test_rps": float(test[test["candidate"] == selected]["rps"].mean()),
            "baseline_rps": float(test[test["candidate"] == "n0_carry_v2"]["rps"].mean()),
            "bookmaker_rps": float(test[test["candidate"] == "bookmaker"]["rps"].mean()),
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=[
        "2015/16", "2016/17", "2017/18", "2018/19", "2019/20",
        "2020/21", "2021/22", "2022/23", "2023/24", "2024/25",
        "2025/26",
    ])
    parser.add_argument("--budget", choices=sorted(BUDGETS), default="screen")
    parser.add_argument("--level-priors", type=float, nargs="+",
                        default=[0.0, 4.5, 9.0, 18.0, 36.0, 72.0,
                                 144.0, float("inf")])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output-root", type=Path, default=Path("v2/output"))
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("--workers must be at least 1.")
    level_priors = sorted(set(args.level_priors))
    if any(value < 0.0 or np.isnan(value) for value in level_priors):
        raise ValueError("Level priors must be non-negative or infinity.")

    latest_start = max(int(season.split("/")[0]) for season in args.seasons)
    earliest = min(args.seasons)
    df = extract_bookmaker_probs(load_bundesliga(
        1993, latest_start + 1, with_extras=True))
    beta = fit_xg_weights(df[df["Season"] < earliest], force=True, cache=False)
    df = add_xg_columns(df, *beta)
    df = add_real_xg_columns(df)

    budget = BUDGETS[args.budget]
    tasks = [(i, season, budget, level_priors)
             for i, season in enumerate(args.seasons)]
    if args.workers == 1:
        _init_worker(df)
        nested = [_run_season(task) for task in tasks]
    else:
        worker_count = min(args.workers, len(tasks))
        print(f"Running {len(tasks)} seasons on {worker_count} processes.",
              flush=True)
        with ProcessPoolExecutor(
                max_workers=worker_count, initializer=_init_worker,
                initargs=(df,)) as executor:
            nested = list(executor.map(_run_season, tasks))
    raw = pd.concat([frame for group in nested for frame in group],
                    ignore_index=True)
    scores = _scores(raw, level_priors)
    pooled = (scores.groupby("candidate", as_index=False)["rps"].mean()
              .sort_values("rps"))
    per_season = (scores.groupby(["season", "candidate"], as_index=False)
                  ["rps"].mean())
    rolling = _rolling_origin(scores)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.output_root / f"early_level_{args.budget}_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    raw.to_csv(report_dir / "raw_predictions.csv", index=False)
    scores.to_csv(report_dir / "per_match_scores.csv", index=False)
    pooled.to_csv(report_dir / "pooled.csv", index=False)
    per_season.to_csv(report_dir / "per_season.csv", index=False)
    rolling.to_csv(report_dir / "rolling_origin.csv", index=False)
    (report_dir / "config.json").write_text(json.dumps({
        "seasons": args.seasons,
        "budget": args.budget,
        "mcmc_budget": budget,
        "level_prior_matches": level_priors,
        "workers": min(args.workers, len(args.seasons)),
        "evaluation_matchdays": [1, 2, 3, 4, 5],
        "xg_source": "Understat real xG",
    }, indent=2), encoding="utf-8")
    print("\nPOOLED", flush=True)
    print(pooled.to_string(index=False, float_format=lambda x: f"{x:.5f}"),
          flush=True)
    print("\nROLLING ORIGIN", flush=True)
    print(rolling.to_string(index=False, float_format=lambda x: f"{x:.5f}"),
          flush=True)
    print(f"\nReport: {report_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
