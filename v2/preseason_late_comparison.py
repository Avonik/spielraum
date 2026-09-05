"""Legacy proxy-xG comparison; this is not the complete V2 backtest."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from backtest import walkforward_predictions
from data import extract_bookmaker_probs, load_bundesliga
from evaluation import brier_one, log_loss_one, rps_one
from market_value import team_market_values
from mcmc import warmup_jit
from xg import add_xg_columns, fit_xg_weights


MODEL_STRATEGIES = [
    "standalone_proxy_replica",
    "fixed_preseason",
    "updating_prior",
    "current_only",
    "midseason_reset",
    "soft_blend_h10",
    "soft_blend_h17",
    "cosine_taper_k18",
    "cosine_taper_k25",
    "cosine_taper_k30",
]


def _metrics(probs: np.ndarray, outcomes: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(outcomes)),
        "rps": float(np.mean([rps_one(p, int(y)) for p, y in zip(probs, outcomes)])),
        "log_loss": float(np.mean([log_loss_one(p, int(y)) for p, y in zip(probs, outcomes)])),
        "brier": float(np.mean([brier_one(p, int(y)) for p, y in zip(probs, outcomes)])),
    }


def _probs_from_wide(frame: pd.DataFrame, strategy: str) -> np.ndarray:
    return frame[[f"p_home_{strategy}", f"p_draw_{strategy}",
                  f"p_away_{strategy}"]].to_numpy(float)


def _paired_bootstrap(per_match: pd.DataFrame, *, seed: int = 42,
                      n_boot: int = 20_000) -> pd.DataFrame:
    means = per_match.groupby("strategy")["rps"].mean()
    best = means.drop("bookmaker").idxmin()
    wide = per_match.pivot_table(index=["season", "season_game"],
                                 columns="strategy", values="rps")
    rng = np.random.default_rng(seed)
    rows = []
    for reference in means.sort_values().index:
        if reference == best:
            continue
        pair = wide[[best, reference]].dropna()
        delta = pair[reference].to_numpy() - pair[best].to_numpy()
        boot = np.array([rng.choice(delta, len(delta), replace=True).mean()
                         for _ in range(n_boot)])
        rows.append({"strategy": best, "reference": reference, "n": len(delta),
                     "rps_advantage": delta.mean(),
                     "ci_low": np.quantile(boot, 0.025),
                     "ci_high": np.quantile(boot, 0.975)})
    return pd.DataFrame(rows)


def _plot(summary: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    pooled = summary[summary["season"] == "POOLED"].sort_values("rps")
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    colors = ["#c62828" if s == "bookmaker" else
              "#6a1b9a" if s == "standalone_proxy_replica" else "#2878b5"
              for s in pooled["strategy"]]
    bars = axes[0].barh(pooled["strategy"], pooled["rps"], color=colors)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("RPS (lower is better)")
    axes[0].set_title("Common late holdout")
    axes[0].bar_label(bars, fmt="%.4f", padding=3, fontsize=8)
    axes[0].set_xlim(max(0, pooled["rps"].min() - 0.01),
                     pooled["rps"].max() + 0.008)

    selected = ["bookmaker", "standalone_proxy_replica", "updating_prior",
                "soft_blend_h10", "soft_blend_h17", "cosine_taper_k30"]
    seasonal = summary[(summary["season"] != "POOLED") &
                       summary["strategy"].isin(selected)]
    for strategy, group in seasonal.groupby("strategy", sort=False):
        axes[1].plot(group["season"], group["rps"], marker="o", label=strategy)
    axes[1].set_ylabel("RPS")
    axes[1].set_title("Late-holdout RPS by season")
    axes[1].legend(fontsize=8)
    fig.suptitle("Standalone model vs. season-transition policies")
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("v2/output"))
    args = parser.parse_args()

    wide_path = args.experiment_dir / "experiment_per_match_wide.csv"
    if not wide_path.is_file():
        raise FileNotFoundError(f"Missing wide predictions: {wide_path}")
    wide_all = pd.read_csv(wide_path, parse_dates=["Date"])
    seasons = list(dict.fromkeys(wide_all["season"].astype(str)))
    earliest = min(seasons)
    latest_start = max(int(s.split("/")[0]) for s in seasons)

    df = extract_bookmaker_probs(load_bundesliga(1993, latest_start + 1,
                                                  with_extras=True))
    beta_off, beta_on = fit_xg_weights(df[df["Season"] < earliest],
                                       force=True, cache=False)
    df = add_xg_columns(df, beta_off, beta_on)
    warmup_jit()

    metric_rows = []
    match_rows = []
    starts = []
    pooled: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        strategy: [] for strategy in (*MODEL_STRATEGIES, "bookmaker")}

    for season_i, season in enumerate(seasons):
        print(f"Standalone walk-forward: {season}")
        market_values = team_market_values(season)
        standalone = walkforward_predictions(
            df, season,
            use_xg=True, tau=100.0, gamma=0.10, eps=0.20,
            holdout_frac=0.30,
            base_iter=3000, base_burnin=600,
            warm_iter=1500, warm_burnin=250, thin=10,
            proposal_sd=0.06, seed=42 + season_i * 1000,
            verbose=False, n_chains=1,
            continuous_xg=True, phi=5.0,
            market_values=market_values, market_kappa=0.10,
        )
        source = standalone["df_season"]
        wide = (wide_all[wide_all["season"] == season]
                .sort_values("season_game").reset_index(drop=True))
        if not (source["HomeTeam"].to_numpy() == wide["HomeTeam"].to_numpy()).all():
            raise RuntimeError(f"Home-team alignment failed for {season}")
        if not (source["AwayTeam"].to_numpy() == wide["AwayTeam"].to_numpy()).all():
            raise RuntimeError(f"Away-team alignment failed for {season}")

        probs_map = {"standalone_proxy_replica": standalone["probs_model"]}
        for strategy in MODEL_STRATEGIES[1:]:
            probs_map[strategy] = _probs_from_wide(wide, strategy)
        probs_map["bookmaker"] = _probs_from_wide(wide, "bookmaker")
        outcomes = wide["outcome"].to_numpy(int)
        common = np.arange(len(wide)) >= int(standalone["cutoff"])
        for probs in probs_map.values():
            common &= np.all(np.isfinite(probs), axis=1)
        indices = np.where(common)[0]
        if not len(indices):
            raise RuntimeError(f"No common holdout rows for {season}")

        first = int(indices[0])
        starts.append({"season": season, "first_season_game": first + 1,
                       "approx_matchday": first // 9 + 1,
                       "first_date": str(pd.Timestamp(wide.loc[first, "Date"]).date()),
                       "n_games": len(indices)})
        for strategy, probs in probs_map.items():
            metrics = _metrics(probs[indices], outcomes[indices])
            metric_rows.append({"season": season, "strategy": strategy, **metrics})
            pooled[strategy].append((probs[indices], outcomes[indices]))
            for idx in indices:
                match_rows.append({
                    "season": season,
                    "season_game": int(idx + 1),
                    "strategy": strategy,
                    "rps": rps_one(probs[idx], int(outcomes[idx])),
                    "log_loss": log_loss_one(probs[idx], int(outcomes[idx])),
                    "brier": brier_one(probs[idx], int(outcomes[idx])),
                })

    for strategy, chunks in pooled.items():
        probs = np.concatenate([chunk[0] for chunk in chunks])
        outcomes = np.concatenate([chunk[1] for chunk in chunks])
        metric_rows.append({"season": "POOLED", "strategy": strategy,
                            **_metrics(probs, outcomes)})

    summary = pd.DataFrame(metric_rows)
    per_match = pd.DataFrame(match_rows)
    paired = _paired_bootstrap(per_match)
    starts_df = pd.DataFrame(starts)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.output_root / f"preseason_late_comparison_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    summary.to_csv(report_dir / "late_comparison_summary.csv", index=False)
    per_match.to_csv(report_dir / "late_comparison_per_match.csv", index=False)
    paired.to_csv(report_dir / "late_comparison_paired.csv", index=False)
    starts_df.to_csv(report_dir / "late_holdout_starts.csv", index=False)
    (report_dir / "config.json").write_text(json.dumps({
        "source_experiment": str(args.experiment_dir),
        "seasons": seasons,
        "standalone_holdout_frac": 0.30,
        "xg_source": "football-data shot proxy",
        "xg_weights": {"off_target": beta_off, "on_target": beta_on},
        "standalone_budget": {"base_iter": 3000, "base_burnin": 600,
                              "warm_iter": 1500, "warm_burnin": 250,
                              "thin": 10},
    }, indent=2), encoding="utf-8")
    _plot(summary, report_dir / "late_comparison.png")

    print("\nHOLDOUT STARTS")
    print(starts_df.to_string(index=False))
    print("\nPOOLED COMMON-HOLDOUT METRICS")
    print(summary[summary["season"] == "POOLED"].sort_values("rps").to_string(
        index=False, float_format=lambda x: f"{x:.5f}"))
    print("\nPAIRED RPS AGAINST BEST MODEL")
    print(paired.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print(f"\nReport: {report_dir.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
