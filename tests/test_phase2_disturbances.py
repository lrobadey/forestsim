import numpy as np
import pytest

from wattforest import ClimateLayers, DeterministicRNG, EventLog, EventType, LandscapeConfig, SimEvent, SoilLayers
from wattforest import SpeciesParams, TerrainLayers, WattForestEngine
from wattforest.modules.grazing import GrazingModule
from wattforest.modules.harvest import HarvestModule
from wattforest.modules.recruitment import RecruitmentModule
from wattforest.modules.structure import recompute_cohort_structure
from wattforest.species import default_species_table
from wattforest.state import CellVegetation, Cohort, DisturbanceType


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


def _empty_vegetation(shape: tuple[int, int], mineral_soil_exposed_frac: float = 1.0) -> np.ndarray:
    vegetation = np.empty(shape, dtype=object)
    for row in range(shape[0]):
        for col in range(shape[1]):
            vegetation[row, col] = CellVegetation(mineral_soil_exposed_frac=mineral_soil_exposed_frac)
    return vegetation


def _disturbance_summary(engine: WattForestEngine, mask: np.ndarray, max_age: int) -> dict[str, float]:
    total_biomass = 0.0
    mineral_soil = 0.0
    young_pioneer_biomass = 0.0
    mean_fire_severity = 0.0
    count = 0
    for row in range(engine.config.shape[0]):
        for col in range(engine.config.shape[1]):
            if not mask[row, col]:
                continue
            count += 1
            cell = engine.vegetation[row, col]
            total_biomass += cell.total_biomass_kg_ha
            mineral_soil += cell.mineral_soil_exposed_frac
            mean_fire_severity += cell.recent_fire_severity
            for cohort in cell.cohorts:
                species = engine.species[cohort.species_id]
                if species.pft.startswith("pioneer") and cohort.age <= max_age:
                    young_pioneer_biomass += cohort.biomass_kg_ha
    return {
        "total_biomass": total_biomass,
        "mineral_soil": mineral_soil,
        "young_pioneer_biomass": young_pioneer_biomass,
        "mean_fire_severity": mean_fire_severity / max(1, count),
    }


def test_windthrow_event_is_deterministic_and_keeps_structure_consistent():
    config = LandscapeConfig((200.0, 200.0), 20.0, (0.0, 0.0), 32610)
    affected_mask = np.ones(config.shape, dtype=bool)
    wind_event = SimEvent(
        event_id="wind-30",
        event_type=EventType.WINDSTORM,
        year=30,
        affected_cells=affected_mask,
        params={"wind_speed_ms": 42.0, "wind_dir_deg": 90.0},
    )

    engine_a = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[wind_event]))
    engine_b = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[wind_event]))
    engine_a.run(0, 30)
    engine_b.run(0, 30)

    assert any(record.area_blown_down_ha > 0.0 for record in engine_a.history if record.year == 30)
    assert np.allclose(engine_a.canopy_cover_grid(), engine_b.canopy_cover_grid())

    mature_cohorts_checked = 0
    for row in range(config.shape[0]):
        for col in range(config.shape[1]):
            cell = engine_a.vegetation[row, col]
            if cell.disturbance_type_last != DisturbanceType.WINDTHROW:
                continue
            for cohort in cell.cohorts:
                if cohort.age == 0:
                    continue
                mature_cohorts_checked += 1
                expected_height, expected_cover, expected_lai = _expected_structure(
                    engine_a.species[cohort.species_id],
                    cohort.biomass_kg_ha,
                    cohort.density_stems_ha,
                )
                assert np.isclose(cohort.canopy_height_m, expected_height)
                assert np.isclose(cohort.crown_cover_frac, expected_cover)
                assert np.isclose(cohort.leaf_area_index, expected_lai)

    assert mature_cohorts_checked >= 1


def test_harvest_module_supports_methods_threshold_and_slash():
    species = _test_species()
    removed_by_method: dict[str, float] = {}

    for method in ("selection", "shelterwood", "clearcut"):
        vegetation = np.empty((1, 1), dtype=object)
        vegetation[0, 0] = CellVegetation(
            cohorts=[
                Cohort(
                    species_id=species.species_id,
                    age=30,
                    biomass_kg_ha=9000.0,
                    density_stems_ha=450.0,
                    canopy_height_m=28.0,
                    crown_cover_frac=0.9,
                    vigor=0.85,
                    leaf_area_index=9.0,
                ),
                Cohort(
                    species_id=species.species_id,
                    age=6,
                    biomass_kg_ha=1500.0,
                    density_stems_ha=220.0,
                    canopy_height_m=4.0,
                    crown_cover_frac=0.2,
                    vigor=0.95,
                    leaf_area_index=1.5,
                ),
            ]
        )

        result = HarvestModule().apply_harvest(
            affected_mask=np.array([[True]]),
            method=method,
            retention_frac=0.1,
            species_filter=None,
            min_biomass_kg_ha=2000.0,
            vegetation_grid=vegetation,
            species_lookup={species.species_id: species},
        )

        treated_cell = vegetation[0, 0]
        dominant = treated_cell.cohorts[0]
        removed_by_method[method] = 9000.0 - dominant.biomass_kg_ha
        expected_height, expected_cover, expected_lai = _expected_structure(
            species,
            dominant.biomass_kg_ha,
            dominant.density_stems_ha,
        )

        assert result["total_removed_kg"] == pytest.approx(removed_by_method[method])
        assert 0.0 < dominant.biomass_kg_ha < 9000.0
        assert treated_cell.cohorts[1].biomass_kg_ha == pytest.approx(1500.0)
        assert treated_cell.litter_kg_ha > 0.0
        assert treated_cell.coarse_woody_debris_kg_ha > 0.0
        assert treated_cell.disturbance_type_last == DisturbanceType.HARVEST
        assert treated_cell.recent_disturbance_severity > 0.0
        assert np.isclose(dominant.canopy_height_m, expected_height)
        assert np.isclose(dominant.crown_cover_frac, expected_cover)
        assert np.isclose(dominant.leaf_area_index, expected_lai)

    assert removed_by_method["selection"] < removed_by_method["shelterwood"] < removed_by_method["clearcut"]

    with pytest.raises(ValueError):
        HarvestModule().apply_harvest(
            affected_mask=np.array([[True]]),
            method="thin",
            retention_frac=0.0,
            species_filter=None,
            min_biomass_kg_ha=0.0,
            vegetation_grid=np.array([[CellVegetation()]], dtype=object),
            species_lookup={species.species_id: species},
        )


def test_harvest_skips_cells_without_eligible_biomass():
    species = _test_species()
    vegetation = np.empty((1, 1), dtype=object)
    vegetation[0, 0] = CellVegetation(
        cohorts=[
            Cohort(
                species_id=species.species_id,
                age=12,
                biomass_kg_ha=1500.0,
                density_stems_ha=200.0,
                canopy_height_m=6.0,
                crown_cover_frac=0.25,
                vigor=0.9,
                leaf_area_index=2.0,
            )
        ],
        litter_kg_ha=3.0,
        coarse_woody_debris_kg_ha=4.0,
        mineral_soil_exposed_frac=0.2,
        recent_disturbance_severity=0.15,
        regeneration_delay_yr=7,
    )

    result = HarvestModule().apply_harvest(
        affected_mask=np.array([[True]]),
        method="selection",
        retention_frac=0.1,
        species_filter=None,
        min_biomass_kg_ha=2000.0,
        vegetation_grid=vegetation,
        species_lookup={species.species_id: species},
    )

    cell = vegetation[0, 0]
    cohort = cell.cohorts[0]

    assert result["total_removed_kg"] == pytest.approx(0.0)
    assert result["cells_treated"] == pytest.approx(0.0)
    assert cohort.biomass_kg_ha == pytest.approx(1500.0)
    assert cohort.density_stems_ha == pytest.approx(200.0)
    assert cell.litter_kg_ha == pytest.approx(3.0)
    assert cell.coarse_woody_debris_kg_ha == pytest.approx(4.0)
    assert cell.mineral_soil_exposed_frac == pytest.approx(0.2)
    assert cell.recent_disturbance_severity == pytest.approx(0.15)
    assert cell.regeneration_delay_yr == 7
    assert cell.disturbance_type_last == DisturbanceType.NONE
    assert cell.time_since_disturbance == 0


def test_grazing_suppresses_recruitment_and_recovery_restores_it():
    shape = (8, 8)
    species = _test_species()
    recruitment_module = RecruitmentModule()
    grazing_module = GrazingModule()
    mask = np.ones(shape, dtype=bool)
    vegetation = _empty_vegetation(shape)
    ground_light = np.full(shape, 0.95)
    seed_rain = np.full(shape, 50.0)
    terrain = TerrainLayers(*(np.zeros(shape) for _ in range(6)))
    soils = SoilLayers(np.zeros(shape), np.zeros(shape), np.zeros(shape, dtype=np.uint8), np.zeros(shape))
    climate = ClimateLayers(
        np.full(shape, 1600.0),
        np.full(shape, 850.0),
        np.zeros(shape),
        np.full(shape, 160, dtype=np.int16),
    )

    baseline = recruitment_module.establish_recruits(
        seed_rain=seed_rain,
        species=species,
        ground_light=ground_light,
        terrain=terrain,
        soil=soils,
        climate=climate,
        vegetation_grid=vegetation,
        rng=DeterministicRNG(11),
        year=3,
        establishment_scalar=np.ones(shape),
        moisture_bonus=np.zeros(shape),
    )

    grazing_module.activate(mask, 1.0)
    grazed = recruitment_module.establish_recruits(
        seed_rain=seed_rain,
        species=species,
        ground_light=ground_light,
        terrain=terrain,
        soil=soils,
        climate=climate,
        vegetation_grid=vegetation,
        rng=DeterministicRNG(11),
        year=3,
        establishment_scalar=np.full(shape, grazing_module.recruitment_modifier(0, 0)),
        moisture_bonus=np.zeros(shape),
    )

    grazing_module.deactivate(mask)
    recovered = recruitment_module.establish_recruits(
        seed_rain=seed_rain,
        species=species,
        ground_light=ground_light,
        terrain=terrain,
        soil=soils,
        climate=climate,
        vegetation_grid=vegetation,
        rng=DeterministicRNG(11),
        year=3,
        establishment_scalar=np.ones(shape),
        moisture_bonus=np.zeros(shape),
    )

    assert len(grazed) < len(baseline)
    assert len(recovered) == len(baseline)


def test_river_shift_scours_cells_and_persists_establishment_rewrite():
    config = LandscapeConfig((200.0, 200.0), 20.0, (0.0, 0.0), 32610)
    affected_mask = np.zeros(config.shape, dtype=bool)
    center_row = config.shape[0] // 2
    center_col = config.shape[1] // 2
    affected_mask[center_row - 1 : center_row + 2, center_col - 1 : center_col + 2] = True
    river_event = SimEvent(
        event_id="river-20",
        event_type=EventType.RIVER_SHIFT,
        year=20,
        affected_cells=affected_mask,
        params={"scour_frac": 0.55, "moisture_bonus": 0.3, "recruitment_scalar": 1.6},
    )

    immediate_river = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[river_event]))
    immediate_river.run(0, 20)
    immediate_baseline = WattForestEngine.from_synthetic(config, event_log=EventLog())
    immediate_baseline.run(0, 20)

    immediate_river_summary = _disturbance_summary(immediate_river, affected_mask, max_age=1)
    immediate_baseline_summary = _disturbance_summary(immediate_baseline, affected_mask, max_age=1)

    river_engine = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[river_event]))
    river_engine.run(0, 25)
    baseline_engine = WattForestEngine.from_synthetic(config, event_log=EventLog())
    baseline_engine.run(0, 25)

    river_summary = _disturbance_summary(river_engine, affected_mask, max_age=5)
    baseline_summary = _disturbance_summary(baseline_engine, affected_mask, max_age=5)

    assert np.allclose(river_engine._river_moisture_bonus[affected_mask], 0.3)
    assert np.allclose(river_engine._river_recruitment_scalar[affected_mask], 1.6)
    assert immediate_river_summary["total_biomass"] < immediate_baseline_summary["total_biomass"]
    assert immediate_river_summary["mineral_soil"] > immediate_baseline_summary["mineral_soil"]
    assert river_summary["young_pioneer_biomass"] >= baseline_summary["young_pioneer_biomass"]


def test_recent_harvest_changes_fire_behavior_via_slash_fuels():
    config = LandscapeConfig((200.0, 200.0), 20.0, (0.0, 0.0), 32610)
    affected_mask = np.zeros(config.shape, dtype=bool)
    center_row = config.shape[0] // 2
    center_col = config.shape[1] // 2
    affected_mask[center_row - 1 : center_row + 2, center_col - 1 : center_col + 2] = True

    harvest_event = SimEvent(
        event_id="harvest-18",
        event_type=EventType.HARVEST,
        year=18,
        affected_cells=affected_mask,
        params={"method": "clearcut", "retention_frac": 0.0, "min_biomass_kg_ha": 0.0},
    )
    fire_event = SimEvent(
        event_id="fire-19",
        event_type=EventType.FIRE_IGNITION,
        year=19,
        params={
            "ignition_cells": [(center_row, center_col)],
            "duration_hr": 5.0,
            "wind_speed_ms": 11.0,
            "wind_dir_deg": 90.0,
        },
    )

    harvest_only = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[harvest_event]))
    harvest_only.run(0, 18)
    mature_only = WattForestEngine.from_synthetic(config, event_log=EventLog())
    mature_only.run(0, 18)

    harvest_fuel = harvest_only._fuel_load_grid()[affected_mask]
    mature_fuel = mature_only._fuel_load_grid()[affected_mask]

    harvest_then_fire = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[harvest_event, fire_event]))
    harvest_then_fire.run(0, 19)
    fire_only = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[fire_event]))
    fire_only.run(0, 19)

    harvest_summary = _disturbance_summary(harvest_then_fire, affected_mask, max_age=1)
    mature_summary = _disturbance_summary(fire_only, affected_mask, max_age=1)
    harvest_year = next(record for record in harvest_then_fire.history if record.year == 19)
    mature_year = next(record for record in fire_only.history if record.year == 19)

    assert harvest_fuel.mean() > mature_fuel.mean()
    assert harvest_summary["mean_fire_severity"] >= mature_summary["mean_fire_severity"]
    assert harvest_year.area_burned_ha >= mature_year.area_burned_ha


def test_flood_event_reduces_biomass_and_persists_moisture_bonus():
    config = LandscapeConfig((80.0, 80.0), 20.0, (0.0, 0.0), 32610)
    affected_mask = np.zeros(config.shape, dtype=bool)
    affected_mask[:2, :2] = True
    flood_event = SimEvent(
        event_id="flood-4",
        event_type=EventType.FLOOD,
        year=4,
        affected_cells=affected_mask,
        params={"severity": 0.75, "mortality_frac": 0.5, "moisture_bonus": 0.4, "recruitment_scalar": 1.25},
    )

    flooded = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[flood_event]))
    flooded.run(0, 4)
    baseline = WattForestEngine.from_synthetic(config, event_log=EventLog())
    baseline.run(0, 4)

    flooded_biomass = sum(flooded.vegetation[row, col].total_biomass_kg_ha for row, col in zip(*np.where(affected_mask)))
    baseline_biomass = sum(baseline.vegetation[row, col].total_biomass_kg_ha for row, col in zip(*np.where(affected_mask)))

    assert flooded_biomass < baseline_biomass
    assert np.allclose(flooded._river_moisture_bonus[affected_mask], 0.4)
    assert all(flooded.vegetation[row, col].disturbance_type_last == DisturbanceType.FLOOD for row, col in zip(*np.where(affected_mask)))


def test_climate_shift_event_persists_for_subsequent_years():
    config = LandscapeConfig((80.0, 80.0), 20.0, (0.0, 0.0), 32610)
    affected_mask = np.ones(config.shape, dtype=bool)
    shift_event = SimEvent(
        event_id="climate-2",
        event_type=EventType.CLIMATE_SHIFT,
        year=2,
        affected_cells=affected_mask,
        params={"gdd_delta": 180.0, "precip_delta_mm": -60.0, "drought_delta": 0.12, "frost_free_delta": -8},
    )

    shifted = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[shift_event]))
    shifted.run(0, 3)
    baseline = WattForestEngine.from_synthetic(config, event_log=EventLog())
    baseline.run(0, 3)

    assert shifted.climate.growing_degree_days.mean() > baseline.climate.growing_degree_days.mean() + 150.0
    assert shifted.climate.annual_precip_mm.mean() < baseline.climate.annual_precip_mm.mean() - 50.0
    assert shifted.climate.drought_index.mean() > baseline.climate.drought_index.mean() + 0.1
    assert shifted.climate.frost_free_days.mean() < baseline.climate.frost_free_days.mean() - 6.0


def test_planting_event_adds_requested_species_to_empty_cells():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    affected_mask = np.ones(config.shape, dtype=bool)
    empty_vegetation = _empty_vegetation(config.shape, mineral_soil_exposed_frac=0.5)
    planting_event = SimEvent(
        event_id="plant-0",
        event_type=EventType.PLANTING,
        year=0,
        affected_cells=affected_mask,
        params={"species_id": 1, "density_stems_ha": 240.0, "biomass_kg_ha": 80.0, "age": 1},
    )

    engine = WattForestEngine.from_synthetic(
        config,
        event_log=EventLog(events=[planting_event]),
        initial_vegetation=empty_vegetation,
    )
    engine.run(0, 0)

    for row in range(config.shape[0]):
        for col in range(config.shape[1]):
            cell = engine.vegetation[row, col]
            assert cell.cohorts
            assert any(cohort.species_id == 1 for cohort in cell.cohorts)
            assert cell.disturbance_type_last == DisturbanceType.PLANTING


def test_insect_outbreak_targets_selected_species():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    species_table = default_species_table()[:2]
    vegetation = np.empty(config.shape, dtype=object)
    for row in range(config.shape[0]):
        for col in range(config.shape[1]):
            vegetation[row, col] = CellVegetation(
                cohorts=[
                    Cohort(
                        species_id=species_table[0].species_id,
                        age=40,
                        biomass_kg_ha=3200.0,
                        density_stems_ha=180.0,
                        canopy_height_m=0.0,
                        crown_cover_frac=0.0,
                        vigor=0.8,
                    ),
                    Cohort(
                        species_id=species_table[1].species_id,
                        age=40,
                        biomass_kg_ha=3200.0,
                        density_stems_ha=180.0,
                        canopy_height_m=0.0,
                        crown_cover_frac=0.0,
                        vigor=0.8,
                    ),
                ]
            )
            for cohort in vegetation[row, col].cohorts:
                recompute_cohort_structure(cohort, species_table[cohort.species_id])

    outbreak = SimEvent(
        event_id="insect-0",
        event_type=EventType.INSECT_OUTBREAK,
        year=0,
        affected_cells=np.ones(config.shape, dtype=bool),
        params={"severity": 0.7, "species_filter": [species_table[0].species_id], "min_age": 10},
    )

    engine = WattForestEngine.from_synthetic(
        config,
        species_table=species_table,
        initial_vegetation=vegetation,
        event_log=EventLog(events=[outbreak]),
    )
    engine.run(0, 0)

    for row in range(config.shape[0]):
        for col in range(config.shape[1]):
            cohorts = {cohort.species_id: cohort for cohort in engine.vegetation[row, col].cohorts}
            assert cohorts[species_table[0].species_id].biomass_kg_ha < cohorts[species_table[1].species_id].biomass_kg_ha
            assert engine.vegetation[row, col].disturbance_type_last == DisturbanceType.INSECT_OUTBREAK
