"""Real-xG pretests and rolling-origin handoff selection for two true V2 streams."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data import extract_bookmaker_probs, load_bundesliga
from evaluation import bookmaker_probs_from_df, rps_one
from mcmc import warmup_jit
from real_xg import add_real_xg_columns
from season_transition_v2 import fit_previous_v2, run_dual_v2_season
from xg import add_xg_columns, fit_xg_weights


BUDGETS = {
    "screen": dict(prior_iter=1_500, prior_burnin=300,
                   base_iter=1_000, base_burnin=200,
                   warm_iter=500, warm_burnin=100, thin=10),
    "confirm": dict(prior_iter=5_000, prior_burnin=1_000,
                    base_iter=3_000, base_burnin=600,
                    warm_iter=1_500, warm_burnin=250, thin=10),
    "v2_single": dict(prior_iter=40_000, prior_burnin=8_000,
                      base_iter=40_000, base_burnin=8_000,
                      warm_iter=20_000, warm_burnin=3_000, thin=10),
}


_WORKER_DF: pd.DataFrame | None = None


def _carry_weight(matchdays: np.ndarray, end_matchday: int,
                  width: int) -> np.ndarray:
    matchdays = np.asarray(matchdays, dtype=float)
    if width == 0:
        return (matchdays < end_matchday).astype(float)
    start = max(1, end_matchday - width)
    progress = np.clip((matchdays - start) / float(end_matchday - start),
                       0.0, 1.0)
    weights = 0.5 * (1.0 + np.cos(np.pi * progress))
    return np.where(matchdays < start, 1.0,
                    np.where(matchdays >= end_matchday, 0.0, weights))


def _probabilities(frame: pd.DataFrame, suffix: str) -> np.ndarray:
    return frame[[f"p_home_{suffix}", f"p_draw_{suffix}",
                  f"p_away_{suffix}"]].to_numpy(float)


def _policy_scores(raw: pd.DataFrame, scales: list[float]) -> pd.DataFrame:
    rows = []
    for season, season_all in raw.groupby("season", sort=False):
        first = season_all[season_all["summer_variance_scale"] == scales[0]]
        outcomes = first["outcome"].to_numpy(int)
        fresh = _probabilities(first, "fresh_v2")
        bookmaker = _probabilities(first, "bookmaker")
        base = first[["season", "season_game", "matchday"]].copy()
        candidates = {
            "fresh_always": fresh,
            "bookmaker": bookmaker,
        }
        for scale in scales:
            frame = season_all[season_all["summer_variance_scale"] == scale]
            carry = _probabilities(frame, "carry_v2")
            recommended = _probabilities(frame, "recommended_v2")
            scale_tag = f"{scale:g}".replace(".", "p")
            candidates[f"carry_s{scale_tag}_always"] = carry
            candidates[f"recommended_s{scale_tag}"] = recommended
            for end in range(4, 31, 2):
                for width in (0, 2, 4, 6):
                    weight = _carry_weight(frame["matchday"].to_numpy(), end, width)
                    label = (f"carry_s{scale_tag}_hard_end{end}" if width == 0
                             else f"carry_s{scale_tag}_cos_w{width}_end{end}")
                    candidates[label] = (weight[:, None] * carry
                                         + (1.0 - weight[:, None]) * fresh)
        for candidate, probs in candidates.items():
            part = base.copy()
            part["candidate"] = candidate
            part["rps"] = [rps_one(p, y) for p, y in zip(probs, outcomes)]
            rows.append(part)
    return pd.concat(rows, ignore_index=True)


def _rolling_origin(policy_scores: pd.DataFrame, min_train_seasons: int = 3
                    ) -> pd.DataFrame:
    seasons = sorted(policy_scores["season"].unique())
    rows = []
    for test_i in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_i]
        train_seasons = seasons[:test_i]
        train = policy_scores[
            policy_scores["season"].isin(train_seasons)
            & ~policy_scores["candidate"].eq("bookmaker")
        ]
        ranking = train.groupby("candidate")["rps"].mean().sort_values()
        selected = str(ranking.index[0])
        test = policy_scores[policy_scores["season"] == test_season]
        selected_rps = float(test[test["candidate"] == selected]["rps"].mean())
        fresh_rps = float(test[test["candidate"] == "fresh_always"]["rps"].mean())
        bookmaker_rps = float(test[test["candidate"] == "bookmaker"]["rps"].mean())
        rows.append({
            "test_season": test_season,
            "n_train_seasons": len(train_seasons),
            "selected_candidate": selected,
            "train_rps": float(ranking.iloc[0]),
            "test_rps": selected_rps,
            "fresh_rps": fresh_rps,
            "bookmaker_rps": bookmaker_rps,
        })
    return pd.DataFrame(rows)


def _init_season_worker(df: pd.DataFrame) -> None:
    """Install shared read-only input once per process and load the JIT kernel."""
    global _WORKER_DF
    _WORKER_DF = df
    warmup_jit()


def _run_one_season(
    task: tuple[int, str, dict, list[float], float, float | None],
) -> list[pd.DataFrame]:
    """Run one deterministic season job; safe for a Windows process pool."""
    (season_i, season, budget, scales, goal_level_prior_matches,
     goal_level_prior_fade_matches) = task
    if _WORKER_DF is None:
        raise RuntimeError("Season worker was not initialized with match data.")
    df = _WORKER_DF
    print(f"{season}: previous V2 endpoint", flush=True)
    endpoint = fit_previous_v2(
        df, season,
        n_iter=budget["prior_iter"],
        burnin=budget["prior_burnin"],
        thin=budget["thin"],
        seed=42 + season_i * 10_000,
    )
    frames = []
    reference_fresh = None
    for scale in scales:
        print(f"{season}: summer variance scale {scale:g}", flush=True)
        result = run_dual_v2_season(
            df, season, endpoint,
            base_iter=budget["base_iter"],
            base_burnin=budget["base_burnin"],
            warm_iter=budget["warm_iter"],
            warm_burnin=budget["warm_burnin"],
            thin=budget["thin"],
            seed=42 + season_i * 10_000,
            summer_variance_scale=scale,
            goal_level_prior_matches=goal_level_prior_matches,
            goal_level_prior_fade_matches=goal_level_prior_fade_matches,
        )
        bookmaker = bookmaker_probs_from_df(
            df[df["Season"] == season].sort_values("Date").reset_index(drop=True))
        result["p_home_bookmaker"] = bookmaker[:, 0]
        result["p_draw_bookmaker"] = bookmaker[:, 1]
        result["p_away_bookmaker"] = bookmaker[:, 2]
        result["summer_variance_scale"] = scale
        result["goal_level_prior_matches"] = goal_level_prior_matches
        result["goal_level_prior_fade_matches"] = (
            np.nan if goal_level_prior_fade_matches is None
            else goal_level_prior_fade_matches)
        fresh = _probabilities(result, "fresh_v2")
        if reference_fresh is None:
            reference_fresh = fresh
        elif not np.array_equal(reference_fresh, fresh):
            raise RuntimeError("Fresh V2 changed with the carry summer scale.")
        frames.append(result)
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=[
        "2015/16", "2016/17", "2017/18", "2018/19", "2019/20",
        "2020/21", "2021/22", "2022/23", "2023/24", "2024/25",
        "2025/26",
    ])
    parser.add_argument("--budget", choices=sorted(BUDGETS), default="screen")
    parser.add_argument("--summer-scales", type=float, nargs="+",
                        default=[1.0])
    parser.add_argument("--output-root", type=Path, default=Path("v2/output"))
    parser.add_argument("--workers", type=int, default=1,
                        help="Independent season processes (1 = sequential).")
    parser.add_argument("--goal-level-prior-matches", type=float, default=144.0,
                        help="Historical pseudo-matches for global goal levels.")
    parser.add_argument("--goal-level-prior-fade-matches", type=float,
                        help="Cosine-fade pseudo-count to zero by this many games.")
    args = parser.parse_args()

    scales = sorted(set(float(value) for value in args.summer_scales))
    if any(value <= 0.0 for value in scales):
        raise ValueError("Summer variance scales must be positive.")
    if args.workers < 1:
        raise ValueError("--workers must be at least 1.")
    if (args.goal_level_prior_matches < 0.0
            or np.isnan(args.goal_level_prior_matches)):
        raise ValueError("Goal-level prior must be non-negative or infinity.")
    if (args.goal_level_prior_fade_matches is not None
            and args.goal_level_prior_fade_matches <= 0.0):
        raise ValueError("Goal-level prior fade must be positive.")
    budget = BUDGETS[args.budget]
    earliest = min(args.seasons)
    latest_start = max(int(season.split("/")[0]) for season in args.seasons)
    df = extract_bookmaker_probs(load_bundesliga(1993, latest_start + 1,
                                                  with_extras=True))
    beta = fit_xg_weights(df[df["Season"] < earliest], force=True, cache=False)
    df = add_xg_columns(df, *beta)
    df = add_real_xg_columns(df)
    tasks = [(season_i, season, budget, scales,
              args.goal_level_prior_matches,
              args.goal_level_prior_fade_matches)
             for season_i, season in enumerate(args.seasons)]
    if args.workers == 1:
        _init_season_worker(df)
        season_frames = [_run_one_season(task) for task in tasks]
    else:
        worker_count = min(args.workers, len(tasks))
        print(f"Running {len(tasks)} seasons on {worker_count} processes.",
              flush=True)
        with ProcessPoolExecutor(
                max_workers=worker_count,
                initializer=_init_season_worker,
                initargs=(df,)) as executor:
            # map preserves task order, so CSVs remain byte-order reproducible.
            season_frames = list(executor.map(_run_one_season, tasks))
    frames = [frame for per_season in season_frames for frame in per_season]

    raw = pd.concat(frames, ignore_index=True)
    scores = _policy_scores(raw, scales)
    rolling = _rolling_origin(scores)
    pooled = (scores.groupby("candidate", as_index=False)["rps"].mean()
              .sort_values("rps"))
    by_matchday = (raw.groupby(["summer_variance_scale", "matchday"], as_index=False)
                   .agg(rps_fresh=("rps_fresh_v2", "mean"),
                        rps_carry=("rps_carry_v2", "mean"),
                        n=("rps_fresh_v2", "count")))
    by_matchday["fresh_minus_carry"] = (
        by_matchday["rps_fresh"] - by_matchday["rps_carry"])

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    level_tag = ("inf" if np.isinf(args.goal_level_prior_matches)
                 else f"{args.goal_level_prior_matches:g}".replace(".", "p"))
    fade_tag = ("none" if args.goal_level_prior_fade_matches is None
                else f"{args.goal_level_prior_fade_matches:g}".replace(".", "p"))
    report_dir = (args.output_root /
                  f"season_transition_v2_{args.budget}_g{level_tag}_f{fade_tag}_{stamp}")
    report_dir.mkdir(parents=True, exist_ok=False)
    raw.to_csv(report_dir / "dual_v2_raw_predictions.csv", index=False)
    scores.to_csv(report_dir / "policy_per_match.csv", index=False)
    pooled.to_csv(report_dir / "policy_pooled.csv", index=False)
    rolling.to_csv(report_dir / "rolling_origin.csv", index=False)
    by_matchday.to_csv(report_dir / "fresh_vs_carry_by_matchday.csv", index=False)
    (report_dir / "config.json").write_text(json.dumps({
        "seasons": args.seasons,
        "budget": args.budget,
        "mcmc_budget": budget,
        "summer_variance_scales": scales,
        "xg_source": "Understat real xG",
        "continuous_xg": True,
        "phi": 5.0,
        "tau": 100.0,
        "gamma": 0.10,
        "epsilon": 0.20,
        "market_kappa": 0.10,
        "selection": "rolling origin; prior seasons only",
        "production_policy": {
            "summer_variance_scale": 1.0,
            "carry_full_through_matchday": 12,
            "carry_cosine_fade_to_zero_at_matchday": 18,
        },
        "season_workers": min(args.workers, len(args.seasons)),
        "goal_level_prior_matches": args.goal_level_prior_matches,
        "goal_level_prior_fade_matches": args.goal_level_prior_fade_matches,
    }, indent=2), encoding="utf-8")

    print("\nPOOLED DESCRIPTIVE TOP 15")
    print(pooled.head(15).to_string(index=False,
                                    float_format=lambda x: f"{x:.5f}"))
    print("\nROLLING-ORIGIN SELECTION")
    print(rolling.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print(f"\nReport: {report_dir.resolve()}")


if __name__ == "__main__":
    main()
