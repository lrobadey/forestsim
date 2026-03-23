"""Checkpoint persistence scaffold."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any


def save_checkpoint(path: str | Path, state: Any) -> None:
    Path(path).write_bytes(pickle.dumps(state))


def load_checkpoint(path: str | Path) -> Any:
    return pickle.loads(Path(path).read_bytes())
