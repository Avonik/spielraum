from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
WEB = ROOT / "web"


def clean_environment() -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in os.environ.items():
        canonical = "PATH" if key.lower() == "path" else key
        cleaned[canonical] = value
    cleaned.update({
        "SPIELRAUM_DATA_DIR": str(RUNTIME),
        "UV_CACHE_DIR": str(ROOT / ".uv-cache-live"),
        "UV_PYTHON_INSTALL_DIR": str(ROOT / ".uv-python-live"),
    })
    return cleaned


def start(command: list[str], *, cwd: Path, log_name: str, environment: dict[str, str]) -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    output = (RUNTIME / f"{log_name}.log").open("ab")
    errors = (RUNTIME / f"{log_name}-error.log").open("ab")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=output,
        stderr=errors,
        creationflags=flags,
        close_fds=True,
    )
    return process.pid


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local Spielraum preview")
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--web-only", action="store_true")
    args = parser.parse_args()
    if args.api_only and args.web_only:
        raise ValueError("--api-only and --web-only are mutually exclusive")
    environment = clean_environment()
    uv = shutil.which("uv", path=environment.get("PATH"))
    npm = shutil.which("npm.cmd", path=environment.get("PATH"))
    if not uv or not npm:
        raise RuntimeError("uv oder npm wurde nicht gefunden")
    api = [
        uv, "run", "--no-project", "--python", sys.executable,
        "--with-requirements", "portfolio-requirements.txt",
        "uvicorn", "spielraum.api:app", "--host", "127.0.0.1", "--port", "8000",
    ]
    web = [
        os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", npm,
        "run", "dev", "--", "--host", "127.0.0.1",
    ]
    if not args.web_only:
        api_pid = start(api, cwd=ROOT, log_name="api-dev", environment=environment)
        print(f"API_PID={api_pid}")
    if not args.api_only:
        web_pid = start(web, cwd=WEB, log_name="web-dev", environment=environment)
        print(f"WEB_PID={web_pid}")


if __name__ == "__main__":
    main()
