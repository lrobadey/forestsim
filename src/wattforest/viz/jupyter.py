"""Jupyter-friendly helpers for inspecting an engine snapshot."""

from __future__ import annotations

from typing import Any

import numpy as np


def build_map(engine, layer: str = "canopy_height") -> dict[str, Any]:
    """Return a serializable layer snapshot for notebook rendering."""

    if layer == "canopy_height":
        grid = engine.dominant_height_grid()
    elif layer == "mean_age":
        grid = engine.mean_age_grid()
    elif layer == "gap_mask":
        grid = (engine.canopy_cover_grid() < 0.3).astype(np.uint8)
    elif layer == "recent_fire_severity":
        grid = np.asarray([[float(cell.recent_fire_severity) for cell in row] for row in engine.vegetation], dtype=np.float32)
    else:
        raise ValueError(f"Unsupported layer for build_map: {layer}")
    return {"layer": layer, "shape": list(grid.shape), "values": np.asarray(grid).tolist()}

