from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    timezone: str = "Europe/Berlin"
    model_weekday: int = 0  # Monday
    model_hour: int = 3
    model_minute: int = 30
    results_interval_minutes: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("SPIELRAUM_DATA_DIR", "runtime")).resolve()
        database_path = Path(
            os.environ.get("SPIELRAUM_DATABASE", data_dir / "spielraum.sqlite3")
        ).resolve()
        return cls(data_dir=data_dir, database_path=database_path)

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "artifacts").mkdir(exist_ok=True)
        (self.data_dir / "exports").mkdir(exist_ok=True)
