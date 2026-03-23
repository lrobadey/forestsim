"""Windthrow module scaffold."""

from __future__ import annotations

from typing import Dict

import numpy as np
from scipy.ndimage import uniform_filter

from ..rng import DeterministicRNG
from ..soils import SoilLayers
from ..species import SpeciesParams
from ..terrain import TerrainLayers


class WindthrowModule:
    def apply_windstorm(
        self,
        wind_speed_ms: float,
        wind_dir_deg: float,
        affected_mask: np.ndarray,
        vegetation_grid: np.ndarray,
        terrain: TerrainLayers,
        soil: SoilLayers,
        species: Dict[int, SpeciesParams],
        rng: DeterministicRNG,
        year: int,
        damage_scalar: float = 1.0,
    ) -> np.ndarray:
        _ = species
        damage = np.zeros(affected_mask.shape, dtype=np.float32)
        wind_from_deg = (wind_dir_deg + 180.0) % 360.0
        aspect_alignment = np.cos(np.radians(terrain.aspect - wind_from_deg))
        exposure = np.clip(0.5 + 0.5 * aspect_alignment, 0.0, 1.0)
        local_mean_elev = uniform_filter(terrain.elevation, size=5)
        relative_elevation = (terrain.elevation - local_mean_elev) / max(1.0, float(terrain.elevation.std()))
        ridge_exposure = np.clip(relative_elevation, 0.0, 2.0) / 2.0
        edge_exposure = self._edge_exposure(vegetation_grid)
        for row in range(affected_mask.shape[0]):
            for col in range(affected_mask.shape[1]):
                if not affected_mask[row, col]:
                    continue
                cell = vegetation_grid[row, col]
                if not cell.cohorts or cell.dominant_height_m < 5.0:
                    continue
                root_depth_factor = min(1.0, soil.depth_to_restriction[row, col] / 100.0)
                mean_trait = self._mean_trait_scalars(cell, species)
                # TODO: Revisit this critical-wind relationship against
                # windthrow literature. It is currently heuristic and also uses
                # flammability as a mechanical-failure driver, which needs
                # either a clear justification or removal.
                critical_wind_speed = (
                    18.0
                    + 12.0 * root_depth_factor
                    + 4.0 * mean_trait["drought_tolerance"]
                    - 0.22 * cell.dominant_height_m
                    - 3.0 * mean_trait["flammability"]
                )
                effective_wind = wind_speed_ms * (
                    0.25
                    + 0.55 * exposure[row, col]
                    + 0.45 * ridge_exposure[row, col]
                    + 0.55 * edge_exposure[row, col]
                )
                if effective_wind <= critical_wind_speed:
                    continue
                exceedance = (effective_wind - critical_wind_speed) / critical_wind_speed
                damage_prob = min(0.95, exceedance * (1.1 + 0.6 * mean_trait["height_risk"]) * damage_scalar)
                if rng.uniform("windthrow", year, row, col) < damage_prob:
                    damage[row, col] = min(
                        1.0,
                        exceedance * (0.75 + 0.35 * edge_exposure[row, col] + 0.2 * mean_trait["height_risk"]),
                    )
        return damage

    def _edge_exposure(self, vegetation_grid: np.ndarray) -> np.ndarray:
        height = np.zeros(vegetation_grid.shape, dtype=np.float32)
        for row in range(vegetation_grid.shape[0]):
            for col in range(vegetation_grid.shape[1]):
                height[row, col] = float(vegetation_grid[row, col].dominant_height_m)
        local_mean = uniform_filter(height, size=3)
        return np.clip((height - local_mean + 4.0) / 12.0, 0.0, 1.0)

    def _mean_trait_scalars(self, cell, species: Dict[int, SpeciesParams]) -> dict[str, float]:
        total_biomass = max(sum(max(0.0, cohort.biomass_kg_ha) for cohort in cell.cohorts), 1e-6)
        weighted_flammability = 0.0
        weighted_drought_tolerance = 0.0
        weighted_height_risk = 0.0
        for cohort in cell.cohorts:
            params = species[cohort.species_id]
            weight = max(0.0, cohort.biomass_kg_ha) / total_biomass
            weighted_flammability += weight * float(params.flammability)
            weighted_drought_tolerance += weight * float(params.drought_tolerance)
            weighted_height_risk += weight * float(
                np.clip(
                    cohort.canopy_height_m / max(params.h_max_m, 1.0) + (1.0 - params.wood_density_kg_m3 / 900.0),
                    0.0,
                    1.5,
                )
            )
        return {
            "flammability": weighted_flammability,
            "drought_tolerance": weighted_drought_tolerance,
            "height_risk": weighted_height_risk,
        }
