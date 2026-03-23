"""Harvest module scaffold."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from ..species import SpeciesParams
from ..state import DisturbanceType
from .structure import recompute_cohort_structure


class HarvestModule:
    def apply_harvest(
        self,
        affected_mask: np.ndarray,
        method: str,
        retention_frac: float,
        species_filter: Optional[List[int]],
        min_biomass_kg_ha: float,
        vegetation_grid: np.ndarray,
        species_lookup: Dict[int, SpeciesParams],
    ) -> Dict[str, float]:
        if method not in {"clearcut", "selection", "shelterwood"}:
            raise ValueError(f"Unsupported harvest method: {method}")
        total_removed = 0.0
        cells_treated = 0
        for row in range(affected_mask.shape[0]):
            for col in range(affected_mask.shape[1]):
                if not affected_mask[row, col]:
                    continue
                cell = vegetation_grid[row, col]
                if method == "clearcut":
                    removal_frac = 1.0 - retention_frac
                elif method == "selection":
                    removal_frac = 0.3
                elif method == "shelterwood":
                    removal_frac = 0.6
                cell_removed = 0.0
                for cohort in cell.cohorts:
                    if species_filter and cohort.species_id not in species_filter:
                        continue
                    if cohort.biomass_kg_ha < min_biomass_kg_ha:
                        continue
                    removed = cohort.biomass_kg_ha * removal_frac
                    if removed <= 0.0:
                        continue
                    cohort.biomass_kg_ha = max(0.0, cohort.biomass_kg_ha - removed)
                    cohort.density_stems_ha = max(0.0, cohort.density_stems_ha * (1.0 - removal_frac))
                    recompute_cohort_structure(cohort, species_lookup[cohort.species_id])
                    total_removed += removed
                    cell_removed += removed
                    cell.litter_kg_ha += removed * 0.2
                    cell.coarse_woody_debris_kg_ha += removed * 0.35
                    cell.mineral_soil_exposed_frac = min(1.0, cell.mineral_soil_exposed_frac + removal_frac * 0.3)
                if cell_removed > 0.0:
                    cells_treated += 1
                    cell.remove_empty_cohorts()
                    cell.time_since_disturbance = 0
                    cell.disturbance_type_last = DisturbanceType.HARVEST
                    cell.recent_disturbance_severity = max(cell.recent_disturbance_severity, 0.25 + 0.55 * removal_frac)
                    cell.regeneration_delay_yr = max(cell.regeneration_delay_yr, 2 + int(round(3.0 * removal_frac)))
        return {"total_removed_kg": total_removed, "cells_treated": float(cells_treated)}
