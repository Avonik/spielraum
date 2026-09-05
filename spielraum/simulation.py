from __future__ import annotations

from typing import Any, Callable, Iterable

import numpy as np


def simulate_placements(
    matches: Iterable[Any],
    *,
    teams: list[str],
    lambdas_for_match: Callable[[Any], tuple[float, float, float, float, float]],
    simulations: int = 50_000,
    seed: int = 202627,
) -> list[dict[str, float | int | str]]:
    """Simulate the remaining season from dual-stream Poisson intensities.

    ``lambdas_for_match`` returns fresh home/away lambdas, carry home/away
    lambdas and the carry mixture weight for one scheduled match.
    """
    if simulations < 100:
        raise ValueError("simulations must be at least 100")
    team_index = {team: index for index, team in enumerate(teams)}
    if len(team_index) != len(teams):
        raise ValueError("teams must be unique")
    points = np.zeros((simulations, len(teams)), dtype=np.int16)
    goals_for = np.zeros_like(points)
    goals_against = np.zeros_like(points)
    rng = np.random.default_rng(seed)

    pending = []
    for match in matches:
        home = team_index[match.home_fd]
        away = team_index[match.away_fd]
        if match.finished:
            if match.score is None:
                raise ValueError(f"finished match {match.fixture_id} has no score")
            home_goals, away_goals = match.score
            goals_for[:, home] += home_goals
            goals_against[:, home] += away_goals
            goals_for[:, away] += away_goals
            goals_against[:, away] += home_goals
            if home_goals > away_goals:
                points[:, home] += 3
            elif away_goals > home_goals:
                points[:, away] += 3
            else:
                points[:, home] += 1
                points[:, away] += 1
        else:
            pending.append((match, home, away))

    for match, home, away in pending:
        fresh_h, fresh_a, carry_h, carry_a, carry_weight = lambdas_for_match(match)
        choose_carry = rng.random(simulations) < carry_weight
        lambda_home = np.where(choose_carry, carry_h, fresh_h)
        lambda_away = np.where(choose_carry, carry_a, fresh_a)
        home_goals = rng.poisson(lambda_home).astype(np.int16)
        away_goals = rng.poisson(lambda_away).astype(np.int16)
        goals_for[:, home] += home_goals
        goals_against[:, home] += away_goals
        goals_for[:, away] += away_goals
        goals_against[:, away] += home_goals
        home_win = home_goals > away_goals
        away_win = away_goals > home_goals
        draw = ~(home_win | away_win)
        points[:, home] += 3 * home_win + draw
        points[:, away] += 3 * away_win + draw

    goal_difference = goals_for - goals_against
    jitter = rng.random(points.shape) * 0.001
    ranking_key = points.astype(float) * 1_000_000 + goal_difference * 1_000 + goals_for + jitter
    order = np.argsort(-ranking_key, axis=1)
    ranks = np.empty_like(order, dtype=np.int16)
    rows = np.arange(simulations)[:, None]
    ranks[rows, order] = np.arange(1, len(teams) + 1, dtype=np.int16)

    output: list[dict[str, float | int | str]] = []
    for team, index in team_index.items():
        team_ranks = ranks[:, index]
        output.append({
            "team": team,
            "median": float(np.median(team_ranks)),
            "low": int(np.quantile(team_ranks, 0.10, method="nearest")),
            "high": int(np.quantile(team_ranks, 0.90, method="nearest")),
            "title": float(np.mean(team_ranks == 1)),
            "top4": float(np.mean(team_ranks <= 4)),
            "relegation": float(np.mean(team_ranks >= 16)),
            "simulations": simulations,
        })
    output.sort(key=lambda item: (float(item["median"]), -float(item["title"])))
    return output

