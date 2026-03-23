"""Mortality module scaffold."""

from __future__ import annotations

from ..species import SpeciesParams
from ..state import CellVegetation, Cohort
from .structure import recompute_cohort_structure


class MortalityModule:
    def compute_mortality_probability(
        self,
        cohort: Cohort,
        species: SpeciesParams,
        stress_scalar: float = 1.0,
    ) -> float:
        age_ratio = cohort.age / species.age_max_yr if species.age_max_yr else 0.0
        background = species.background_mortality_yr * (1.0 + 2.0 * age_ratio**3)
        stress = 0.0
        if cohort.vigor < species.stress_mortality_threshold:
            stress_severity = 1.0 - (cohort.vigor / species.stress_mortality_threshold)
            stress = species.stress_mortality_rate * stress_scalar * stress_severity
        survival = (1.0 - background) * (1.0 - stress)
        return 1.0 - survival

    def apply_cohort_mortality(
        self,
        cell: CellVegetation,
        cohort_idx: int,
        mortality_frac: float,
        species: SpeciesParams,
    ) -> float:
        cohort = cell.cohorts[cohort_idx]
        killed_biomass = cohort.biomass_kg_ha * mortality_frac
        cohort.biomass_kg_ha = max(0.0, cohort.biomass_kg_ha - killed_biomass)
        cohort.density_stems_ha = max(0.0, cohort.density_stems_ha * (1.0 - mortality_frac))
        recompute_cohort_structure(cohort, species)
        cell.litter_kg_ha += killed_biomass * 0.3
        cell.coarse_woody_debris_kg_ha += killed_biomass * 0.7
        return killed_biomass
