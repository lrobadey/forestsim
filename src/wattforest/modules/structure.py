"""Shared helpers for normalizing cohort structure."""

from __future__ import annotations

import numpy as np

from ..species import SpeciesParams
from ..state import Cohort


def recompute_cohort_structure(cohort: Cohort, species: SpeciesParams) -> None:
    """Recompute derived cohort structure from biomass, density, and traits."""

    cohort.biomass_kg_ha = max(0.0, float(cohort.biomass_kg_ha))
    cohort.density_stems_ha = max(0.0, float(cohort.density_stems_ha))
    cohort.canopy_height_m = float(
        species.h_max_m * (1.0 - np.exp(-0.00011 * cohort.biomass_kg_ha))
    )
    cover_from_biomass = 1.0 - np.exp(-cohort.biomass_kg_ha / 11000.0)
    cover_from_density = 1.0 - np.exp(-cohort.density_stems_ha / 280.0)
    cohort.crown_cover_frac = float(
        np.clip(0.78 * cover_from_biomass + 0.22 * cover_from_density, 0.0, 0.95)
    )
    cohort.leaf_area_index = float(
        max(
            0.0,
            cohort.biomass_kg_ha * species.specific_leaf_area * cohort.crown_cover_frac / 10000.0,
        )
    )
