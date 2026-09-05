"""Fast preseason-to-matchday-34 backtest for three prior policies.

Strategies:
  fixed_preseason  - never update the previous-season strengths.
  updating_prior   - use them only as a start prior, then update after every date.
  midseason_reset  - same as updating_prior until 153 played matches, then refit
                     using target-season observations only.

The default is deliberately a quick diagnostic, not a publication-grade MCMC
run. Use ``--full`` for a larger sampling budget.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from data import extract_bookmaker_probs, load_bundesliga
from evaluation import (
    bookmaker_probs_from_df,
    evaluate_predictions,
    outcome_index,
    rps_one,
)
from market_value import team_market_values
from mcmc import run_mcmc, warmup_jit
from model import MAX_GOALS, PRIOR_VAR, build_league, predict_outcome_probs
from preseason import (
    fit_preseason_state,
    previous_season_label,
    standardized_market_value_signal,
)
from xg import add_xg_columns, fit_xg_weights


DEFAULT_SEASONS = ["2022/23", "2023/24", "2024/25"]
CORE_STRATEGIES = ("fixed_preseason", "updating_prior")


def cosine_taper_weights(matchdays: np.ndarray, end_matchday: int) -> np.ndarray:
    """Smoothly decay from one on MD1 to exactly zero on ``end_matchday``."""
    matchdays = np.asarray(matchdays, dtype=float)
    progress = np.clip(
        (matchdays - 1.0) / max(1.0, float(end_matchday - 1)), 0.0, 1.0)
    weights = 0.5 * (1.0 + np.cos(np.pi * progress))
    return np.where(matchdays >= end_matchday, 0.0, weights)


def _flat_init(league, strengths: dict[str, tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    attack = np.zeros(int(league.team_start[-1]), dtype=float)
    defense = np.zeros_like(attack)
    for i, team in enumerate(league.teams):
        a, d = strengths.get(team, (0.0, 0.0))
        attack[league.team_start[i]:league.team_start[i + 1]] = a
        defense[league.team_start[i]:league.team_start[i + 1]] = d
    return attack, defense


def _last_strengths(samples: dict, league, *,
                    fallback: dict[str, tuple[float, float]] | None = None
                    ) -> dict[str, tuple[float, float]]:
    out = dict(fallback or {})
    for i, team in enumerate(league.teams):
        attack = np.mean([sample[i][-1] for sample in samples["attack"]])
        defense = np.mean([sample[i][-1] for sample in samples["defense"]])
        out[team] = (float(attack), float(defense))
    return out


def _predict_games(games: pd.DataFrame, strengths: dict[str, tuple[float, float]],
                   c_x: float, c_y: float, gamma: float, epsilon: float,
                   probs: np.ndarray) -> None:
    for idx, row in games.iterrows():
        home, away = row["HomeTeam"], row["AwayTeam"]
        if home not in strengths or away not in strengths:
            continue
        ah, dh = strengths[home]
        aa, da = strengths[away]
        probs[idx] = predict_outcome_probs(
            ah, dh, aa, da, c_x, c_y,
            gamma=gamma, eps=epsilon, max_k=MAX_GOALS,
        )


def run_season(
    df: pd.DataFrame,
    season: str,
    *,
    carry_weight: float,
    market_kappa: float,
    reset_after_games: int,
    prior_iter: int,
    prior_burnin: int,
    base_iter: int,
    base_burnin: int,
    warm_iter: int,
    warm_burnin: int,
    thin: int,
    seed: int,
    market_delta_kappa: float = 0.0,
    market_level_new_only: bool = False,
    early_process_multiplier: float = 1.0,
    early_process_half_life: float = 6.0,
    include_current_only: bool = True,
    blend_half_lives: tuple[float, ...] = (3.0, 6.0, 10.0),
    taper_end_matchdays: tuple[int, ...] = (18, 25, 30),
    verbose: bool = True,
) -> pd.DataFrame:
    season_df = (df[df["Season"] == season]
                 .sort_values("Date").reset_index(drop=True))
    teams = sorted(set(season_df["HomeTeam"]) | set(season_df["AwayTeam"]))
    try:
        market_values = team_market_values(season)
    except (FileNotFoundError, ValueError):
        market_values = {}
    try:
        previous_market_values = team_market_values(previous_season_label(season))
    except (FileNotFoundError, ValueError):
        previous_market_values = {}
    delta_signal = standardized_market_value_signal(
        market_values, teams, previous_values=previous_market_values,
    ) if market_delta_kappa != 0.0 else {}

    state = fit_preseason_state(
        df,
        season,
        target_teams=teams,
        carry_weight=carry_weight,
        market_kappa=market_kappa,
        market_delta_kappa=market_delta_kappa,
        market_delta_signal=delta_signal,
        market_level_new_only=market_level_new_only,
        early_process_multiplier=early_process_multiplier,
        early_process_half_life=early_process_half_life,
        n_iter=prior_iter,
        burnin=prior_burnin,
        thin=thin,
        seed=seed,
        verbose=False,
    )
    fixed_strengths = state.effective_strengths(market_values or None)
    n = len(season_df)
    predictions = {name: np.full((n, 3), np.nan) for name in CORE_STRATEGIES}
    if include_current_only:
        predictions["current_only"] = np.full((n, 3), np.nan)
    warm_update = None
    warm_current = None
    dates = sorted(season_df["Date"].unique())
    t0 = time.time()

    for date_i, date in enumerate(dates):
        prefix = season_df[season_df["Date"] < date]
        games = season_df[season_df["Date"] == date]
        _predict_games(games, fixed_strengths, state.c_x, state.c_y,
                       state.gamma, state.epsilon, predictions["fixed_preseason"])

        if prefix.empty:
            update_strengths = fixed_strengths
        else:
            league = build_league(prefix, **state.league_kwargs(market_values or None))
            init_a, init_d = _flat_init(
                league, fixed_strengths if warm_update is None else warm_update)
            samples = run_mcmc(
                league,
                n_iter=base_iter if warm_update is None else warm_iter,
                burnin=base_burnin if warm_update is None else warm_burnin,
                thin=thin,
                proposal_sd=0.06,
                seed=seed + date_i,
                verbose=False,
                init_attack=init_a,
                init_defense=init_d,
            )
            update_strengths = _last_strengths(samples, league,
                                                fallback=fixed_strengths)
            warm_update = update_strengths
        _predict_games(games, update_strengths, state.c_x, state.c_y,
                       state.gamma, state.epsilon, predictions["updating_prior"])

        if include_current_only:
            # No carried or market-value team prior: target-season evidence only.
            if prefix.empty:
                current_strengths = {team: (0.0, 0.0) for team in teams}
            else:
                current_league = build_league(
                    prefix,
                    use_xg=state.use_xg,
                    tau=state.tau,
                    gamma=state.gamma,
                    epsilon=state.epsilon,
                    continuous_xg=state.continuous_xg,
                    phi=state.phi,
                    initial_prior_var=PRIOR_VAR,
                    c_x_override=state.c_x,
                    c_y_override=state.c_y,
                    early_process_multiplier=early_process_multiplier,
                    early_process_half_life=early_process_half_life,
                )
                if warm_current is None:
                    init_a = init_d = None
                    n_iter, burnin = base_iter, base_burnin
                else:
                    init_a, init_d = _flat_init(current_league, warm_current)
                    n_iter, burnin = warm_iter, warm_burnin
                samples = run_mcmc(
                    current_league,
                    n_iter=n_iter,
                    burnin=burnin,
                    thin=thin,
                    proposal_sd=0.06,
                    seed=seed + 10_000 + date_i,
                    verbose=False,
                    init_attack=init_a,
                    init_defense=init_d,
                )
                current_strengths = _last_strengths(
                    samples, current_league,
                    fallback={team: (0.0, 0.0) for team in teams},
                )
                warm_current = current_strengths
            _predict_games(games, current_strengths, state.c_x, state.c_y,
                           state.gamma, state.epsilon,
                           predictions["current_only"])

        if verbose and ((date_i + 1) % 10 == 0 or date_i + 1 == len(dates)):
            print(f"    {season}: {date_i + 1:>2}/{len(dates)} dates, "
                  f"{time.time() - t0:.1f}s")

    if include_current_only:
        reset_mask = np.arange(n) >= reset_after_games
        predictions["midseason_reset"] = np.where(
            reset_mask[:, None], predictions["current_only"],
            predictions["updating_prior"],
        )
        matchday = np.arange(n) // 9 + 1
        for half_life in blend_half_lives:
            weight = 0.5 ** ((matchday - 1) / float(half_life))
            tag = f"soft_blend_h{float(half_life):g}".replace(".", "p")
            predictions[tag] = (
                weight[:, None] * predictions["updating_prior"]
                + (1.0 - weight[:, None]) * predictions["current_only"]
            )
        for end_matchday in taper_end_matchdays:
            weight = cosine_taper_weights(matchday, end_matchday)
            tag = f"cosine_taper_k{int(end_matchday)}"
            predictions[tag] = (
                weight[:, None] * predictions["updating_prior"]
                + (1.0 - weight[:, None]) * predictions["current_only"]
            )

    bookmaker = bookmaker_probs_from_df(season_df)
    outcomes = np.array([
        outcome_index(int(row.FTHG), int(row.FTAG))
        for row in season_df.itertuples()
    ])
    phase = np.where(np.arange(n) < 45, "matchdays_1_5",
                     np.where(np.arange(n) < reset_after_games,
                              "matchdays_6_17", "matchdays_18_34"))
    result = season_df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].copy()
    result.insert(0, "season", season)
    result["season_game"] = np.arange(1, n + 1)
    result["phase"] = phase
    result["outcome"] = outcomes
    for strategy, probs in predictions.items():
        result[f"p_home_{strategy}"] = probs[:, 0]
        result[f"p_draw_{strategy}"] = probs[:, 1]
        result[f"p_away_{strategy}"] = probs[:, 2]
        result[f"rps_{strategy}"] = [rps_one(p, y) for p, y in zip(probs, outcomes)]
    result["p_home_bookmaker"] = bookmaker[:, 0]
    result["p_draw_bookmaker"] = bookmaker[:, 1]
    result["p_away_bookmaker"] = bookmaker[:, 2]
    result["rps_bookmaker"] = [
        rps_one(p, y) if np.all(np.isfinite(p)) else np.nan
        for p, y in zip(bookmaker, outcomes)
    ]
    result["new_team"] = result["HomeTeam"].isin(state.new_teams) | \
        result["AwayTeam"].isin(state.new_teams)
    return result


def available_strategies(per_match: pd.DataFrame) -> list[str]:
    return [col.removeprefix("rps_") for col in per_match.columns
            if col.startswith("rps_") and col != "rps_bookmaker"]


def summarise(per_match: pd.DataFrame) -> pd.DataFrame:
    strategies = available_strategies(per_match)
    rows = []
    for (season, phase), group in per_match.groupby(["season", "phase"], sort=False):
        for strategy in (*strategies, "bookmaker"):
            values = group[f"rps_{strategy}"].dropna()
            rows.append({"season": season, "phase": phase, "strategy": strategy,
                         "n": len(values), "rps": values.mean()})
    for strategy in (*strategies, "bookmaker"):
        values = per_match[f"rps_{strategy}"].dropna()
        rows.append({"season": "POOLED", "phase": "full_season",
                     "strategy": strategy, "n": len(values), "rps": values.mean()})
    for phase, group in per_match.groupby("phase", sort=False):
        for strategy in (*strategies, "bookmaker"):
            values = group[f"rps_{strategy}"].dropna()
            rows.append({"season": "POOLED", "phase": phase,
                         "strategy": strategy, "n": len(values),
                         "rps": values.mean()})
    return pd.DataFrame(rows)


def paired_comparisons(per_match: pd.DataFrame, *, seed: int = 42,
                       n_boot: int = 10_000) -> pd.DataFrame:
    """Paired RPS deltas; positive means the first named strategy is better."""
    rng = np.random.default_rng(seed)
    specs = [
        ("updating_prior", "fixed_preseason", "full_season"),
        ("midseason_reset", "updating_prior", "full_season"),
        ("midseason_reset", "updating_prior", "matchdays_18_34"),
        ("bookmaker", "midseason_reset", "full_season"),
    ]
    rows = []
    for better, reference, phase in specs:
        group = per_match if phase == "full_season" else per_match[per_match["phase"] == phase]
        delta = (group[f"rps_{reference}"] - group[f"rps_{better}"]).dropna().to_numpy()
        boot = np.array([
            rng.choice(delta, len(delta), replace=True).mean()
            for _ in range(n_boot)
        ])
        rows.append({
            "strategy": better,
            "reference": reference,
            "phase": phase,
            "n": len(delta),
            "rps_advantage": delta.mean(),
            "ci_low": np.quantile(boot, 0.025),
            "ci_high": np.quantile(boot, 0.975),
        })
    return pd.DataFrame(rows)


def _plot(per_match: pd.DataFrame, summary: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    phases = ["matchdays_1_5", "matchdays_6_17", "matchdays_18_34"]
    candidates = ["fixed_preseason", "updating_prior", "midseason_reset",
                  "soft_blend_h6", "bookmaker"]
    strategies = [s for s in candidates if f"rps_{s}" in per_match]
    pooled = []
    for phase in phases:
        group = per_match[per_match["phase"] == phase]
        pooled.append([group[f"rps_{s}"].mean() for s in strategies])
    x = np.arange(len(phases))
    width = 0.8 / len(strategies)
    label_map = {"fixed_preseason": "Fixed preseason",
                 "updating_prior": "Updating prior",
                 "midseason_reset": "Midseason reset",
                 "soft_blend_h6": "Soft blend (h=6)",
                 "bookmaker": "Bookmaker"}
    labels = [label_map[s] for s in strategies]
    for i, label in enumerate(labels):
        offset = (i - (len(labels) - 1) / 2) * width
        axes[0].bar(x + offset, np.array(pooled)[:, i], width, label=label)
    axes[0].set_xticks(x, ["MD 1-5", "MD 6-17", "MD 18-34"])
    axes[0].set_ylabel("Mean RPS (lower is better)")
    axes[0].set_title("Performance by season phase")
    axes[0].legend(fontsize=8)

    ordered = per_match.sort_values(["season", "season_game"]).reset_index(drop=True)
    for strategy, label in zip(strategies, labels):
        axes[1].plot(ordered[f"rps_{strategy}"].expanding().mean(), label=label)
    axes[1].set_xlabel("Pooled chronological matches")
    axes[1].set_ylabel("Cumulative mean RPS")
    axes[1].set_title("Cumulative quick-backtest result")
    axes[1].legend(fontsize=8)
    fig.suptitle("Preseason strength policy backtest (proxy xG, quick MCMC)")
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS)
    parser.add_argument("--carry-weight", type=float, default=0.75)
    parser.add_argument("--market-kappa", type=float, default=0.10)
    parser.add_argument("--reset-after-games", type=int, default=153)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    return parser


def main() -> None:
    args = _parser().parse_args()
    earliest = min(args.seasons)
    latest_start = max(int(s.split("/")[0]) for s in args.seasons)
    df = extract_bookmaker_probs(load_bundesliga(1993, latest_start + 1,
                                                  with_extras=True))
    xg_train = df[df["Season"] < earliest]
    beta_off, beta_on = fit_xg_weights(xg_train, force=True, cache=False)
    df = add_xg_columns(df, beta_off, beta_on)
    budgets = ({"prior_iter": 12_000, "prior_burnin": 2_500,
                "base_iter": 6_000, "base_burnin": 1_200,
                "warm_iter": 3_000, "warm_burnin": 500, "thin": 10}
               if args.full else
               {"prior_iter": 2_500, "prior_burnin": 500,
                "base_iter": 1_400, "base_burnin": 300,
                "warm_iter": 700, "warm_burnin": 150, "thin": 10})
    print("Compiling MCMC kernel ...")
    warmup_jit()
    frames = []
    for i, season in enumerate(args.seasons):
        print(f"  Running {season} ...")
        frames.append(run_season(
            df, season,
            carry_weight=args.carry_weight,
            market_kappa=args.market_kappa,
            reset_after_games=args.reset_after_games,
            seed=42 + 1000 * i,
            **budgets,
        ))
    per_match = pd.concat(frames, ignore_index=True)
    summary = summarise(per_match)
    comparisons = paired_comparisons(per_match)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.output_root / f"preseason_backtest_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)
    per_match.to_csv(report_dir / "preseason_backtest_per_match.csv", index=False)
    summary.to_csv(report_dir / "preseason_backtest_summary.csv", index=False)
    comparisons.to_csv(report_dir / "preseason_backtest_comparisons.csv", index=False)
    (report_dir / "config.json").write_text(json.dumps({
        "seasons": args.seasons,
        "carry_weight": args.carry_weight,
        "market_kappa": args.market_kappa,
        "reset_after_games": args.reset_after_games,
        "xg_source": "football-data shot proxy",
        "xg_weights": {"off_target": beta_off, "on_target": beta_on},
        "mcmc_budget": budgets,
        "mode": "full" if args.full else "quick",
    }, indent=2), encoding="utf-8")
    _plot(per_match, summary, report_dir / "preseason_backtest.png")

    pooled = summary[(summary["season"] == "POOLED") &
                     (summary["phase"] == "full_season")]
    print("\nPooled full-season RPS (lower is better):")
    print(pooled[["strategy", "n", "rps"]].to_string(index=False,
                                                       float_format=lambda x: f"{x:.4f}"))
    print("\nPaired RPS advantages (positive = first strategy is better):")
    print(comparisons.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(f"\nReport: {report_dir.resolve()}")


if __name__ == "__main__":
    main()
