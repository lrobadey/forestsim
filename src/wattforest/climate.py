"""Climate layer definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from .config import LandscapeConfig
from .terrain import TerrainLayers


@dataclass
class ClimateLayers:
    growing_degree_days: np.ndarray
    annual_precip_mm: np.ndarray
    drought_index: np.ndarray
    frost_free_days: np.ndarray

    def copy(self) -> "ClimateLayers":
        return ClimateLayers(
            growing_degree_days=np.array(self.growing_degree_days, copy=True),
            annual_precip_mm=np.array(self.annual_precip_mm, copy=True),
            drought_index=np.array(self.drought_index, copy=True),
            frost_free_days=np.array(self.frost_free_days, copy=True),
        )

    @classmethod
    def synthetic(
        cls,
        config: LandscapeConfig,
        terrain: TerrainLayers | None = None,
    ) -> "ClimateLayers":
        """Generate a mild climate gradient for phase-0 runs."""

        rows, cols = config.shape
        y = np.linspace(0.0, 1.0, rows, dtype=np.float32)
        x = np.linspace(0.0, 1.0, cols, dtype=np.float32)
        xx, yy = np.meshgrid(x, y)
        elevation = terrain.elevation if terrain is not None else np.zeros(config.shape, dtype=np.float32)
        elev_norm = (elevation - elevation.min()) / max(1e-6, float(elevation.max() - elevation.min()))

        growing_degree_days = np.clip(2200.0 - 650.0 * elev_norm + 120.0 * np.sin(np.pi * xx), 900.0, 2600.0).astype(np.float32)
        annual_precip_mm = np.clip(780.0 + 260.0 * (1.0 - yy) + 110.0 * np.cos(np.pi * xx / 2.0), 550.0, 1400.0).astype(np.float32)
        drought_index = np.clip(0.55 - (annual_precip_mm - 780.0) / 1200.0 + 0.12 * elev_norm, 0.05, 0.65).astype(np.float32)
        frost_free_days = np.clip(185.0 - 40.0 * elev_norm + 10.0 * np.sin(2.0 * np.pi * yy), 95.0, 210.0).astype(np.int16)

        return cls(
            growing_degree_days=growing_degree_days,
            annual_precip_mm=annual_precip_mm,
            drought_index=drought_index,
            frost_free_days=frost_free_days,
        )


@dataclass
class ClimateScenario:
    """Engine-owned baseline climate plus optional year-specific overrides."""

    baseline: ClimateLayers
    yearly_overrides: dict[int, ClimateLayers] = field(default_factory=dict)

    @classmethod
    def from_baseline(
        cls,
        baseline: ClimateLayers,
        yearly_overrides: Mapping[int, ClimateLayers] | None = None,
    ) -> "ClimateScenario":
        return cls(
            baseline=baseline.copy(),
            yearly_overrides={
                int(year): layers.copy() for year, layers in dict(yearly_overrides or {}).items()
            },
        )

    def for_year(self, year: int) -> ClimateLayers:
        layers = self.yearly_overrides.get(int(year), self.baseline)
        return layers.copy()
