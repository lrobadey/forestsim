"""Soil layer definitions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import LandscapeConfig
from .terrain import TerrainLayers


@dataclass
class SoilLayers:
    awc: np.ndarray
    depth_to_restriction: np.ndarray
    texture_class: np.ndarray
    rock_fraction: np.ndarray

    @classmethod
    def synthetic(
        cls,
        config: LandscapeConfig,
        terrain: TerrainLayers | None = None,
    ) -> "SoilLayers":
        """Generate simple synthetic soils aligned to terrain."""

        rows, cols = config.shape
        y = np.linspace(0.0, 1.0, rows, dtype=np.float32)
        x = np.linspace(0.0, 1.0, cols, dtype=np.float32)
        xx, yy = np.meshgrid(x, y)
        slope = terrain.slope if terrain is not None else np.zeros(config.shape, dtype=np.float32)
        twi = terrain.twi if terrain is not None else np.full(config.shape, 6.0, dtype=np.float32)

        awc = np.clip(95.0 + 8.0 * twi - 1.5 * slope + 10.0 * (1.0 - yy), 45.0, 210.0).astype(np.float32)
        rock_fraction = np.clip(0.05 + 0.012 * slope + 0.08 * xx, 0.02, 0.55).astype(np.float32)
        depth_to_restriction = np.clip(140.0 - 120.0 * rock_fraction + 8.0 * np.cos(np.pi * yy), 25.0, 170.0).astype(np.float32)

        texture_class = np.zeros((rows, cols), dtype=np.uint8)
        texture_class[:, :] = 1
        texture_class[:, cols // 3 : 2 * cols // 3] = 2
        texture_class[:, 2 * cols // 3 :] = 3

        return cls(
            awc=awc,
            depth_to_restriction=depth_to_restriction,
            texture_class=texture_class,
            rock_fraction=rock_fraction,
        )
