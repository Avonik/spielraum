"""Leak-free season-transition priors and preseason predictions.

The previous season is used only to initialise the next one. Once matches in
the target season exist, the normal Rue-Salvesen likelihood updates those
strengths; the old values are not frozen or repeatedly copied forward.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

import numpy as np
import pandas as pd

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
from mcmc import posterior_means, run_mcmc


def previous_season_label(season: str) -> str:
    start = int(season.split("/")[0]) - 1
    return f"{start}/{(start + 1) % 100:02d}"


def season_teams(df: pd.DataFrame, season: str) -> list[str]:
    sub = df[df["Season"] == season]
    return sorted(set(sub["HomeTeam"]) | set(sub["AwayTeam"]))


def historical_goal_levels(
    df: pd.DataFrame,
    target_season: str,
    *,
    use_xg: bool,
    n_seasons: int = 3,
) -> tuple[float, float]:
    """Log home/away scoring levels from seasons before ``target_season``."""
    history_seasons = sorted(s for s in df["Season"].unique()
                             if s < target_season)[-n_seasons:]
    history = df[df["Season"].isin(history_seasons)]
    if history.empty:
        raise ValueError(f"No history available before {target_season}.")
    if use_xg and {"xG_home", "xG_away"}.issubset(history.columns):
        home = pd.to_numeric(history["xG_home"], errors="coerce").mean()
        away = pd.to_numeric(history["xG_away"], errors="coerce").mean()
    else:
        home = pd.to_numeric(history["FTHG"], errors="coerce").mean()
        away = pd.to_numeric(history["FTAG"], errors="coerce").mean()
    return float(np.log(max(0.05, home))), float(np.log(max(0.05, away)))


def shrunk_goal_levels(
    df: pd.DataFrame,
    target_season: str,
    prefix: pd.DataFrame,
    *,
    use_xg: bool,
    prior_matches: float,
    n_seasons: int = 3,
) -> tuple[float, float]:
    """Leak-free current-season goal levels shrunk to historical levels.

    ``prior_matches`` is the effective number of historical pseudo-matches.
    Zero reproduces the old current-prefix estimate, while ``np.inf`` keeps
    the historical level fixed. An empty prefix always uses history.
    """
    if prior_matches < 0.0 or np.isnan(prior_matches):
        raise ValueError("prior_matches must be non-negative or infinity.")
    hist_c_x, hist_c_y = historical_goal_levels(
        df, target_season, use_xg=use_xg, n_seasons=n_seasons)
    if prefix.empty or np.isinf(prior_matches):
        return hist_c_x, hist_c_y

    if use_xg and {"xG_home", "xG_away"}.issubset(prefix.columns):
        current_home = pd.to_numeric(prefix["xG_home"], errors="coerce").mean()
        current_away = pd.to_numeric(prefix["xG_away"], errors="coerce").mean()
    else:
        current_home = pd.to_numeric(prefix["FTHG"], errors="coerce").mean()
        current_away = pd.to_numeric(prefix["FTAG"], errors="coerce").mean()
    if not np.isfinite(current_home) or not np.isfinite(current_away):
        return hist_c_x, hist_c_y
    if prior_matches == 0.0:
        return (float(np.log(max(0.05, current_home))),
                float(np.log(max(0.05, current_away))))

    n_current = float(len(prefix))
    home = ((prior_matches * np.exp(hist_c_x) + n_current * current_home)
            / (prior_matches + n_current))
    away = ((prior_matches * np.exp(hist_c_y) + n_current * current_away)
            / (prior_matches + n_current))
    return float(np.log(max(0.05, home))), float(np.log(max(0.05, away)))


def standardized_market_value_signal(
    current_values: dict[str, float],
    teams: list[str],
    *,
    previous_values: dict[str, float] | None = None,
) -> dict[str, float]:
    """z-scored log market-value level or year-over-year log change."""
    raw = []
    valid_teams = []
    for team in teams:
        current = current_values.get(team)
        previous = None if previous_values is None else previous_values.get(team)
        if current is None or current <= 0.0:
            continue
        if previous_values is None:
            value = np.log(current)
        else:
            if previous is None or previous <= 0.0:
                continue
            value = np.log(current) - np.log(previous)
        raw.append(float(value))
        valid_teams.append(team)
    if len(raw) < 2 or float(np.std(raw)) <= 0.0:
        return {}
    values = (np.asarray(raw) - np.mean(raw)) / np.std(raw)
    return {team: float(value) for team, value in zip(valid_teams, values)}


def _last_strengths(samples: dict, league) -> dict[str, tuple[float, float]]:
    mean_attack, mean_defense, _ = posterior_means(samples)
    return {
        team: (float(mean_attack[i][-1]), float(mean_defense[i][-1]))
        for i, team in enumerate(league.teams)
    }


@dataclass
class PreseasonState:
    target_season: str
    source_season: str
    teams: list[str]
    source_strengths: dict[str, tuple[float, float]]
    carried_teams: list[str]
    new_teams: list[str]
    c_x: float
    c_y: float
    carry_weight: float = 0.75
    market_kappa: float = 0.10
    market_delta_kappa: float = 0.0
    market_delta_signal: dict[str, float] = field(default_factory=dict)
    market_level_new_only: bool = False
    summer_prior_var: float = 4.0 * PRIOR_VAR
    new_team_prior_var: float = 9.0 * PRIOR_VAR
    use_xg: bool = True
    continuous_xg: bool = True
    phi: float = DEFAULT_PHI
    tau: float = DEFAULT_TAU
    gamma: float = DEFAULT_GAMMA
    epsilon: float = DEFAULT_EPSILON
    early_process_multiplier: float = 1.0
    early_process_half_life: float = 6.0

    def strength_adjustments(
        self, market_values: dict[str, float] | None = None,
    ) -> dict[str, tuple[float, float]]:
        adjustments: dict[str, tuple[float, float]] = {}
        for team, signal in self.market_delta_signal.items():
            value = self.market_delta_kappa * float(signal)
            adjustments[team] = (value, value)
        if self.market_level_new_only and market_values:
            level = standardized_market_value_signal(market_values, self.teams)
            for team in self.new_teams:
                value = self.market_kappa * level.get(team, 0.0)
                old = adjustments.get(team, (0.0, 0.0))
                adjustments[team] = (old[0] + value, old[1] + value)
        return adjustments

    def prior_variances(self) -> dict[str, float]:
        new = set(self.new_teams)
        return {
            team: self.new_team_prior_var if team in new else self.summer_prior_var
            for team in self.teams
        }

    def effective_strengths(
        self, market_values: dict[str, float] | None = None,
    ) -> dict[str, tuple[float, float]]:
        attack, defense, _ = compose_initial_prior_means(
            self.teams,
            team_values=None if self.market_level_new_only else market_values,
            market_kappa=0.0 if self.market_level_new_only else self.market_kappa,
            team_strength_priors=self.source_strengths,
            carry_weight=self.carry_weight,
            team_strength_adjustments=self.strength_adjustments(market_values),
        )
        return {team: (float(attack[i]), float(defense[i]))
                for i, team in enumerate(self.teams)}

    def league_kwargs(
        self, market_values: dict[str, float] | None = None,
    ) -> dict:
        return {
            "use_xg": self.use_xg,
            "tau": self.tau,
            "gamma": self.gamma,
            "epsilon": self.epsilon,
            "continuous_xg": self.continuous_xg,
            "phi": self.phi,
            "team_values": None if self.market_level_new_only else market_values,
            "market_kappa": 0.0 if self.market_level_new_only else self.market_kappa,
            "team_strength_priors": self.source_strengths,
            "carry_weight": self.carry_weight,
            "team_strength_adjustments": self.strength_adjustments(market_values),
            "initial_prior_var": self.prior_variances(),
            "c_x_override": self.c_x,
            "c_y_override": self.c_y,
            "early_process_multiplier": self.early_process_multiplier,
            "early_process_half_life": self.early_process_half_life,
        }

    def to_dict(self) -> dict:
        out = asdict(self)
        out["source_strengths"] = {
            k: [float(v[0]), float(v[1])]
            for k, v in self.source_strengths.items()
        }
        return out

    def save_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path

    @classmethod
    def load_json(cls, path: str | Path) -> "PreseasonState":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        raw["source_strengths"] = {
            k: (float(v[0]), float(v[1]))
            for k, v in raw["source_strengths"].items()
        }
        return cls(**raw)


def fit_preseason_state(
    df: pd.DataFrame,
    target_season: str,
    *,
    target_teams: list[str] | None = None,
    carry_weight: float = 0.75,
    market_kappa: float = 0.10,
    market_delta_kappa: float = 0.0,
    market_delta_signal: dict[str, float] | None = None,
    market_level_new_only: bool = False,
    summer_prior_var: float = 4.0 * PRIOR_VAR,
    new_team_prior_var: float = 9.0 * PRIOR_VAR,
    use_xg: bool = True,
    continuous_xg: bool = True,
    phi: float = DEFAULT_PHI,
    tau: float = DEFAULT_TAU,
    gamma: float = DEFAULT_GAMMA,
    epsilon: float = DEFAULT_EPSILON,
    early_process_multiplier: float = 1.0,
    early_process_half_life: float = 6.0,
    history_seasons: int = 3,
    n_iter: int = 3000,
    burnin: int = 600,
    thin: int = 10,
    proposal_sd: float = 0.06,
    seed: int = 42,
    verbose: bool = False,
) -> PreseasonState:
    """Fit the previous complete season and create the next season's prior."""
    source_season = previous_season_label(target_season)
    source = (df[df["Season"] == source_season]
              .sort_values("Date").reset_index(drop=True))
    if source.empty:
        raise ValueError(f"Source season {source_season} is missing.")

    source_c_x, source_c_y = historical_goal_levels(
        df, source_season, use_xg=use_xg, n_seasons=history_seasons)
    league = build_league(
        source,
        use_xg=use_xg,
        tau=tau,
        gamma=gamma,
        epsilon=epsilon,
        continuous_xg=continuous_xg,
        phi=phi,
        c_x_override=source_c_x,
        c_y_override=source_c_y,
    )
    samples = run_mcmc(
        league,
        n_iter=n_iter,
        burnin=burnin,
        thin=thin,
        proposal_sd=proposal_sd,
        seed=seed,
        verbose=verbose,
    )
    strengths = _last_strengths(samples, league)

    if target_teams is None:
        target_teams = season_teams(df, target_season) or list(league.teams)
    target_teams = sorted(set(target_teams))
    source_team_set = set(league.teams)
    carried = sorted(source_team_set.intersection(target_teams))
    new = sorted(set(target_teams) - source_team_set)
    c_x, c_y = historical_goal_levels(
        df, target_season, use_xg=use_xg, n_seasons=history_seasons)

    return PreseasonState(
        target_season=target_season,
        source_season=source_season,
        teams=target_teams,
        source_strengths=strengths,
        carried_teams=carried,
        new_teams=new,
        c_x=c_x,
        c_y=c_y,
        carry_weight=carry_weight,
        market_kappa=market_kappa,
        market_delta_kappa=market_delta_kappa,
        market_delta_signal=dict(market_delta_signal or {}),
        market_level_new_only=market_level_new_only,
        summer_prior_var=summer_prior_var,
        new_team_prior_var=new_team_prior_var,
        use_xg=use_xg,
        continuous_xg=continuous_xg,
        phi=phi,
        tau=tau,
        gamma=gamma,
        epsilon=epsilon,
        early_process_multiplier=early_process_multiplier,
        early_process_half_life=early_process_half_life,
    )


def predict_preseason_fixtures(
    fixtures: pd.DataFrame,
    state: PreseasonState,
    *,
    market_values: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Predict fixtures from preseason priors without target-season results."""
    needed = {"HomeTeam", "AwayTeam"}
    if not needed.issubset(fixtures.columns):
        raise ValueError("Fixtures need HomeTeam and AwayTeam columns.")
    strengths = state.effective_strengths(market_values)
    rows = []
    for _, row in fixtures.iterrows():
        home, away = str(row["HomeTeam"]), str(row["AwayTeam"])
        if home not in strengths or away not in strengths:
            missing = home if home not in strengths else away
            raise ValueError(f"Team {missing!r} is missing from the preseason state.")
        ah, dh = strengths[home]
        aa, da = strengths[away]
        probs = predict_outcome_probs(
            ah, dh, aa, da, state.c_x, state.c_y,
            gamma=state.gamma, eps=state.epsilon, max_k=MAX_GOALS,
        )
        out = row.to_dict()
        out.update({"p_home": probs[0], "p_draw": probs[1], "p_away": probs[2]})
        rows.append(out)
    return pd.DataFrame(rows)
