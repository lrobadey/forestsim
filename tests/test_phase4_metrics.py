import numpy as np
import pytest

from wattforest import CalibrationGlobals, LandscapeConfig, Phase4PatternSnapshot, WattForestEngine
from wattforest.modules.structure import recompute_cohort_structure
from wattforest.state import CellVegetation, Cohort
from wattforest.validation import summarize_phase4_engine


def _cohort(species, age: int, biomass_kg_ha: float, density_stems_ha: float) -> Cohort:
    cohort = Cohort(
        species_id=species.species_id,
        age=age,
        biomass_kg_ha=biomass_kg_ha,
        density_stems_ha=density_stems_ha,
        canopy_height_m=0.0,
        crown_cover_frac=0.0,
        vigor=0.8,
    )
    recompute_cohort_structure(cohort, species)
    return cohort


def test_summarize_phase4_engine_returns_expected_metrics():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    engine = WattForestEngine.from_synthetic(config, calibration_globals=CalibrationGlobals())
    species = {entry.species_id: entry for entry in engine.species_table}

    engine.vegetation[0, 0] = CellVegetation(
        cohorts=[
            _cohort(species[0], age=15, biomass_kg_ha=6000.0, density_stems_ha=220.0),
            _cohort(species[1], age=45, biomass_kg_ha=3000.0, density_stems_ha=80.0),
        ]
    )
    engine.vegetation[0, 1] = CellVegetation(
        cohorts=[_cohort(species[1], age=65, biomass_kg_ha=8000.0, density_stems_ha=150.0)]
    )
    engine.vegetation[1, 0] = CellVegetation(
        cohorts=[_cohort(species[2], age=95, biomass_kg_ha=5000.0, density_stems_ha=90.0)]
    )
    engine.vegetation[1, 1] = CellVegetation()

    summary = summarize_phase4_engine(engine, age_bins=[0, 20, 40, 80, 120, 999])

    assert isinstance(summary, Phase4PatternSnapshot)
    assert summary.total_biomass_kg_ha == pytest.approx(22000.0)
    assert 0.0 < summary.gap_fraction < 1.0
    assert summary.mean_gap_size_ha >= 0.0
    assert summary.gap_size_p50_ha >= 0.0
    assert summary.gap_size_p90_ha >= summary.gap_size_p50_ha
    assert summary.dominant_pft_patch_p50_cells >= 1.0
    assert summary.dominant_pft_patch_p90_cells >= summary.dominant_pft_patch_p50_cells
    assert summary.species_richness >= 3.0
    assert len(summary.biomass_trajectory_shape) >= 1
    assert set(summary.pft_biomass_fraction) >= {"pioneer_conifer", "shade_tolerant_hardwood", "shade_intolerant_hardwood"}
    assert sum(summary.pft_biomass_fraction.values()) == pytest.approx(1.0)
    assert len(summary.age_distribution) == 5
    assert sum(summary.age_distribution) == pytest.approx(1.0)
    assert summary.age_distribution[0] > 0.0
    assert summary.age_distribution[3] > 0.0
