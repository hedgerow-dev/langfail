"""Runtime settings, read from ``LARCHWAY_*`` environment variables.

Defaults are tuned for a single-machine dev setup so ``larchway serve`` works
out of the box. Tests build a ``Settings`` directly instead of touching the
environment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    session_key: str = "larchway-workbench-local-session-key"
    session_algorithm: str = "HS256"
    session_ttl_seconds: int = 8 * 3600
    runner_key: str = ""
    confine_reads: bool = False
    debug: bool = False

    @property
    def database_path(self) -> Path:
        return self.data_dir / "workbench.sqlite3"

    @property
    def workspace_file(self) -> Path:
        return self.data_dir / "workspace.json"

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            data_dir=Path(env.get("LARCHWAY_HOME", Path.home() / ".larchway")),
            session_key=env.get("LARCHWAY_SESSION_KEY", cls.session_key),
            session_ttl_seconds=int(env.get("LARCHWAY_SESSION_TTL", cls.session_ttl_seconds)),
            runner_key=env.get("LARCHWAY_RUNNER_KEY", cls.runner_key),
            confine_reads=env.get("LARCHWAY_CONFINE_READS", "0") == "1",
            debug=env.get("LARCHWAY_DEBUG", "0") == "1",
        )
