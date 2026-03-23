"""Landscape state objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List

from .species import SpeciesParams


class DisturbanceType(IntEnum):
    NONE = 0
    FIRE = 1
    WINDTHROW = 2
    HARVEST = 3
    RIVER_SHIFT = 4
    FLOOD = 5
    PLANTING = 6
    INSECT_OUTBREAK = 7
    CUSTOM = 8


@dataclass
class Cohort:
    """A single species-age cohort within a cell."""

    species_id: int
    age: int
    biomass_kg_ha: float
    density_stems_ha: float
    canopy_height_m: float
    crown_cover_frac: float
    vigor: float
    leaf_area_index: float = 0.0


@dataclass
class CellVegetation:
    """Vegetation state for one grid cell."""

    cohorts: List[Cohort] = field(default_factory=list)
    time_since_disturbance: int = 0
    disturbance_type_last: int = DisturbanceType.NONE
    litter_kg_ha: float = 0.0
    coarse_woody_debris_kg_ha: float = 0.0
    mineral_soil_exposed_frac: float = 1.0
    recent_disturbance_severity: float = 0.0
    recent_fire_severity: float = 0.0
    regeneration_delay_yr: int = 0

    @property
    def total_canopy_cover(self) -> float:
        return min(1.0, sum(c.crown_cover_frac for c in self.cohorts))

    @property
    def dominant_height_m(self) -> float:
        return max((c.canopy_height_m for c in self.cohorts), default=0.0)

    @property
    def total_biomass_kg_ha(self) -> float:
        return sum(c.biomass_kg_ha for c in self.cohorts)

    @property
    def mean_age(self) -> float:
        if not self.cohorts:
            return 0.0
        return sum(c.age for c in self.cohorts) / len(self.cohorts)

    def add_or_merge_cohort(
        self,
        new_cohort: Cohort,
        age_window: int = 5,
        species: SpeciesParams | None = None,
    ) -> None:
        from .modules.structure import recompute_cohort_structure

        for cohort in self.cohorts:
            if cohort.species_id != new_cohort.species_id:
                continue
            if abs(cohort.age - new_cohort.age) > age_window:
                continue

            total_biomass = cohort.biomass_kg_ha + new_cohort.biomass_kg_ha
            if total_biomass <= 0.0:
                continue

            cohort.age = int(round((cohort.age * cohort.biomass_kg_ha + new_cohort.age * new_cohort.biomass_kg_ha) / total_biomass))
            cohort.density_stems_ha += new_cohort.density_stems_ha
            cohort.canopy_height_m = max(cohort.canopy_height_m, new_cohort.canopy_height_m)
            cohort.crown_cover_frac = min(0.98, cohort.crown_cover_frac + new_cohort.crown_cover_frac)
            cohort.vigor = min(1.0, (cohort.vigor * cohort.biomass_kg_ha + new_cohort.vigor * new_cohort.biomass_kg_ha) / total_biomass)
            cohort.biomass_kg_ha = total_biomass
            if species is not None:
                recompute_cohort_structure(cohort, species)
            return

        self.cohorts.append(new_cohort)

    def remove_empty_cohorts(self, min_biomass_kg_ha: float = 5.0, min_density_stems_ha: float = 1.0) -> None:
        self.cohorts = [
            cohort
            for cohort in self.cohorts
            if cohort.biomass_kg_ha >= min_biomass_kg_ha and cohort.density_stems_ha >= min_density_stems_ha
        ]
