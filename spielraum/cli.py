from __future__ import annotations

import argparse

from .artifacts import export_release
from .config import Settings
from .scheduler import run_job
from .publish import publish_file
from .seed import seed_preview
from .storage import initialize, read_dashboard


def main() -> None:
    parser = argparse.ArgumentParser(description="Spielraum publishing pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser("init", help="Initialize the SQLite database")
    init_parser.add_argument("--seed-preview", action="store_true")
    sub.add_parser("show", help="Print the dashboard payload")
    sub.add_parser("export", help="Create a hashed desktop-to-Pi release bundle")
    run_parser = sub.add_parser("run", help="Run a configured pipeline adapter")
    run_parser.add_argument("job", choices=("results", "model"))
    publish_parser = sub.add_parser("publish", help="Validate and publish a model snapshot JSON")
    publish_parser.add_argument("snapshot")
    args = parser.parse_args()

    settings = Settings.from_env()
    settings.ensure_directories()
    initialize(settings.database_path)
    if args.command == "init":
        if args.seed_preview:
            seed_preview(settings.database_path)
        print(settings.database_path)
    elif args.command == "show":
        import json
        print(json.dumps(read_dashboard(settings.database_path), ensure_ascii=False, indent=2))
    elif args.command == "export":
        print(export_release(settings.database_path, settings.data_dir / "exports"))
    elif args.command == "run":
        status = run_job(settings, args.job)
        print(status)
        if status in {"failed", "deferred", "skipped"}:
            import json
            from .storage import connect
            with connect(settings.database_path, readonly=True) as connection:
                row = connection.execute(
                    "SELECT details_json FROM pipeline_runs WHERE job = ? ORDER BY id DESC LIMIT 1",
                    (args.job,),
                ).fetchone()
            if row and row["details_json"]:
                print(json.dumps(json.loads(row["details_json"]), ensure_ascii=False, indent=2))
    elif args.command == "publish":
        print(publish_file(settings.database_path, settings.data_dir, args.snapshot))


if __name__ == "__main__":
    main()
