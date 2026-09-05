"""Compare preseason transitions with saved full-V2 walk-forward forecasts.

The V2 probabilities are read from a completed ``backtest_multiseason.py``
run, so real xG, high MCMC budget and multi-chain settings remain exactly the
ones used by that run. The comparison starts only where those V2 forecasts
exist (roughly matchday 24).
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation import brier_one, log_loss_one, rps_one


TRANSITION_STRATEGIES = [
    "soft_blend_h10",
    "soft_blend_h17",
    "cosine_taper_k30",
    "current_only",
    "updating_prior",
]


def _metrics(probs: np.ndarray, outcomes: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(outcomes)),
        "rps": float(np.mean([rps_one(p, int(y)) for p, y in zip(probs, outcomes)])),
        "log_loss": float(np.mean([log_loss_one(p, int(y))
                                   for p, y in zip(probs, outcomes)])),
        "brier": float(np.mean([brier_one(p, int(y))
                                for p, y in zip(probs, outcomes)])),
    }


def _bootstrap(per_match: pd.DataFrame, *, n_boot: int = 20_000,
               seed: int = 42) -> pd.DataFrame:
    means = per_match.groupby("strategy")["rps"].mean()
    focus = means.drop("bookmaker").idxmin()
    wide = per_match.pivot(index=["season", "season_game"],
                           columns="strategy", values="rps")
    rng = np.random.default_rng(seed)
    rows = []
    for reference in means.sort_values().index:
        if reference == focus:
            continue
        pair = wide[[focus, reference]].dropna()
        delta = pair[reference].to_numpy() - pair[focus].to_numpy()
        boot = np.array([
            rng.choice(delta, len(delta), replace=True).mean()
            for _ in range(n_boot)
        ])
        season_delta = (pair[reference] - pair[focus]).groupby(level="season").mean()
        season_boot = np.array([
            rng.choice(season_delta, len(season_delta), replace=True).mean()
            for _ in range(n_boot)
        ])
        rows.append({
            "strategy": focus,
            "reference": reference,
            "n": len(delta),
            "rps_advantage": float(delta.mean()),
            "ci_low": float(np.quantile(boot, 0.025)),
            "ci_high": float(np.quantile(boot, 0.975)),
            "season_ci_low": float(np.quantile(season_boot, 0.025)),
            "season_ci_high": float(np.quantile(season_boot, 0.975)),
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--v2-run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("v2/output"))
    args = parser.parse_args()

    experiment_config = json.loads(
        (args.experiment_dir / "config.json").read_text(encoding="utf-8"))
    if experiment_config.get("xg_source") != "Understat real xG":
        raise ValueError("Transition experiment must use Understat real xG.")

    transitions = pd.read_csv(
        args.experiment_dir / "experiment_per_match_wide.csv")
    v2 = pd.read_csv(args.v2_run_dir / "multiseason_per_match_rps.csv")
    required = {
        "season", "season_game", "actual_result_idx",
        "p_home_v2", "p_draw_v2", "p_away_v2",
        "p_home_book", "p_draw_book", "p_away_book",
    }
    missing = required - set(v2.columns)
    if missing:
        raise ValueError(f"Saved V2 run lacks columns: {sorted(missing)}")

    common = v2.merge(
        transitions,
        on=["season", "season_game"],
        how="inner",
        validate="one_to_one",
        suffixes=("_saved_v2", "_transition"),
    )
    if len(common) != len(v2):
        raise RuntimeError(f"Only aligned {len(common)}/{len(v2)} V2 forecasts.")
    if not np.array_equal(common["actual_result_idx"].to_numpy(int),
                          common["outcome"].to_numpy(int)):
        raise RuntimeError("Outcome alignment failed.")

    probability_columns = {
        "v2_full": ["p_home_v2", "p_draw_v2", "p_away_v2"],
        "bookmaker": ["p_home_book", "p_draw_book", "p_away_book"],
    }
    for strategy in TRANSITION_STRATEGIES:
        probability_columns[strategy] = [
            f"p_home_{strategy}", f"p_draw_{strategy}", f"p_away_{strategy}",
        ]

    metric_rows = []
    match_rows = []
    for season, season_frame in common.groupby("season", sort=False):
        outcomes = season_frame["outcome"].to_numpy(int)
        for strategy, columns in probability_columns.items():
            probs = season_frame[columns].to_numpy(float)
            metric_rows.append({"season": season, "strategy": strategy,
                                **_metrics(probs, outcomes)})
            for game, probability, outcome in zip(
                    season_frame["season_game"], probs, outcomes):
                match_rows.append({
                    "season": season,
                    "season_game": int(game),
                    "strategy": strategy,
                    "rps": rps_one(probability, int(outcome)),
                    "log_loss": log_loss_one(probability, int(outcome)),
                    "brier": brier_one(probability, int(outcome)),
                })

    per_match = pd.DataFrame(match_rows)
    for strategy, strategy_frame in per_match.groupby("strategy", sort=False):
        metric_rows.append({
            "season": "POOLED",
            "strategy": strategy,
            "n": len(strategy_frame),
            "rps": strategy_frame["rps"].mean(),
            "log_loss": strategy_frame["log_loss"].mean(),
            "brier": strategy_frame["brier"].mean(),
        })
    summary = pd.DataFrame(metric_rows)
    paired = _bootstrap(per_match)

    # End-to-end production policies: transition forecast before the saved V2
    # holdout starts, then use the full V2 probabilities from that point on.
    v2_probability_cols = ["p_home_v2", "p_draw_v2", "p_away_v2"]
    v2_lookup = v2[["season", "season_game", *v2_probability_cols]]
    full = transitions.merge(v2_lookup, on=["season", "season_game"],
                             how="left", validate="one_to_one")
    cutoffs = v2.groupby("season")["season_game"].min().to_dict()
    full["v2_available"] = full.apply(
        lambda row: int(row["season_game"]) >= int(cutoffs.get(row["season"], 10**9)),
        axis=1,
    )
    if full.loc[full["v2_available"], v2_probability_cols].isna().any().any():
        raise RuntimeError("Saved V2 probabilities are missing after a holdout start.")

    early_rows = []
    handoff_rows = []
    for season, season_frame in full.groupby("season", sort=False):
        outcomes = season_frame["outcome"].to_numpy(int)
        available = season_frame["v2_available"].to_numpy(bool)
        v2_probs = season_frame[v2_probability_cols].to_numpy(float)
        bookmaker_probs = season_frame[
            ["p_home_bookmaker", "p_draw_bookmaker", "p_away_bookmaker"]
        ].to_numpy(float)
        for strategy in TRANSITION_STRATEGIES:
            transition_probs = season_frame[
                [f"p_home_{strategy}", f"p_draw_{strategy}",
                 f"p_away_{strategy}"]
            ].to_numpy(float)
            early_metrics = _metrics(transition_probs[~available], outcomes[~available])
            early_rows.append({"season": season, "strategy": strategy,
                               **early_metrics})
            handoff_probs = np.where(available[:, None], v2_probs,
                                     transition_probs)
            handoff_name = f"{strategy}_to_v2"
            for game, probability, outcome in zip(
                    season_frame["season_game"], handoff_probs, outcomes):
                handoff_rows.append({
                    "season": season,
                    "season_game": int(game),
                    "strategy": handoff_name,
                    "rps": rps_one(probability, int(outcome)),
                    "log_loss": log_loss_one(probability, int(outcome)),
                    "brier": brier_one(probability, int(outcome)),
                })
        early_rows.append({"season": season, "strategy": "bookmaker",
                           **_metrics(bookmaker_probs[~available],
                                      outcomes[~available])})
        for game, probability, outcome in zip(
                season_frame["season_game"], bookmaker_probs, outcomes):
            handoff_rows.append({
                "season": season,
                "season_game": int(game),
                "strategy": "bookmaker",
                "rps": rps_one(probability, int(outcome)),
                "log_loss": log_loss_one(probability, int(outcome)),
                "brier": brier_one(probability, int(outcome)),
            })

    early_summary = pd.DataFrame(early_rows)
    for strategy, strategy_frame in early_summary.groupby("strategy", sort=False):
        early_summary = pd.concat([early_summary, pd.DataFrame([{
            "season": "POOLED", "strategy": strategy,
            "n": int(strategy_frame["n"].sum()),
            "rps": float(np.average(strategy_frame["rps"],
                                    weights=strategy_frame["n"])),
            "log_loss": float(np.average(strategy_frame["log_loss"],
                                         weights=strategy_frame["n"])),
            "brier": float(np.average(strategy_frame["brier"],
                                      weights=strategy_frame["n"])),
        }])], ignore_index=True)

    handoff_per_match = pd.DataFrame(handoff_rows)
    handoff_summary_rows = []
    for strategy, strategy_frame in handoff_per_match.groupby("strategy", sort=False):
        handoff_summary_rows.append({
            "strategy": strategy,
            "n": len(strategy_frame),
            "rps": strategy_frame["rps"].mean(),
            "log_loss": strategy_frame["log_loss"].mean(),
            "brier": strategy_frame["brier"].mean(),
        })
    handoff_summary = pd.DataFrame(handoff_summary_rows)
    handoff_paired = _bootstrap(handoff_per_match)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.output_root / f"preseason_v2_late_comparison_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    summary.to_csv(report_dir / "v2_late_summary.csv", index=False)
    per_match.to_csv(report_dir / "v2_late_per_match.csv", index=False)
    paired.to_csv(report_dir / "v2_late_paired.csv", index=False)
    early_summary.to_csv(report_dir / "early_before_v2_summary.csv", index=False)
    handoff_summary.to_csv(report_dir / "handoff_summary.csv", index=False)
    handoff_per_match.to_csv(report_dir / "handoff_per_match.csv", index=False)
    handoff_paired.to_csv(report_dir / "handoff_paired.csv", index=False)
    (report_dir / "config.json").write_text(json.dumps({
        "transition_experiment": str(args.experiment_dir),
        "saved_v2_run": str(args.v2_run_dir),
        "comparison_starts_at_saved_v2_forecasts": True,
        "n_common_matches": int(len(common)),
        "transition_mcmc_budget": experiment_config.get("mcmc_budget"),
        "transition_xg_source": experiment_config.get("xg_source"),
    }, indent=2), encoding="utf-8")

    print(summary[summary["season"] == "POOLED"].sort_values("rps")
          .to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print("\nPAIRED AGAINST BEST MODEL")
    print(paired.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print("\nEARLY WINDOW BEFORE V2 STARTS")
    print(early_summary[early_summary["season"] == "POOLED"].sort_values("rps")
          .to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print("\nFULL-SEASON HANDOFF POLICIES")
    print(handoff_summary.sort_values("rps").to_string(
        index=False, float_format=lambda x: f"{x:.5f}"))
    print("\nHANDOFF PAIRED AGAINST BEST MODEL")
    print(handoff_paired.to_string(index=False,
                                  float_format=lambda x: f"{x:.5f}"))
    print(f"\nReport: {report_dir.resolve()}")


if __name__ == "__main__":
    main()
