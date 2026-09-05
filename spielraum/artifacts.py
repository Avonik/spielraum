from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: str | Path, payload: Any) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return hashlib.sha256(data).hexdigest()


def export_release(database_path: str | Path, export_root: str | Path) -> Path:
    source = Path(database_path).resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = Path(export_root).resolve() / stamp
    target.mkdir(parents=True, exist_ok=False)
    database_copy = target / "spielraum.sqlite3"
    with sqlite3.connect(source) as source_db, sqlite3.connect(database_copy) as target_db:
        source_db.backup(target_db)

    artifacts_source = source.parent / "artifacts"
    if artifacts_source.exists():
        shutil.copytree(artifacts_source, target / "artifacts")
    files = sorted(p for p in target.rglob("*") if p.is_file())
    manifest = {
        "format": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "architecture_independent": True,
        "files": [{"path": p.relative_to(target).as_posix(), "sha256": sha256_file(p), "bytes": p.stat().st_size} for p in files],
    }
    write_json_atomic(target / "manifest.json", manifest)
    return target
