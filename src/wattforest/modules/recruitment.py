"""Recruitment module scaffold."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
from scipy.signal import fftconvolve

from ..climate import ClimateLayers
from ..config import LandscapeConfig
from ..rng import DeterministicRNG
from ..soils import SoilLayers
from ..species import SpeciesParams
from ..state import CellVegetation, Cohort
from ..terrain import TerrainLayers


class RecruitmentModule:
    def compute_seed_rain(
        self,
        species_id: int,
        species: SpeciesParams,
        vegetation_grid: np.ndarray,
        config: LandscapeConfig,
    ) -> np.ndarray:
        rows, cols = config.shape
        source = np.zeros((rows, cols), dtype=np.float32)
        for row in range(rows):
            for col in range(cols):
                cell = vegetation_grid[row, col]
                for cohort in cell.cohorts:
                    if cohort.species_id == species_id and cohort.age >= species.maturity_age_yr:
                        source[row, col] += species.fecundity_seeds_yr * cohort.density_stems_ha / 1000.0
        radius = min(int(np.ceil(species.dispersal_mean_m * 5 / config.cell_size_m)), 50)
        kernel = self._build_2dt_kernel(
            species.dispersal_mean_m,
            species.dispersal_fat_tail_p,
            config.cell_size_m,
            radius,
        )
        return np.maximum(0.0, fftconvolve(source, kernel, mode="same"))

    def _build_2dt_kernel(self, mean_dist: float, fat_tail_p: float, cell_size: float, radius_cells: int) -> np.ndarray:
        size = 2 * radius_cells + 1
        kernel = np.zeros((size, size), dtype=np.float64)
        p = max(1.1, fat_tail_p)
        u = mean_dist * (p - 1.0) / np.sqrt(np.pi * p)
        for i in range(size):
            for j in range(size):
                dx = (i - radius_cells) * cell_size
                dy = (j - radius_cells) * cell_size
                r_sq = dx**2 + dy**2
                kernel[i, j] = (p - 1.0) / (np.pi * u**2) * (1.0 + r_sq / u**2) ** (-p)
        kernel *= cell_size**2
        kernel /= kernel.sum()
        return kernel

    def establish_recruits(
        self,
        seed_rain: np.ndarray,
        species: SpeciesParams,
        ground_light: np.ndarray,
        terrain: TerrainLayers,
        soil: SoilLayers,
        climate: ClimateLayers,
        vegetation_grid: np.ndarray,
        rng: DeterministicRNG,
        year: int,
        establishment_scalar: np.ndarray | None = None,
        moisture_bonus: np.ndarray | None = None,
        recruitment_base_scalar: float = 1.0,
        recruitment_disturbance_scalar: float = 1.0,
    ) -> List[Tuple[int, int, Cohort]]:
        new_cohorts: List[Tuple[int, int, Cohort]] = []
        twi_min = float(np.min(terrain.twi))
        twi_span = max(1e-6, float(np.ptp(terrain.twi)))
        for row in range(seed_rain.shape[0]):
            for col in range(seed_rain.shape[1]):
                if seed_rain[row, col] < 0.1:
                    continue
                if species.shade_tolerance < 1.6:
                    required_light = max(0.48, species.light_compensation_frac + 0.28)
                elif species.shade_tolerance < 3.0:
                    required_light = max(0.34, species.light_compensation_frac + 0.18)
                else:
                    required_light = max(0.05, species.light_compensation_frac + 0.02)
                light_ok = ground_light[row, col] > required_light
                if not light_ok:
                    continue
                gdd = climate.growing_degree_days[row, col]
                if gdd < species.gdd_min or gdd > species.gdd_max:
                    continue
                awc = float(soil.awc[row, col])
                depth = float(soil.depth_to_restriction[row, col])
                rock = float(np.clip(soil.rock_fraction[row, col], 0.0, 1.0))
                terrain_wetness = float(np.clip((terrain.twi[row, col] - twi_min) / twi_span, 0.0, 1.0))
                slope_scalar = float(np.clip(1.0 - terrain.slope[row, col] / 85.0, 0.35, 1.0))
                soil_scalar = float(
                    np.clip((0.45 + awc / 180.0) * (0.7 + 0.3 * depth / 100.0) * (1.0 - 0.15 * rock), 0.35, 1.15)
                )
                moisture_scalar = float(
                    np.clip(
                        0.7 + 0.3 * terrain_wetness - 0.18 * climate.drought_index[row, col],
                        0.45,
                        1.15,
                    )
                )
                cell: CellVegetation = vegetation_grid[row, col]
                disturbance_window = cell.regeneration_delay_yr > 0 or cell.recent_disturbance_severity > 0.2
                substrate_bonus = cell.mineral_soil_exposed_frac if species.shade_tolerance < 3 else 0.35 * cell.mineral_soil_exposed_frac
                base_prob = min(0.82, seed_rain[row, col] / 30.0)
                prob = recruitment_base_scalar * base_prob * (0.35 + 0.65 * substrate_bonus)
                prob *= soil_scalar * moisture_scalar * slope_scalar
                if establishment_scalar is not None:
                    prob *= max(0.0, float(establishment_scalar[row, col]))
                if moisture_bonus is not None:
                    prob *= 1.0 + 0.35 * max(0.0, float(moisture_bonus[row, col]))
                if disturbance_window:
                    if species.shade_tolerance < 3:
                        prob *= 1.0 + recruitment_disturbance_scalar * (
                            0.25 + 2.2 * cell.recent_fire_severity + 1.0 * cell.recent_disturbance_severity
                        )
                    else:
                        prob *= max(
                            0.08,
                            1.0
                            - recruitment_disturbance_scalar
                            * (0.35 + 1.4 * cell.recent_fire_severity + 0.35 * cell.recent_disturbance_severity),
                        )
                if cell.regeneration_delay_yr > 0:
                    if species.shade_tolerance < 3:
                        prob *= 0.85 + 0.15 * cell.mineral_soil_exposed_frac
                    else:
                        prob *= 0.2
                if rng.uniform("recruitment", year, row, col, species.species_id) < prob:
                    recruit_biomass = max(12.0, species.seed_mass_g * seed_rain[row, col] * 4.0)
                    recruit_density = max(35.0, seed_rain[row, col] * prob * 8.0)
                    if disturbance_window and species.shade_tolerance < 3:
                        disturbance_scalar = 1.0 + recruitment_disturbance_scalar * (
                            1.4 * cell.recent_fire_severity + 0.45 * cell.recent_disturbance_severity
                        )
                        recruit_biomass *= disturbance_scalar
                        recruit_density *= disturbance_scalar
                    new_cohorts.append(
                        (
                            row,
                            col,
                            Cohort(
                                species_id=species.species_id,
                                age=0,
                                biomass_kg_ha=recruit_biomass,
                                density_stems_ha=recruit_density,
                                canopy_height_m=0.6,
                                crown_cover_frac=0.02,
                                vigor=1.0,
                            ),
                        )
                    )
        return new_cohorts
