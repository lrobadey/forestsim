"""Terrain layer definitions and DEM processing stubs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import LandscapeConfig


def _aspect_from_gradient(grad_x: np.ndarray, grad_y: np.ndarray) -> np.ndarray:
    """Return downslope aspect in the same convention as terrain initialization."""

    return (np.degrees(np.arctan2(-grad_x, -grad_y)) + 360.0).astype(np.float32) % 360.0


@dataclass
class TerrainLayers:
    elevation: np.ndarray
    slope: np.ndarray
    aspect: np.ndarray
    twi: np.ndarray
    flow_accumulation: np.ndarray
    curvature: np.ndarray

    @classmethod
    def synthetic(cls, config: LandscapeConfig) -> "TerrainLayers":
        """Generate a smooth synthetic terrain surface for smoke tests."""

        rows, cols = config.shape
        y = np.linspace(0.0, 1.0, rows, dtype=np.float32)
        x = np.linspace(0.0, 1.0, cols, dtype=np.float32)
        xx, yy = np.meshgrid(x, y)

        elevation = (
            900.0
            + 140.0 * yy
            + 55.0 * np.sin(2.0 * np.pi * xx)
            + 25.0 * np.cos(3.0 * np.pi * yy)
            + 18.0 * np.sin(2.0 * np.pi * (xx + yy))
        ).astype(np.float32)

        if rows > 1 and cols > 1:
            grad_y, grad_x = np.gradient(elevation, config.cell_size_m)
            slope = np.degrees(np.arctan(np.hypot(grad_x, grad_y))).astype(np.float32)
            aspect = _aspect_from_gradient(grad_x, grad_y)
            dyy, _ = np.gradient(grad_y, config.cell_size_m)
            _, dxx = np.gradient(grad_x, config.cell_size_m)
            curvature = (dxx + dyy).astype(np.float32)
        else:
            slope = np.zeros((rows, cols), dtype=np.float32)
            aspect = np.zeros((rows, cols), dtype=np.float32)
            curvature = np.zeros((rows, cols), dtype=np.float32)

        wetness = 7.0 + 2.2 * (1.0 - yy) - 0.08 * slope + 0.6 * np.cos(np.pi * xx)
        twi = np.clip(wetness, 2.0, 12.0).astype(np.float32)
        flow_accumulation = (1.0 + 60.0 * (1.0 - yy) ** 2 + 8.0 * np.sin(np.pi * xx) ** 2).astype(np.float32)

        return cls(
            elevation=elevation,
            slope=slope,
            aspect=aspect,
            twi=twi,
            flow_accumulation=flow_accumulation,
            curvature=curvature,
        )
