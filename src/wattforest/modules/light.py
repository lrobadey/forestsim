"""Light competition module scaffold."""

from __future__ import annotations

from typing import Dict

import numpy as np

from ..species import SpeciesParams
from ..state import CellVegetation


class LightModule:
    def __init__(self, k_extinction: float = 0.5):
        self.k = k_extinction

    def compute_light(self, cell: CellVegetation, species: Dict[int, SpeciesParams]) -> Dict[int, float]:
        if not cell.cohorts:
            return {}
        sorted_indices = sorted(
            range(len(cell.cohorts)),
            key=lambda idx: cell.cohorts[idx].canopy_height_m,
            reverse=True,
        )
        cumulative_lai = 0.0
        available_light: Dict[int, float] = {}
        for idx in sorted_indices:
            cohort = cell.cohorts[idx]
            params = species[cohort.species_id]
            available_light[idx] = float(np.exp(-self.k * cumulative_lai))
            cohort_lai = (
                cohort.biomass_kg_ha * params.specific_leaf_area * cohort.crown_cover_frac / 10000.0
            )
            cumulative_lai += cohort_lai
        return available_light

    def ground_light(self, cell: CellVegetation, species: Dict[int, SpeciesParams]) -> float:
        total_lai = sum(
            cohort.biomass_kg_ha
            * species[cohort.species_id].specific_leaf_area
            * cohort.crown_cover_frac
            / 10000.0
            for cohort in cell.cohorts
        )
        return float(np.exp(-self.k * total_lai))
