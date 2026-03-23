"""Optional LANDFIRE helpers for local fallback workflows."""

from __future__ import annotations

from pathlib import Path

from ..config import LandscapeConfig
from .geospatial import read_raster_to_grid


def load_landfire_layers(
    landfire_paths: dict[str, str | Path],
    config: LandscapeConfig,
    *,
    categorical_keys: set[str] | None = None,
) -> dict[str, object]:
    """Load LANDFIRE rasters onto the engine grid as an optional helper."""

    categorical_keys = categorical_keys or {"evt", "bps", "fuel_model"}
    layers: dict[str, object] = {}
    for layer_name, layer_path in landfire_paths.items():
        layers[layer_name] = read_raster_to_grid(
            layer_path,
            config,
            categorical=layer_name in categorical_keys,
            fail_on_nodata=False,
        )
    return layers
