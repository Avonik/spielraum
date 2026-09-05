from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .publish import publish_file, record_results, sync_schedule
from .storage import finish_run, initialize, start_run, transaction


def _now() -> datetime:
    return datetime.now(UTC)


def _command_for(job: str) -> list[str] | None:
    raw = os.environ.get(f"SPIELRAUM_{job.upper()}_COMMAND")
    if not raw:
        return None
    parts = shlex.split(raw, posix=os.name != "nt")
    if os.name == "nt":
        parts = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"} else part
            for part in parts
        ]
    return parts


def run_job(settings: Settings, job: str) -> str:
    started = _now()
    run_id = start_run(settings.database_path, job, started.isoformat())
    command = _command_for(job)
    if not command:
        finish_run(settings.database_path, run_id, _now().isoformat(), "skipped", {"reason": "command not configured"})
        return "skipped"
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
            timeout=60 * 90,
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        payload = json.loads(lines[-1]) if lines else {}
        if job == "model" and not (
            payload.get("matchday_complete")
            and payload.get("xg_complete")
            and payload.get("market_values_complete", True)
        ):
            payload.setdefault("reason", "matchday, xG or market-value data incomplete")
            finish_run(settings.database_path, run_id, _now().isoformat(), "deferred", payload)
            return "deferred"
        if job == "model":
            if payload.get("season_complete"):
                finish_run(settings.database_path, run_id, _now().isoformat(), "success", payload)
                return "success"
            snapshot_path = payload.get("snapshot_path")
            if not snapshot_path:
                raise ValueError("model adapter did not return snapshot_path")
            payload["published_artifact"] = str(publish_file(settings.database_path, settings.data_dir, snapshot_path))
        elif job == "results":
            results = payload.get("results")
            if not isinstance(results, list):
                raise ValueError("results adapter did not return a results list")
            teams = payload.get("teams")
            fixtures = payload.get("fixtures")
            if teams is not None or fixtures is not None:
                if not isinstance(teams, list) or not isinstance(fixtures, list):
                    raise ValueError("schedule sync requires teams and fixtures lists")
                payload["fixtures_synced"] = sync_schedule(settings.database_path, teams, fixtures)
            payload["recorded"] = record_results(settings.database_path, results, payload.get("source", "configured adapter"))
        finish_run(settings.database_path, run_id, _now().isoformat(), "success", payload)
        return "success"
    except subprocess.CalledProcessError as exc:
        details = {"error": str(exc), "returncode": exc.returncode}
        if exc.stdout:
            details["stdout"] = exc.stdout[-8000:]
        if exc.stderr:
            details["stderr"] = exc.stderr[-8000:]
        finish_run(settings.database_path, run_id, _now().isoformat(), "failed", details)
        return "failed"
    except Exception as exc:
        finish_run(settings.database_path, run_id, _now().isoformat(), "failed", {"error": str(exc)})
        return "failed"


def _state(settings: Settings, job: str):
    from .storage import connect
    with connect(settings.database_path) as connection:
        row = connection.execute("SELECT last_attempt_at, last_success_at, last_status FROM scheduler_state WHERE job = ?", (job,)).fetchone()
    if not row:
        return None
    return {
        "attempt": datetime.fromisoformat(row["last_attempt_at"]),
        "success": datetime.fromisoformat(row["last_success_at"]) if row["last_success_at"] else None,
        "status": row["last_status"],
    }


def _mark_attempt(settings: Settings, job: str, status: str) -> None:
    now = _now().isoformat()
    with transaction(settings.database_path) as connection:
        connection.execute(
            """INSERT INTO scheduler_state(job, last_attempt_at, last_success_at, last_status) VALUES (?, ?, ?, ?)
               ON CONFLICT(job) DO UPDATE SET last_attempt_at = excluded.last_attempt_at,
               last_success_at = CASE WHEN excluded.last_success_at IS NOT NULL THEN excluded.last_success_at ELSE scheduler_state.last_success_at END,
               last_status = excluded.last_status""",
            (job, now, now if status == "success" else None, status),
        )


def tick(settings: Settings) -> None:
    now = _now()
    local = now.astimezone(ZoneInfo(settings.timezone))
    match_window = (
        (local.weekday() == 4 and local.hour >= 18)
        or (local.weekday() in {5, 6} and 13 <= local.hour <= 23)
        or (local.weekday() == 0 and local.hour <= 1)
        or (local.weekday() in {1, 2} and 18 <= local.hour <= 23)
    )
    results_interval = settings.results_interval_minutes if match_window else 24 * 60
    results_state = _state(settings, "results")
    if results_state is None or now - results_state["attempt"] >= timedelta(minutes=results_interval):
        _mark_attempt(settings, "results", run_job(settings, "results"))

    week_start = (local - timedelta(days=local.weekday())).replace(
        hour=settings.model_hour, minute=settings.model_minute, second=0, microsecond=0
    )
    model_state = _state(settings, "model")
    already_succeeded = model_state is not None and model_state["success"] is not None and model_state["success"].astimezone(ZoneInfo(settings.timezone)) >= week_start
    retry_due = model_state is None or now - model_state["attempt"] >= timedelta(hours=2)
    in_retry_window = week_start <= local < week_start + timedelta(days=2)
    if in_retry_window and not already_succeeded and retry_due:
        _mark_attempt(settings, "model", run_job(settings, "model"))


def main() -> None:
    settings = Settings.from_env()
    settings.ensure_directories()
    initialize(settings.database_path)
    while True:
        tick(settings)
        time.sleep(30)


if __name__ == "__main__":
    main()
