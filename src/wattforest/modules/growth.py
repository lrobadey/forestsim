"""Growth module scaffold."""

from __future__ import annotations

import numpy as np

from ..climate import ClimateLayers
from ..soils import SoilLayers
from ..species import SpeciesParams
from ..state import Cohort
from .structure import recompute_cohort_structure


class GrowthModule:
    def grow_cohort(
        self,
        cohort: Cohort,
        species: SpeciesParams,
        available_light: float,
        climate: ClimateLayers,
        soil: SoilLayers,
        row: int,
        col: int,
    ) -> float:
        relative_age = cohort.age / species.age_max_yr if species.age_max_yr else 0.0
        size_scalar = max(0.18, 1.0 - relative_age**1.35)
        potential = species.g_max_cm_yr * 260.0 * size_scalar

        light_min = species.light_compensation_frac
        light_span = max(0.05, species.light_saturation_frac - light_min)
        light_scalar = np.clip((available_light - light_min) / light_span, 0.03, 1.0)

        gdd = climate.growing_degree_days[row, col]
        gdd_range = species.gdd_max - species.gdd_min
        gdd_scalar = 1.0
        if gdd_range > 0:
            gdd_opt = (species.gdd_min + species.gdd_max) / 2.0
            gdd_scalar = max(0.0, 1.0 - ((gdd - gdd_opt) / max(gdd_range / 2.0, 1e-6)) ** 2)

        precip_scalar = float(np.clip(climate.annual_precip_mm[row, col] / 1000.0, 0.8, 1.15))
        frost_scalar = float(
            np.clip(
                climate.frost_free_days[row, col] / max(float(species.frost_tolerance), 1.0),
                0.8,
                1.0,
            )
        )

        awc = soil.awc[row, col]
        depth = soil.depth_to_restriction[row, col]
        rock = soil.rock_fraction[row, col]
        drought = climate.drought_index[row, col]
        soil_scalar = (
            min(1.0, awc / 150.0)
            * (0.9 + 0.1 * min(1.0, depth / 120.0))
            * (1.0 - drought * (1.0 - species.drought_tolerance))
            * (1.0 - 0.1 * float(np.clip(rock, 0.0, 1.0)))
        )
        density_scalar = 1.0 / (1.0 + cohort.density_stems_ha / 1400.0)
        competition_scalar = max(0.18, 1.0 - 0.6 * cohort.crown_cover_frac)
        return max(
            0.0,
            potential
            * light_scalar
            * gdd_scalar
            * precip_scalar
            * frost_scalar
            * soil_scalar
            * (0.65 + 0.35 * density_scalar)
            * competition_scalar,
        )

    def update_allometry(self, cohort: Cohort, species: SpeciesParams, delta_biomass: float) -> None:
        cohort.biomass_kg_ha += delta_biomass
        cohort.age += 1
        recompute_cohort_structure(cohort, species)
