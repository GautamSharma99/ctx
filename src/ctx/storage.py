from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CTX_DIRNAME = ".ctx"


@dataclass
class Paths:
    root: Path

    @property
    def ctx_dir(self) -> Path:
        return self.root / CTX_DIRNAME

    @property
    def sessions_dir(self) -> Path:
        return self.ctx_dir / "sessions"

    @property
    def index_path(self) -> Path:
        return self.ctx_dir / "index.json"

    @property
    def current_path(self) -> Path:
        return self.ctx_dir / "current.md"

    @property
    def config_path(self) -> Path:
        return self.ctx_dir / "config.yaml"


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from `start` looking for a .ctx directory. Fall back to cwd."""
    start = (start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / CTX_DIRNAME).is_dir():
            return candidate
    return start


def ensure_initialized(paths: Paths) -> None:
    if not paths.ctx_dir.is_dir():
        raise RuntimeError(
            f"No {CTX_DIRNAME}/ directory found at {paths.root}. "
            "Run `ctx init` first."
        )


def init_project(root: Path) -> Paths:
    paths = Paths(root=root.resolve())
    paths.ctx_dir.mkdir(exist_ok=True)
    paths.sessions_dir.mkdir(exist_ok=True)
    if not paths.index_path.exists():
        paths.index_path.write_text(json.dumps({"sessions": []}, indent=2))
    return paths


def load_index(paths: Paths) -> dict[str, Any]:
    if not paths.index_path.exists():
        return {"sessions": []}
    return json.loads(paths.index_path.read_text())


def save_index(paths: Paths, index: dict[str, Any]) -> None:
    paths.index_path.write_text(json.dumps(index, indent=2))


def append_index_entry(paths: Paths, entry: dict[str, Any]) -> None:
    index = load_index(paths)
    # De-duplicate by session_id + source: replace prior entry if present.
    key = (entry.get("source"), entry.get("session_id"))
    index["sessions"] = [
        s for s in index.get("sessions", [])
        if (s.get("source"), s.get("session_id")) != key
    ]
    index["sessions"].append(entry)
    save_index(paths, index)


def session_basename(started_at: str, session_id: str) -> str:
    # started_at is ISO; take the date portion for filename readability.
    try:
        date = started_at[:10]
    except Exception:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{date}-{session_id}"


def write_transcript(paths: Paths, transcript: dict[str, Any]) -> Path:
    base = session_basename(transcript.get("started_at", ""), transcript["session_id"])
    path = paths.sessions_dir / f"{base}.transcript.json"
    path.write_text(json.dumps(transcript, indent=2))
    return path


def write_snapshot(paths: Paths, transcript: dict[str, Any], snapshot_md: str) -> Path:
    base = session_basename(transcript.get("started_at", ""), transcript["session_id"])
    path = paths.sessions_dir / f"{base}.snapshot.md"
    path.write_text(snapshot_md)
    return path


def write_current(paths: Paths, snapshot_md: str) -> Path:
    paths.current_path.write_text(snapshot_md)
    return paths.current_path
