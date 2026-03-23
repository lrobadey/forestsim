import numpy as np

from wattforest import EventLog, EventType, LandscapeConfig, SimEvent, WattForestEngine
from wattforest.modules.harvest import HarvestModule
from wattforest.modules.mortality import MortalityModule
from wattforest.species import SpeciesParams
from wattforest.state import CellVegetation, Cohort


def _test_species() -> SpeciesParams:
    return SpeciesParams(
        species_id=0,
        name="test",
        pft="pioneer",
        d_max_cm=80.0,
        h_max_m=35.0,
        age_max_yr=200,
        g_max_cm_yr=0.5,
        specific_leaf_area=10.0,
        wood_density_kg_m3=500.0,
        shade_tolerance=2.0,
        light_compensation_frac=0.1,
        light_saturation_frac=0.8,
        gdd_min=500.0,
        gdd_max=3000.0,
        drought_tolerance=0.5,
        frost_tolerance=100.0,
        background_mortality_yr=0.01,
        stress_mortality_threshold=0.3,
        stress_mortality_rate=0.2,
        maturity_age_yr=15,
        fecundity_seeds_yr=1000.0,
        seed_mass_g=0.5,
        dispersal_mean_m=50.0,
        dispersal_fat_tail_p=2.0,
        leaf_litter_bulk_density=20.0,
        flammability=0.5,
    )


def _expected_structure(species: SpeciesParams, biomass: float, density: float) -> tuple[float, float, float]:
    canopy_height = species.h_max_m * (1.0 - np.exp(-0.00011 * biomass))
    cover_from_biomass = 1.0 - np.exp(-biomass / 11000.0)
    cover_from_density = 1.0 - np.exp(-density / 280.0)
    crown_cover = np.clip(0.78 * cover_from_biomass + 0.22 * cover_from_density, 0.0, 0.95)
    leaf_area_index = biomass * species.specific_leaf_area * crown_cover / 10000.0
    return float(canopy_height), float(crown_cover), float(leaf_area_index)


def test_mortality_recomputes_structure_after_biomass_loss():
    species = _test_species()
    cell = CellVegetation(
        cohorts=[
            Cohort(
                species_id=species.species_id,
                age=25,
                biomass_kg_ha=10000.0,
                density_stems_ha=500.0,
                canopy_height_m=30.0,
                crown_cover_frac=0.95,
                vigor=0.9,
                leaf_area_index=12.0,
            )
        ]
    )

    killed = MortalityModule().apply_cohort_mortality(cell, 0, 0.5, species)
    cohort = cell.cohorts[0]
    expected_height, expected_cover, expected_lai = _expected_structure(species, 5000.0, 250.0)

    assert killed == 5000.0
    assert cohort.biomass_kg_ha == 5000.0
    assert cohort.density_stems_ha == 250.0
    assert cohort.canopy_height_m < 30.0
    assert cohort.crown_cover_frac < 0.95
    assert np.isclose(cohort.canopy_height_m, expected_height)
    assert np.isclose(cohort.crown_cover_frac, expected_cover)
    assert np.isclose(cohort.leaf_area_index, expected_lai)


def test_fire_keeps_surviving_burned_cohorts_structurally_consistent():
    config = LandscapeConfig((200.0, 200.0), 20.0, (0.0, 0.0), 32610)
    fire_event = SimEvent(
        event_id="fire-20",
        event_type=EventType.FIRE_IGNITION,
        year=20,
        params={
            "ignition_cells": [(config.shape[0] // 2, config.shape[1] // 2)],
            "duration_hr": 6.0,
            "wind_speed_ms": 12.0,
            "wind_dir_deg": 90.0,
        },
    )
    engine = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[fire_event]))
    engine.run(0, 20)

    surviving_burned = 0
    for row in range(engine.config.shape[0]):
        for col in range(engine.config.shape[1]):
            cell = engine.vegetation[row, col]
            if cell.recent_fire_severity <= 0.02:
                continue
            for cohort in cell.cohorts:
                if cohort.age == 0:
                    continue
                expected_height, expected_cover, expected_lai = _expected_structure(
                    engine.species[cohort.species_id],
                    cohort.biomass_kg_ha,
                    cohort.density_stems_ha,
                )
                assert np.isclose(cohort.canopy_height_m, expected_height)
                assert np.isclose(cohort.crown_cover_frac, expected_cover)
                assert np.isclose(cohort.leaf_area_index, expected_lai)
                surviving_burned += 1

    assert surviving_burned >= 1


def test_harvest_recomputes_structure_after_removal():
    species = _test_species()
    vegetation = np.empty((1, 1), dtype=object)
    vegetation[0, 0] = CellVegetation(
        cohorts=[
            Cohort(
                species_id=species.species_id,
                age=30,
                biomass_kg_ha=8000.0,
                density_stems_ha=400.0,
                canopy_height_m=28.0,
                crown_cover_frac=0.9,
                vigor=0.85,
                leaf_area_index=9.0,
            )
        ]
    )

    result = HarvestModule().apply_harvest(
        affected_mask=np.array([[True]]),
        method="clearcut",
        retention_frac=0.5,
        species_filter=None,
        min_biomass_kg_ha=0.0,
        vegetation_grid=vegetation,
        species_lookup={species.species_id: species},
    )
    cohort = vegetation[0, 0].cohorts[0]
    expected_height, expected_cover, expected_lai = _expected_structure(species, 4000.0, 200.0)

    assert result["total_removed_kg"] == 4000.0
    assert cohort.biomass_kg_ha == 4000.0
    assert cohort.density_stems_ha == 200.0
    assert cohort.canopy_height_m < 28.0
    assert cohort.crown_cover_frac < 0.9
    assert np.isclose(cohort.canopy_height_m, expected_height)
    assert np.isclose(cohort.crown_cover_frac, expected_cover)
    assert np.isclose(cohort.leaf_area_index, expected_lai)
