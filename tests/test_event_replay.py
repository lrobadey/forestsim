import numpy as np

from wattforest.climate import ClimateLayers
from wattforest.config import LandscapeConfig
from wattforest.engine import WattForestEngine
from wattforest.events import EventLog, EventType, SimEvent
from wattforest.soils import SoilLayers
from wattforest.terrain import TerrainLayers


def _burned_mask(engine: WattForestEngine) -> np.ndarray:
    mask = np.zeros(engine.config.shape, dtype=bool)
    for row in range(engine.config.shape[0]):
        for col in range(engine.config.shape[1]):
            cell = engine.vegetation[row, col]
            mask[row, col] = cell.recent_fire_severity > 0.02
    return mask


def _burned_cell_summary(engine: WattForestEngine, mask: np.ndarray, max_age: int) -> dict[str, float]:
    total_biomass = 0.0
    mineral_soil = 0.0
    pioneer_young_biomass = 0.0
    for row in range(engine.config.shape[0]):
        for col in range(engine.config.shape[1]):
            if not mask[row, col]:
                continue
            cell = engine.vegetation[row, col]
            total_biomass += cell.total_biomass_kg_ha
            mineral_soil += cell.mineral_soil_exposed_frac
            for cohort in cell.cohorts:
                species = engine.species[cohort.species_id]
                if species.pft.startswith("pioneer") and cohort.age <= max_age:
                    pioneer_young_biomass += cohort.biomass_kg_ha
    return {
        "total_biomass": total_biomass,
        "mineral_soil": mineral_soil,
        "pioneer_young_biomass": pioneer_young_biomass,
    }


def test_engine_replay_runs_from_initial_state_without_checkpoint():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    shape = config.shape
    engine = WattForestEngine(
        config=config,
        species_table=[],
        terrain=TerrainLayers(*(np.zeros(shape) for _ in range(6))),
        soils=SoilLayers(np.zeros(shape), np.zeros(shape), np.zeros(shape, dtype=np.uint8), np.zeros(shape)),
        climate=ClimateLayers(np.zeros(shape), np.zeros(shape), np.zeros(shape), np.zeros(shape, dtype=np.int16)),
        event_log=EventLog(),
    )
    engine.run(0, 1)
    engine.replay_from(0, 1)
    assert engine.history


def test_replay_after_fire_edit_is_deterministic_and_changes_trajectory():
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

    engine = WattForestEngine.from_synthetic(config, event_log=EventLog())
    engine.run(0, 40)
    baseline_biomass = np.array([record.total_biomass_kg for record in engine.history], dtype=float)

    engine.event_log.events.append(fire_event)
    engine.replay_from(20, 40)
    edited_biomass = np.array([record.total_biomass_kg for record in engine.history], dtype=float)

    assert np.any(np.abs(edited_biomass - baseline_biomass) > 1e-6)
    assert any(record.area_burned_ha > 0.0 for record in engine.history if record.year == 20)

    replay_engine = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[fire_event]))
    replay_engine.run(0, 40)
    replay_biomass = np.array([record.total_biomass_kg for record in replay_engine.history], dtype=float)

    assert np.allclose(edited_biomass, replay_biomass)


def test_fire_event_changes_post_fire_state_in_burned_cells():
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

    fire_engine = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[fire_event]))
    fire_engine.run(0, 20)
    burned_mask = _burned_mask(fire_engine)

    assert np.count_nonzero(burned_mask) >= 8

    fire_engine.run(21, 26)
    baseline_engine = WattForestEngine.from_synthetic(config, event_log=EventLog())
    baseline_engine.run(0, 26)

    fire_summary = _burned_cell_summary(fire_engine, burned_mask, max_age=6)
    baseline_summary = _burned_cell_summary(baseline_engine, burned_mask, max_age=6)

    assert fire_summary["total_biomass"] < baseline_summary["total_biomass"]
    assert fire_summary["mineral_soil"] >= baseline_summary["mineral_soil"]
    assert fire_summary["pioneer_young_biomass"] > baseline_summary["pioneer_young_biomass"]


def test_durable_checkpoint_restore_resumes_deterministically(tmp_path):
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

    uninterrupted = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[fire_event]))
    uninterrupted.run(0, 40)

    engine = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[fire_event]))
    engine.run(0, 24)
    checkpoint_path = tmp_path / "engine-checkpoint.pkl"
    engine.save_checkpoint(checkpoint_path)

    restored = WattForestEngine.load_checkpoint(checkpoint_path)
    restored.run(25, 40)

    uninterrupted_biomass = np.array([record.total_biomass_kg for record in uninterrupted.history], dtype=float)
    restored_biomass = np.array([record.total_biomass_kg for record in restored.history], dtype=float)

    assert checkpoint_path.exists()
    assert np.allclose(restored_biomass, uninterrupted_biomass)
    assert np.allclose(restored.canopy_cover_grid(), uninterrupted.canopy_cover_grid())


def test_replay_from_checkpoint_year_reruns_that_year_event():
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

    engine = WattForestEngine.from_synthetic(config, event_log=EventLog())
    engine.checkpoint_interval = 10
    engine.run(0, 30)
    baseline_biomass = np.array([record.total_biomass_kg for record in engine.history], dtype=float)

    engine.event_log.events.append(fire_event)
    engine.replay_from(20, 30)
    replay_biomass = np.array([record.total_biomass_kg for record in engine.history], dtype=float)

    fresh = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[fire_event]))
    fresh.checkpoint_interval = 10
    fresh.run(0, 30)
    fresh_biomass = np.array([record.total_biomass_kg for record in fresh.history], dtype=float)

    assert np.any(np.abs(replay_biomass - baseline_biomass) > 1e-6)
    assert any(record.area_burned_ha > 0.0 for record in engine.history if record.year == 20)
    assert np.allclose(replay_biomass, fresh_biomass)


def test_durable_checkpoint_replay_reruns_checkpoint_year_event(tmp_path):
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

    engine = WattForestEngine.from_synthetic(config, event_log=EventLog())
    engine.checkpoint_interval = 10
    engine.run(0, 30)
    checkpoint_path = tmp_path / "checkpoint-year.pkl"
    engine.save_checkpoint(checkpoint_path)

    restored = WattForestEngine.load_checkpoint(checkpoint_path)
    restored.event_log.events.append(fire_event)
    restored.replay_from(20, 30)

    fresh = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[fire_event]))
    fresh.checkpoint_interval = 10
    fresh.run(0, 30)

    restored_biomass = np.array([record.total_biomass_kg for record in restored.history], dtype=float)
    fresh_biomass = np.array([record.total_biomass_kg for record in fresh.history], dtype=float)

    assert checkpoint_path.exists()
    assert any(record.area_burned_ha > 0.0 for record in restored.history if record.year == 20)
    assert np.allclose(restored_biomass, fresh_biomass)
    assert np.allclose(restored.canopy_cover_grid(), fresh.canopy_cover_grid())
