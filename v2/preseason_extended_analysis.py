"""Robustness report for a frozen extended preseason-policy backtest."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


FULL_MODELS = [
    "soft_blend_h17",
    "soft_blend_h10",
    "cosine_taper_k30",
    "current_only",
    "updating_prior",
    "midseason_reset",
]
LATE_MODELS = [
    "soft_blend_h17",
    "soft_blend_h10",
    "cosine_taper_k30",
    "current_only",
    "updating_prior",
    "fixed_preseason",
    "standalone_original",
]


def _bootstrap_mean(values: np.ndarray, rng: np.random.Generator,
                    n_boot: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    chunks = []
    for start in range(0, n_boot, 1_000):
        size = min(1_000, n_boot - start)
        indices = rng.integers(0, len(values), size=(size, len(values)))
        chunks.append(values[indices].mean(axis=1))
    return np.concatenate(chunks)


def _paired_rows(frame: pd.DataFrame, focus: str, references: list[str],
                 period: str, *, season_clustered: bool,
                 rng: np.random.Generator, n_boot: int) -> list[dict]:
    wide = frame.pivot_table(index=["season", "season_game"],
                             columns="strategy", values="rps")
    rows = []
    for reference in references:
        pair = wide[[focus, reference]].dropna()
        delta = pair[reference] - pair[focus]
        if season_clustered:
            sample_values = delta.groupby(level="season").mean().to_numpy()
            method = "season_cluster"
        else:
            sample_values = delta.to_numpy()
            method = "match"
        boot = _bootstrap_mean(sample_values, rng, n_boot)
        rows.append({
            "sample": period,
            "focus": focus,
            "reference": reference,
            "n_matches": len(delta),
            "n_seasons": delta.index.get_level_values("season").nunique(),
            "rps_advantage": float(delta.mean()),
            "ci_low": float(np.quantile(boot, 0.025)),
            "ci_high": float(np.quantile(boot, 0.975)),
            "bootstrap": method,
        })
    return rows


def _period_summary(frame: pd.DataFrame, sample: str) -> pd.DataFrame:
    return (frame.groupby("strategy", as_index=False)["rps"]
            .agg(n="count", rps="mean")
            .assign(sample=sample)[["sample", "strategy", "n", "rps"]])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--late-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("v2/output"))
    parser.add_argument("--holdout-season", default="2025/26")
    parser.add_argument("--n-boot", type=int, default=20_000)
    args = parser.parse_args()

    full = pd.read_csv(args.experiment_dir / "experiment_per_match_long.csv")
    full = full[full["strategy"].isin([*FULL_MODELS, "bookmaker"])].copy()
    late = pd.read_csv(args.late_dir / "late_comparison_per_match.csv")
    late = late[late["strategy"].isin([*LATE_MODELS, "bookmaker"])].copy()

    full_by_season = (full.groupby(["season", "strategy"], as_index=False)
                      .agg(n=("rps", "count"), rps=("rps", "mean")))
    late_by_season = (late.groupby(["season", "strategy"], as_index=False)
                      .agg(n=("rps", "count"), rps=("rps", "mean")))

    rng = np.random.default_rng(20260728)
    paired = []
    summaries = []
    for label, source, models in [
        ("full", full, FULL_MODELS),
        ("late", late, LATE_MODELS),
    ]:
        samples = {
            f"{label}_all": source,
            f"{label}_pre_holdout": source[source["season"] != args.holdout_season],
            f"{label}_holdout": source[source["season"] == args.holdout_season],
        }
        for sample, part in samples.items():
            summaries.append(_period_summary(part, sample))
            paired.extend(_paired_rows(
                part,
                "soft_blend_h17",
                [model for model in [*models[1:], "bookmaker"]
                 if model in set(part["strategy"])],
                sample,
                season_clustered=part["season"].nunique() > 1,
                rng=rng,
                n_boot=args.n_boot,
            ))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.output_root / f"preseason_extended_analysis_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    full_by_season.to_csv(report_dir / "full_by_season.csv", index=False)
    late_by_season.to_csv(report_dir / "late_by_season.csv", index=False)
    pd.concat(summaries, ignore_index=True).to_csv(
        report_dir / "period_summary.csv", index=False)
    paired_df = pd.DataFrame(paired)
    paired_df.to_csv(report_dir / "paired_uncertainty.csv", index=False)

    print("FULL-SEASON HOLDOUT")
    period = pd.concat(summaries, ignore_index=True)
    print(period[period["sample"] == "full_holdout"].sort_values("rps")
          .to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print("\nH17 PAIRED UNCERTAINTY")
    selected = paired_df[
        paired_df["sample"].isin(["full_all", "full_holdout", "late_all",
                                  "late_holdout"])
    ]
    print(selected.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print(f"\nReport: {report_dir.resolve()}")


if __name__ == "__main__":
    main()
