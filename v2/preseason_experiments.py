"""Leak-free screening of season-transition policies.

The script separates tuning seasons from confirmation seasons. It compares
carry strength, market-value corrections, faster early evolution, current-only,
hard reset, and probability-level soft blends.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data import extract_bookmaker_probs, load_bundesliga
from mcmc import warmup_jit
from preseason_backtest import available_strategies, run_season
from real_xg import add_real_xg_columns
from xg import add_xg_columns, fit_xg_weights


SCREEN_SEASONS = ["2018/19", "2019/20", "2020/21", "2021/22"]
CONFIRM_SEASONS = ["2022/23", "2023/24", "2024/25"]

CONFIGS = {
    "carry75": dict(carry_weight=0.75, market_kappa=0.0),
    "carry50": dict(carry_weight=0.50, market_kappa=0.0),
    "level_all10": dict(carry_weight=0.75, market_kappa=0.10),
    "delta05": dict(carry_weight=0.75, market_kappa=0.10,
                    market_delta_kappa=0.05, market_level_new_only=True),
    "delta10": dict(carry_weight=0.75, market_kappa=0.10,
                    market_delta_kappa=0.10, market_level_new_only=True),
    "early2": dict(carry_weight=0.75, market_kappa=0.0,
                   early_process_multiplier=2.0,
                   early_process_half_life=6.0),
    "level_all10_early2": dict(carry_weight=0.75, market_kappa=0.10,
                               early_process_multiplier=2.0,
                               early_process_half_life=6.0),
    "delta05_early2": dict(carry_weight=0.75, market_kappa=0.10,
                           market_delta_kappa=0.05,
                           market_level_new_only=True,
                           early_process_multiplier=2.0,
                           early_process_half_life=6.0),
}

BUDGETS = {
    "screen": dict(prior_iter=1200, prior_burnin=250,
                   base_iter=800, base_burnin=180,
                   warm_iter=350, warm_burnin=70, thin=10),
    "quick": dict(prior_iter=2500, prior_burnin=500,
                  base_iter=1400, base_burnin=300,
                  warm_iter=700, warm_burnin=150, thin=10),
    "confirm": dict(prior_iter=5000, prior_burnin=1000,
                    base_iter=3000, base_burnin=600,
                    warm_iter=1500, warm_burnin=250, thin=10),
}


def _to_long(frame: pd.DataFrame, config_name: str) -> pd.DataFrame:
    id_cols = ["season", "season_game", "phase", "new_team"]
    rows = []
    for strategy in (*available_strategies(frame), "bookmaker"):
        part = frame[id_cols].copy()
        part["config"] = config_name
        part["strategy"] = strategy
        part["candidate"] = f"{config_name}:{strategy}"
        part["rps"] = frame[f"rps_{strategy}"].to_numpy()
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def _candidate_summary(long: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for candidate, group in long.groupby("candidate", sort=False):
        config, strategy = candidate.split(":", 1)
        rows.append({"candidate": candidate, "config": config,
                     "strategy": strategy, "phase": "full_season",
                     "n": group["rps"].notna().sum(), "rps": group["rps"].mean()})
        for phase, phase_group in group.groupby("phase", sort=False):
            rows.append({"candidate": candidate, "config": config,
                         "strategy": strategy, "phase": phase,
                         "n": phase_group["rps"].notna().sum(),
                         "rps": phase_group["rps"].mean()})
    return pd.DataFrame(rows).sort_values(["phase", "rps"]).reset_index(drop=True)


def _paired_comparison(long: pd.DataFrame, candidates: list[str], *,
                       seed: int = 42, n_boot: int = 10_000) -> pd.DataFrame:
    keys = ["season", "season_game"]
    wide = long[long["candidate"].isin(candidates)].pivot_table(
        index=keys, columns="candidate", values="rps", aggfunc="first")
    best = candidates[0]
    rng = np.random.default_rng(seed)
    rows = []
    for reference in candidates[1:]:
        pair = wide[[best, reference]].dropna()
        delta = pair[reference].to_numpy() - pair[best].to_numpy()
        boot = np.array([rng.choice(delta, len(delta), replace=True).mean()
                         for _ in range(n_boot)])
        rows.append({"candidate": best, "reference": reference, "n": len(delta),
                     "rps_advantage": delta.mean(),
                     "ci_low": np.quantile(boot, 0.025),
                     "ci_high": np.quantile(boot, 0.975)})
    return pd.DataFrame(rows)


def _plot(summary: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    full = summary[summary["phase"] == "full_season"].nsmallest(10, "rps")
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = ["#c62828" if x.endswith(":bookmaker") else "#2878b5"
              for x in full["candidate"]]
    bars = ax.barh(full["candidate"], full["rps"], color=colors)
    ax.invert_yaxis()
    ax.set_xlabel("Mean RPS (lower is better)")
    ax.set_title("Season-transition policy experiment")
    ax.bar_label(bars, fmt="%.4f", padding=3, fontsize=8)
    left = max(0.0, float(full["rps"].min()) - 0.01)
    ax.set_xlim(left, float(full["rps"].max()) + 0.008)
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["screen", "confirm"], default="screen")
    parser.add_argument("--seasons", nargs="+")
    parser.add_argument("--configs", nargs="+", choices=sorted(CONFIGS),
                        default=list(CONFIGS))
    parser.add_argument("--bundle-configs", nargs="+", choices=sorted(CONFIGS),
                        default=["carry75"],
                        help="Configs that also run current-only/reset/soft blends")
    parser.add_argument("--budget", choices=sorted(BUDGETS))
    parser.add_argument("--xg-source", choices=["real", "proxy"], default="real",
                        help="Use cached Understat xG or the shot-count proxy")
    parser.add_argument("--output-root", type=Path, default=Path("v2/output"))
    args = parser.parse_args()

    seasons = args.seasons or (SCREEN_SEASONS if args.stage == "screen"
                               else CONFIRM_SEASONS)
    budget_name = args.budget or ("screen" if args.stage == "screen" else "confirm")
    budget = BUDGETS[budget_name]
    earliest = min(seasons)
    latest_start = max(int(s.split("/")[0]) for s in seasons)
    df = extract_bookmaker_probs(load_bundesliga(1993, latest_start + 1,
                                                  with_extras=True))
    xg_train = df[df["Season"] < earliest]
    beta_off, beta_on = fit_xg_weights(xg_train, force=True, cache=False)
    df = add_xg_columns(df, beta_off, beta_on)
    if args.xg_source == "real":
        df = add_real_xg_columns(df)
    warmup_jit()

    frames = []
    wide_frames = []
    bookmaker_config = next(
        (name for name in args.configs if name in args.bundle_configs),
        args.configs[0],
    )
    for config_name in args.configs:
        config = CONFIGS[config_name]
        include_bundle = config_name in args.bundle_configs
        print(f"\nCONFIG {config_name}: {config}")
        for season_i, season in enumerate(seasons):
            print(f"  {season}")
            result = run_season(
                df, season,
                reset_after_games=153,
                seed=42 + season_i * 1000,
                include_current_only=include_bundle,
                blend_half_lives=(3.0, 6.0, 10.0, 17.0),
                taper_end_matchdays=(18, 25, 30),
                verbose=False,
                **budget,
                **config,
            )
            long = _to_long(result, config_name)
            if include_bundle:
                wide = result.copy()
                wide.insert(0, "config", config_name)
                wide_frames.append(wide)
            if config_name != bookmaker_config:
                long = long[long["strategy"] != "bookmaker"]
            # Fixed predictions are only a useful candidate for the base config.
            if config_name != "carry75":
                long = long[long["strategy"] != "fixed_preseason"]
            frames.append(long)

    long = pd.concat(frames, ignore_index=True)
    summary = _candidate_summary(long)
    full = summary[summary["phase"] == "full_season"].sort_values("rps")
    model_full = full[full["strategy"] != "bookmaker"]
    compare_candidates = model_full["candidate"].head(min(8, len(model_full))).tolist()
    comparisons = _paired_comparison(long, compare_candidates)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.output_root / f"preseason_experiment_{args.stage}_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    long.to_csv(report_dir / "experiment_per_match_long.csv", index=False)
    if wide_frames:
        pd.concat(wide_frames, ignore_index=True).to_csv(
            report_dir / "experiment_per_match_wide.csv", index=False)
    summary.to_csv(report_dir / "experiment_summary.csv", index=False)
    comparisons.to_csv(report_dir / "experiment_paired.csv", index=False)
    (report_dir / "config.json").write_text(json.dumps({
        "stage": args.stage, "seasons": seasons, "configs": args.configs,
        "bundle_configs": args.bundle_configs,
        "budget": budget_name, "mcmc_budget": budget,
        "xg_source": ("Understat real xG" if args.xg_source == "real"
                       else "football-data shot proxy"),
        "xg_source_counts": df["xg_source"].value_counts().to_dict()
        if "xg_source" in df else {"proxy": int(len(df))},
        "xg_weights": {"off_target": beta_off, "on_target": beta_on},
    }, indent=2), encoding="utf-8")
    _plot(summary, report_dir / "experiment_overview.png")

    print("\nTOP CANDIDATES")
    print(full[["candidate", "n", "rps"]].head(15).to_string(
        index=False, float_format=lambda x: f"{x:.5f}"))
    print("\nPAIRED AGAINST BEST")
    print(comparisons.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print(f"\nReport: {report_dir.resolve()}")


if __name__ == "__main__":
    main()
