"""Two-stream V2 walk-forward: fresh current season vs carried prior season."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from evaluation import outcome_index, rps_one
from market_value import team_market_values
from mcmc import run_mcmc
from model import (
    DEFAULT_EPSILON,
    DEFAULT_GAMMA,
    DEFAULT_PHI,
    DEFAULT_TAU,
    MAX_GOALS,
    PRIOR_VAR,
    build_league,
    compose_initial_prior_means,
    predict_outcome_probs,
)
from preseason import (
    historical_goal_levels,
    previous_season_label,
    shrunk_goal_levels,
)


DEFAULT_GOAL_LEVEL_PRIOR_MATCHES = 144.0
DEFAULT_CARRY_FADE_START_MATCHDAY = 12
DEFAULT_CARRY_FADE_END_MATCHDAY = 18


@dataclass
class EndpointPosterior:
    source_season: str
    moments: dict[str, tuple[float, float, float, float]]
    last_match_dates: dict[str, pd.Timestamp]


def endpoint_posterior(samples: dict, league, source_season: str,
                       source: pd.DataFrame) -> EndpointPosterior:
    """Posterior mean/variance of each team's final attack and defence node."""
    moments = {}
    last_dates = {}
    for team_i, team in enumerate(league.teams):
        attack = np.array([sample[team_i][-1] for sample in samples["attack"]],
                          dtype=float)
        defense = np.array([sample[team_i][-1] for sample in samples["defense"]],
                           dtype=float)
        moments[team] = (
            float(attack.mean()),
            float(max(1e-6, attack.var(ddof=1))),
            float(defense.mean()),
            float(max(1e-6, defense.var(ddof=1))),
        )
        games = source[(source["HomeTeam"] == team) |
                       (source["AwayTeam"] == team)]
        last_dates[team] = pd.Timestamp(games["Date"].max())
    return EndpointPosterior(source_season, moments, last_dates)


def fit_previous_v2(
    df: pd.DataFrame,
    target_season: str,
    *,
    n_iter: int,
    burnin: int,
    thin: int,
    seed: int,
    tau: float = DEFAULT_TAU,
    gamma: float = DEFAULT_GAMMA,
    epsilon: float = DEFAULT_EPSILON,
    phi: float = DEFAULT_PHI,
    market_kappa: float = 0.10,
) -> EndpointPosterior:
    """Fit the preceding season with the same structural V2 configuration."""
    source_season = previous_season_label(target_season)
    source = (df[df["Season"] == source_season]
              .sort_values("Date").reset_index(drop=True))
    if source.empty:
        raise ValueError(f"Missing source season {source_season}.")
    source_market = team_market_values(source_season)
    league = build_league(
        source,
        use_xg=True,
        continuous_xg=True,
        phi=phi,
        tau=tau,
        gamma=gamma,
        epsilon=epsilon,
        team_values=source_market,
        market_kappa=market_kappa,
    )
    samples = run_mcmc(
        league,
        n_iter=n_iter,
        burnin=burnin,
        thin=thin,
        proposal_sd=0.06,
        seed=seed,
        verbose=False,
    )
    return endpoint_posterior(samples, league, source_season, source)


def _teams_and_first_dates(season_df: pd.DataFrame) -> tuple[list[str], dict]:
    teams = sorted(set(season_df["HomeTeam"]) | set(season_df["AwayTeam"]))
    first_dates = {}
    for team in teams:
        games = season_df[(season_df["HomeTeam"] == team) |
                          (season_df["AwayTeam"] == team)]
        first_dates[team] = pd.Timestamp(games["Date"].min())
    return teams, first_dates


def build_fresh_and_carry_priors(
    teams: list[str],
    first_dates: dict[str, pd.Timestamp],
    endpoint: EndpointPosterior,
    target_market: dict[str, float],
    *,
    tau: float = DEFAULT_TAU,
    market_kappa: float = 0.10,
    summer_variance_scale: float = 1.0,
    market_prior_var: float = PRIOR_VAR,
) -> dict[str, dict]:
    """Build priors whose sole distinction is the preceding V2 posterior.

    The carried signal follows the model's Brownian variance over the actual
    summer gap and is precision-combined with the same market prior used by
    fresh V2. Promoted teams therefore have identical priors in both streams.
    """
    market_a, market_d, _ = compose_initial_prior_means(
        teams, team_values=target_market, market_kappa=market_kappa)
    fresh_means = {
        team: (float(market_a[i]), float(market_d[i]))
        for i, team in enumerate(teams)
    }
    fresh_a_var = {team: float(market_prior_var) for team in teams}
    fresh_d_var = dict(fresh_a_var)
    carry_means = dict(fresh_means)
    carry_a_var = dict(fresh_a_var)
    carry_d_var = dict(fresh_d_var)

    for i, team in enumerate(teams):
        moment = endpoint.moments.get(team)
        last_date = endpoint.last_match_dates.get(team)
        if moment is None or last_date is None:
            continue
        gap_days = max(1, int((first_dates[team] - last_date).days))
        process_var = (gap_days / float(tau)) * PRIOR_VAR * summer_variance_scale
        prev_a_mean, prev_a_var, prev_d_mean, prev_d_var = moment
        carried_a_var = prev_a_var + process_var
        carried_d_var = prev_d_var + process_var

        combined_a_var = 1.0 / (1.0 / carried_a_var + 1.0 / market_prior_var)
        combined_d_var = 1.0 / (1.0 / carried_d_var + 1.0 / market_prior_var)
        combined_a_mean = combined_a_var * (
            prev_a_mean / carried_a_var + market_a[i] / market_prior_var)
        combined_d_mean = combined_d_var * (
            prev_d_mean / carried_d_var + market_d[i] / market_prior_var)
        carry_means[team] = (float(combined_a_mean), float(combined_d_mean))
        carry_a_var[team] = float(combined_a_var)
        carry_d_var[team] = float(combined_d_var)

    # Match the MCMC's shared attack/defence sum-to-zero projection without
    # changing promoted teams, whose fresh/carry priors must be identical.
    retained = [team for team in teams if team in endpoint.moments]
    if retained:
        total = float(sum(value for pair in carry_means.values() for value in pair))
        level = total / (2.0 * len(retained))
        for team in retained:
            attack, defense = carry_means[team]
            carry_means[team] = (attack - level, defense - level)
    return {
        "fresh": {"means": fresh_means,
                  "attack_var": fresh_a_var, "defense_var": fresh_d_var},
        "carry": {"means": carry_means,
                  "attack_var": carry_a_var, "defense_var": carry_d_var},
    }


def _flat_init(league, strengths: dict[str, tuple[float, float]]) -> tuple:
    attack = np.zeros(int(league.team_start[-1]), dtype=float)
    defense = np.zeros_like(attack)
    for team_i, team in enumerate(league.teams):
        a, d = strengths.get(team, (0.0, 0.0))
        attack[league.team_start[team_i]:league.team_start[team_i + 1]] = a
        defense[league.team_start[team_i]:league.team_start[team_i + 1]] = d
    return attack, defense


def _last_strengths(samples: dict, league, fallback: dict) -> dict:
    out = dict(fallback)
    for team_i, team in enumerate(league.teams):
        out[team] = (
            float(np.mean([sample[team_i][-1] for sample in samples["attack"]])),
            float(np.mean([sample[team_i][-1] for sample in samples["defense"]])),
        )
    return out


def _predict(games: pd.DataFrame, strengths: dict, c_x: float, c_y: float,
             gamma: float, epsilon: float, target: np.ndarray) -> None:
    for idx, row in games.iterrows():
        ah, dh = strengths[row["HomeTeam"]]
        aa, da = strengths[row["AwayTeam"]]
        target[idx] = predict_outcome_probs(
            ah, dh, aa, da, c_x, c_y,
            gamma=gamma, eps=epsilon, max_k=MAX_GOALS)


def _matchdays(season_df: pd.DataFrame) -> np.ndarray:
    teams = sorted(set(season_df["HomeTeam"]) | set(season_df["AwayTeam"]))
    played = {team: 0 for team in teams}
    matchdays = []
    for row in season_df.itertuples():
        matchdays.append(max(played[row.HomeTeam], played[row.AwayTeam]) + 1)
        played[row.HomeTeam] += 1
        played[row.AwayTeam] += 1
    return np.asarray(matchdays, dtype=int)


def cosine_goal_level_prior(
    prior_matches: float,
    observed_matches: int,
    fade_matches: float | None,
) -> float:
    """Effective historical pseudo-count after an optional cosine fade."""
    if fade_matches is None or np.isinf(prior_matches):
        return float(prior_matches)
    if fade_matches <= 0.0:
        raise ValueError("goal-level fade must be positive.")
    progress = min(1.0, max(0.0, observed_matches / float(fade_matches)))
    return float(prior_matches * 0.5 * (1.0 + np.cos(np.pi * progress)))


def recommended_carry_weight(matchdays: np.ndarray) -> np.ndarray:
    """Production carry weight: full through MD12, zero from MD18."""
    values = np.asarray(matchdays, dtype=float)
    start = float(DEFAULT_CARRY_FADE_START_MATCHDAY)
    end = float(DEFAULT_CARRY_FADE_END_MATCHDAY)
    progress = np.clip((values - start) / (end - start), 0.0, 1.0)
    return 0.5 * (1.0 + np.cos(np.pi * progress))


def recommended_transition_probabilities(frame: pd.DataFrame) -> np.ndarray:
    """Blend dual-stream probabilities using the production transition."""
    required = {"matchday"}
    for stream in ("fresh_v2", "carry_v2"):
        required.update({f"p_home_{stream}", f"p_draw_{stream}",
                         f"p_away_{stream}"})
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing transition columns: {sorted(missing)}")
    fresh = frame[["p_home_fresh_v2", "p_draw_fresh_v2",
                   "p_away_fresh_v2"]].to_numpy(float)
    carry = frame[["p_home_carry_v2", "p_draw_carry_v2",
                   "p_away_carry_v2"]].to_numpy(float)
    weight = recommended_carry_weight(frame["matchday"].to_numpy())
    return weight[:, None] * carry + (1.0 - weight[:, None]) * fresh


def run_dual_v2_season(
    df: pd.DataFrame,
    season: str,
    endpoint: EndpointPosterior,
    *,
    prior_iter: int = 5_000,
    base_iter: int = 3_000,
    base_burnin: int = 600,
    warm_iter: int = 1_500,
    warm_burnin: int = 250,
    thin: int = 10,
    seed: int = 42,
    tau: float = DEFAULT_TAU,
    gamma: float = DEFAULT_GAMMA,
    epsilon: float = DEFAULT_EPSILON,
    phi: float = DEFAULT_PHI,
    market_kappa: float = 0.10,
    summer_variance_scale: float = 1.0,
    goal_level_prior_matches: float = DEFAULT_GOAL_LEVEL_PRIOR_MATCHES,
    goal_level_prior_fade_matches: float | None = None,
    max_matchday: int | None = None,
) -> pd.DataFrame:
    """Forecast every target-season date with fresh and carried V2 priors."""
    del prior_iter  # endpoint is already fitted; kept out of the public driver.
    season_df = (df[df["Season"] == season]
                 .sort_values("Date").reset_index(drop=True))
    if season_df.empty:
        raise ValueError(f"Missing target season {season}.")
    season_df["_matchday"] = _matchdays(season_df)
    if max_matchday is not None:
        if max_matchday < 1:
            raise ValueError("max_matchday must be at least 1.")
        season_df = (season_df[season_df["_matchday"] <= max_matchday]
                     .reset_index(drop=True))
    teams, first_dates = _teams_and_first_dates(season_df)
    target_market = team_market_values(season)
    priors = build_fresh_and_carry_priors(
        teams, first_dates, endpoint, target_market,
        tau=tau, market_kappa=market_kappa,
        summer_variance_scale=summer_variance_scale)
    historical_c_x, historical_c_y = historical_goal_levels(
        df, season, use_xg=True, n_seasons=3)

    predictions = {
        name: np.full((len(season_df), 3), np.nan)
        for name in ("fresh_v2", "carry_v2")
    }
    warm = {"fresh": None, "carry": None}
    for date_i, date in enumerate(sorted(season_df["Date"].unique())):
        prefix = season_df[season_df["Date"] < date]
        games = season_df[season_df["Date"] == date]
        if prefix.empty:
            for name in ("fresh", "carry"):
                _predict(games, priors[name]["means"],
                         historical_c_x, historical_c_y, gamma, epsilon,
                         predictions[f"{name}_v2"])
            continue

        effective_level_prior = cosine_goal_level_prior(
            goal_level_prior_matches, len(prefix),
            goal_level_prior_fade_matches)
        level_c_x, level_c_y = shrunk_goal_levels(
            df, season, prefix, use_xg=True,
            prior_matches=effective_level_prior, n_seasons=3)
        levels = None
        for name in ("fresh", "carry"):
            prior = priors[name]
            league = build_league(
                prefix,
                use_xg=True,
                continuous_xg=True,
                phi=phi,
                tau=tau,
                gamma=gamma,
                epsilon=epsilon,
                team_strength_priors=prior["means"],
                carry_weight=1.0,
                initial_attack_prior_var=prior["attack_var"],
                initial_defense_prior_var=prior["defense_var"],
                c_x_override=level_c_x,
                c_y_override=level_c_y,
            )
            if levels is None:
                levels = (league.c_x, league.c_y)
            elif not np.allclose(levels, (league.c_x, league.c_y), atol=0.0):
                raise RuntimeError("Fresh and carry global levels diverged.")
            initial = prior["means"] if warm[name] is None else warm[name]
            init_attack, init_defense = _flat_init(league, initial)
            samples = run_mcmc(
                league,
                n_iter=base_iter if warm[name] is None else warm_iter,
                burnin=base_burnin if warm[name] is None else warm_burnin,
                thin=thin,
                proposal_sd=0.06,
                seed=seed + date_i,  # common random numbers for both streams
                verbose=False,
                init_attack=init_attack,
                init_defense=init_defense,
            )
            strengths = _last_strengths(samples, league, prior["means"])
            warm[name] = strengths
            _predict(games, strengths, league.c_x, league.c_y, gamma, epsilon,
                     predictions[f"{name}_v2"])

    outcomes = np.array([
        outcome_index(int(row.FTHG), int(row.FTAG))
        for row in season_df.itertuples()
    ])
    result = season_df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].copy()
    result.insert(0, "season", season)
    result["season_game"] = np.arange(1, len(result) + 1)
    result["matchday"] = season_df["_matchday"].to_numpy(int)
    result["outcome"] = outcomes
    for name, probabilities in predictions.items():
        result[f"p_home_{name}"] = probabilities[:, 0]
        result[f"p_draw_{name}"] = probabilities[:, 1]
        result[f"p_away_{name}"] = probabilities[:, 2]
        result[f"rps_{name}"] = [
            rps_one(probability, outcome)
            for probability, outcome in zip(probabilities, outcomes)
        ]
    recommended = recommended_transition_probabilities(result)
    result["carry_weight_recommended"] = recommended_carry_weight(
        result["matchday"].to_numpy())
    result["p_home_recommended_v2"] = recommended[:, 0]
    result["p_draw_recommended_v2"] = recommended[:, 1]
    result["p_away_recommended_v2"] = recommended[:, 2]
    result["rps_recommended_v2"] = [
        rps_one(probability, outcome)
        for probability, outcome in zip(recommended, outcomes)
    ]
    return result
