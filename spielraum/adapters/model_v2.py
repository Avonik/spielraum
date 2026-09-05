from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spielraum.artifacts import write_json_atomic
from spielraum.config import Settings
from spielraum.providers.openligadb import (
    OpenLigaMatch,
    fetch_season,
    next_unfinished_matchday,
    team_payload,
)
from spielraum.simulation import simulate_placements


ROOT = Path(__file__).resolve().parents[2]
V2_DIR = ROOT / "v2"
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))

from data import load_bundesliga  # noqa: E402
from market_value import fetch_current_season_only, team_market_values  # noqa: E402
from mcmc import run_mcmc  # noqa: E402
from model import (  # noqa: E402
    DEFAULT_EPSILON,
    DEFAULT_GAMMA,
    DEFAULT_PHI,
    DEFAULT_TAU,
    build_league,
    compute_lambdas,
    predict_outcome_probs,
)
from real_xg import _FD_TO_US, add_real_xg_columns, fetch_understat_xg  # noqa: E402
from season_transition_v2 import (  # noqa: E402
    DEFAULT_GOAL_LEVEL_PRIOR_MATCHES,
    EndpointPosterior,
    _flat_init,
    _last_strengths,
    build_fresh_and_carry_priors,
    fit_previous_v2,
    historical_goal_levels,
    recommended_carry_weight,
    shrunk_goal_levels,
)
from xg import add_xg_columns, fit_xg_weights  # noqa: E402


SEASON = "2026/27"


def _naive_date(value: str) -> pd.Timestamp:
    return pd.Timestamp(value).tz_convert("Europe/Berlin").tz_localize(None)


def _schedule_frame(matches: list[OpenLigaMatch]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Date": _naive_date(match.kickoff_utc),
        "HomeTeam": match.home_fd,
        "AwayTeam": match.away_fd,
        "_matchday": match.matchday,
    } for match in matches])


def _current_xg(matches: list[OpenLigaMatch]) -> tuple[pd.DataFrame, list[str]]:
    finished = [match for match in matches if match.finished]
    columns = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "Season", "xG_home", "xG_away", "has_xg", "xg_source"]
    if not finished:
        return pd.DataFrame(columns=columns), []

    understat = fetch_understat_xg([2026], verbose=True)
    lookup = {
        (str(row.home_team), str(row.away_team)): (float(row.home_xg), float(row.away_xg))
        for row in understat.itertuples()
    }
    rows = []
    missing = []
    for match in finished:
        expected = (_FD_TO_US.get(match.home_fd), _FD_TO_US.get(match.away_fd))
        values = lookup.get(expected)
        if values is None:
            missing.append(match.fixture_id)
            continue
        home_goals, away_goals = match.score or (0, 0)
        rows.append({
            "Date": _naive_date(match.kickoff_utc),
            "HomeTeam": match.home_fd,
            "AwayTeam": match.away_fd,
            "FTHG": home_goals,
            "FTAG": away_goals,
            "FTR": "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D",
            "Season": SEASON,
            "xG_home": values[0],
            "xG_away": values[1],
            "has_xg": True,
            "xg_source": "real",
        })
    return pd.DataFrame(rows, columns=columns).sort_values("Date").reset_index(drop=True), missing


def _load_or_fit_endpoint(
    history: pd.DataFrame,
    cache_path: Path,
    *,
    n_iter: int,
    burnin: int,
    thin: int,
) -> EndpointPosterior:
    if cache_path.exists():
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        return EndpointPosterior(
            source_season=raw["source_season"],
            moments={team: tuple(map(float, values)) for team, values in raw["moments"].items()},
            last_match_dates={team: pd.Timestamp(value) for team, value in raw["last_match_dates"].items()},
        )
    endpoint = fit_previous_v2(
        history,
        SEASON,
        n_iter=n_iter,
        burnin=burnin,
        thin=thin,
        seed=42,
    )
    payload = {
        "source_season": endpoint.source_season,
        "moments": {team: list(values) for team, values in endpoint.moments.items()},
        "last_match_dates": {team: value.isoformat() for team, value in endpoint.last_match_dates.items()},
        "config": {"n_iter": n_iter, "burnin": burnin, "thin": thin, "real_xg": True},
    }
    write_json_atomic(cache_path, payload)
    return endpoint


def _load_history(settings: Settings) -> pd.DataFrame:
    cache_path = settings.data_dir / "cache" / "history-real-xg-through-2025-26.csv.gz"
    if cache_path.exists():
        return pd.read_csv(cache_path, parse_dates=["Date"])
    history = load_bundesliga(1993, 2026, with_extras=True)
    xg_train = history[history["Season"] < "2025/26"]
    beta_off, beta_on = fit_xg_weights(xg_train, force=True, cache=False)
    history = add_xg_columns(history, beta_off, beta_on)
    history = add_real_xg_columns(history, verbose=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_name(f".{cache_path.name}.tmp")
    history.to_csv(temporary, index=False, compression="gzip")
    os.replace(temporary, cache_path)
    return history


def _target_market_values(settings: Settings) -> tuple[dict[str, float], str]:
    cache_path = settings.data_dir / "cache" / "market-values.csv"
    if not cache_path.exists():
        source = V2_DIR / "data_cache" / "transfermarkt_squad_values.csv"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, cache_path)
    cached = pd.read_csv(cache_path)
    current = cached[cached["Season"] == SEASON]
    cutoff = pd.Timestamp("2026-08-15")
    as_of_values = current.get("AsOfDate", pd.Series(dtype=str)).dropna()
    as_of = str(as_of_values.max()) if len(as_of_values) else "unknown"
    needs_official_refresh = (
        pd.Timestamp.now().normalize() >= cutoff
        and (as_of == "unknown" or pd.Timestamp(as_of) < cutoff)
    )
    values = team_market_values(SEASON, cache_path)
    if len(values) != 18 or needs_official_refresh:
        allow_early = os.environ.get(
            "SPIELRAUM_ALLOW_EARLY_MARKET_VALUES", "true"
        ).lower() in {"1", "true", "yes"}
        fetch_current_season_only(
            cache_path,
            force=needs_official_refresh,
            allow_before_cutoff=allow_early,
        )
        values = team_market_values(SEASON, cache_path)
        cached = pd.read_csv(cache_path)
        current = cached[cached["Season"] == SEASON]
        as_of_values = current.get("AsOfDate", pd.Series(dtype=str)).dropna()
        as_of = str(as_of_values.max()) if len(as_of_values) else "unknown"
    if len(values) != 18:
        raise ValueError(f"Expected 18 market values for {SEASON}, got {len(values)}")
    return values, as_of


def _fit_streams(
    history: pd.DataFrame,
    prefix: pd.DataFrame,
    schedule: pd.DataFrame,
    endpoint: EndpointPosterior,
    market_values: dict[str, float],
    *,
    n_iter: int,
    burnin: int,
    thin: int,
) -> tuple[dict[str, dict[str, tuple[float, float]]], float, float]:
    teams = sorted(set(schedule["HomeTeam"]) | set(schedule["AwayTeam"]))
    first_dates = {
        team: schedule.loc[(schedule["HomeTeam"] == team) | (schedule["AwayTeam"] == team), "Date"].min()
        for team in teams
    }
    priors = build_fresh_and_carry_priors(teams, first_dates, endpoint, market_values)
    historical_c_x, historical_c_y = historical_goal_levels(history, SEASON, use_xg=True, n_seasons=3)
    if prefix.empty:
        return {name: dict(priors[name]["means"]) for name in ("fresh", "carry")}, historical_c_x, historical_c_y

    combined = pd.concat([history, prefix], ignore_index=True, sort=False)
    level_c_x, level_c_y = shrunk_goal_levels(
        combined,
        SEASON,
        prefix,
        use_xg=True,
        prior_matches=DEFAULT_GOAL_LEVEL_PRIOR_MATCHES,
        n_seasons=3,
    )
    streams: dict[str, dict[str, tuple[float, float]]] = {}
    for offset, name in enumerate(("fresh", "carry")):
        prior = priors[name]
        league = build_league(
            prefix,
            use_xg=True,
            continuous_xg=True,
            phi=DEFAULT_PHI,
            tau=DEFAULT_TAU,
            gamma=DEFAULT_GAMMA,
            epsilon=DEFAULT_EPSILON,
            team_strength_priors=prior["means"],
            carry_weight=1.0,
            initial_attack_prior_var=prior["attack_var"],
            initial_defense_prior_var=prior["defense_var"],
            c_x_override=level_c_x,
            c_y_override=level_c_y,
        )
        init_attack, init_defense = _flat_init(league, prior["means"])
        samples = run_mcmc(
            league,
            n_iter=n_iter,
            burnin=burnin,
            thin=thin,
            proposal_sd=0.06,
            seed=42 + offset,
            verbose=False,
            init_attack=init_attack,
            init_defense=init_defense,
        )
        streams[name] = _last_strengths(samples, league, prior["means"])
    return streams, level_c_x, level_c_y


def _probabilities(
    match: OpenLigaMatch,
    streams: dict[str, dict[str, tuple[float, float]]],
    c_x: float,
    c_y: float,
) -> tuple[float, float, float]:
    values = []
    for name in ("fresh", "carry"):
        home_attack, home_defense = streams[name][match.home_fd]
        away_attack, away_defense = streams[name][match.away_fd]
        values.append(np.asarray(predict_outcome_probs(
            home_attack,
            home_defense,
            away_attack,
            away_defense,
            c_x,
            c_y,
            gamma=DEFAULT_GAMMA,
            eps=DEFAULT_EPSILON,
        )))
    weight = float(recommended_carry_weight(np.asarray([match.matchday]))[0])
    mixed = weight * values[1] + (1.0 - weight) * values[0]
    mixed /= mixed.sum()
    return tuple(float(value) for value in mixed)


def _strength_index(value: float) -> float:
    return float(np.clip(100.0 / (1.0 + np.exp(-3.0 * value)), 1.0, 99.0))


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def build_snapshot(
    matches: list[OpenLigaMatch],
    *,
    settings: Settings,
    simulations: int,
    n_iter: int,
    burnin: int,
    thin: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if len(matches) != 306 or {match.matchday for match in matches} != set(range(1, 35)):
        raise ValueError(f"OpenLigaDB season is incomplete: {len(matches)} matches")
    next_matchday = next_unfinished_matchday(matches)
    if next_matchday is None:
        return None, {
            "matchday_complete": True,
            "xg_complete": True,
            "market_values_complete": True,
            "season_complete": True,
            "reason": "season complete",
        }
    matchday_complete = all(match.finished for match in matches if match.matchday < next_matchday)
    prefix, missing_xg = _current_xg(matches)
    if not matchday_complete or missing_xg:
        return None, {
            "matchday_complete": matchday_complete,
            "xg_complete": not missing_xg,
            "missing_xg_fixture_ids": missing_xg,
        }

    try:
        market_values, market_values_as_of = _target_market_values(settings)
    except RuntimeError as exc:
        return None, {
            "matchday_complete": True,
            "xg_complete": True,
            "market_values_complete": False,
            "reason": str(exc),
        }
    history = _load_history(settings)

    cache_path = settings.data_dir / "cache" / f"endpoint-2025-26-n{n_iter}-b{burnin}-t{thin}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    endpoint = _load_or_fit_endpoint(history, cache_path, n_iter=n_iter, burnin=burnin, thin=thin)
    schedule = _schedule_frame(matches)
    streams, c_x, c_y = _fit_streams(
        history,
        prefix,
        schedule,
        endpoint,
        market_values,
        n_iter=n_iter,
        burnin=burnin,
        thin=thin,
    )
    upcoming = [match for match in matches if match.matchday == next_matchday and not match.finished]
    probabilities = {match.fixture_id: _probabilities(match, streams, c_x, c_y) for match in upcoming}

    def lambdas(match: OpenLigaMatch) -> tuple[float, float, float, float, float]:
        values = []
        for name in ("fresh", "carry"):
            ah, dh = streams[name][match.home_fd]
            aa, da = streams[name][match.away_fd]
            values.extend(compute_lambdas(ah, dh, aa, da, c_x, c_y, gamma=DEFAULT_GAMMA))
        weight = float(recommended_carry_weight(np.asarray([match.matchday]))[0])
        return float(values[0]), float(values[1]), float(values[2]), float(values[3]), weight

    teams_fd = sorted({match.home_fd for match in matches} | {match.away_fd for match in matches})
    placements_fd = simulate_placements(
        matches,
        teams=teams_fd,
        lambdas_for_match=lambdas,
        simulations=simulations,
    )
    fd_to_slug = {match.home_fd: match.home_slug for match in matches}
    fd_to_slug.update({match.away_fd: match.away_slug for match in matches})
    current_weight = float(recommended_carry_weight(np.asarray([next_matchday]))[0])
    strengths = []
    for fd_name in teams_fd:
        attack = current_weight * streams["carry"][fd_name][0] + (1.0 - current_weight) * streams["fresh"][fd_name][0]
        defense = current_weight * streams["carry"][fd_name][1] + (1.0 - current_weight) * streams["fresh"][fd_name][1]
        strengths.append({
            "team": fd_to_slug[fd_name],
            "matchday": next_matchday,
            "attack": _strength_index(attack),
            "defense": _strength_index(defense),
        })

    created = datetime.now(UTC)
    stamp = created.strftime("%Y%m%dT%H%M%SZ")
    model_id = f"v2.1-live-{stamp}"
    snapshot = {
        "snapshot_id": f"2627-md{next_matchday:02d}-{stamp}",
        "season": SEASON,
        "matchday": next_matchday,
        "published_at": created.isoformat(),
        "mode": "live",
        "model": {
            "id": model_id,
            "created_at": created.isoformat(),
            "git_sha": _git_sha(),
            "config": {
                "model": "dual V2",
                "tau": DEFAULT_TAU,
                "gamma": DEFAULT_GAMMA,
                "epsilon": DEFAULT_EPSILON,
                "phi": DEFAULT_PHI,
                "continuous_xg": True,
                "xg_source": "Understat via soccerdata",
                "fixtures_results_source": "OpenLigaDB ODbL",
                "market_values": {
                    "season": SEASON,
                    "as_of": market_values_as_of,
                    "provisional": market_values_as_of < "2026-08-15",
                },
                "goal_level_prior_matches": DEFAULT_GOAL_LEVEL_PRIOR_MATCHES,
                "carry_fade": {"full_through_matchday": 12, "zero_from_matchday": 18},
                "mcmc": {"iterations": n_iter, "burnin": burnin, "thin": thin},
            },
        },
        "teams": [team_payload(slug) for slug in sorted(set(fd_to_slug.values()))],
        "fixtures": [{
            "id": match.fixture_id,
            "kickoff_utc": match.kickoff_utc,
            "home": match.home_slug,
            "away": match.away_slug,
            "probabilities": list(probabilities[match.fixture_id]),
            "status": "scheduled",
        } for match in upcoming],
        "strengths": strengths,
        "placements": [{**item, "team": fd_to_slug[str(item["team"])]} for item in placements_fd],
    }
    return snapshot, {"matchday_complete": True, "xg_complete": True, "market_values_complete": True}


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description="Create a production Spielraum V2 snapshot")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--simulations", type=int, default=int(os.environ.get("SPIELRAUM_SIMULATIONS", "50000")))
    parser.add_argument("--n-iter", type=int, default=int(os.environ.get("SPIELRAUM_MCMC_ITER", "5000")))
    parser.add_argument("--burnin", type=int, default=int(os.environ.get("SPIELRAUM_MCMC_BURNIN", "1000")))
    parser.add_argument("--thin", type=int, default=int(os.environ.get("SPIELRAUM_MCMC_THIN", "10")))
    args = parser.parse_args()
    if args.season != 2026:
        raise ValueError("This production adapter is intentionally pinned to season start 2026")
    settings = Settings.from_env()
    settings.ensure_directories()
    matches = fetch_season(args.season)
    snapshot, status = build_snapshot(
        matches,
        settings=settings,
        simulations=args.simulations,
        n_iter=args.n_iter,
        burnin=args.burnin,
        thin=args.thin,
    )
    if snapshot is not None:
        snapshot_path = settings.data_dir / "inbox" / f"{snapshot['snapshot_id']}.json"
        write_json_atomic(snapshot_path, snapshot)
        status["snapshot_path"] = str(snapshot_path.resolve())
        status["snapshot_id"] = snapshot["snapshot_id"]
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
