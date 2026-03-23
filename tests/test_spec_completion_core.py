from __future__ import annotations

import numpy as np
import pytest

from wattforest import LandscapeConfig, PatternOrientedCalibration, WattForestEngine
from wattforest.climate import ClimateLayers
from wattforest.events import EventLog, EventType, SimEvent


def test_engine_climate_updates_with_yearly_overrides():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    engine = WattForestEngine.from_synthetic(config)
    baseline = engine.climate.copy()
    override = ClimateLayers(
        growing_degree_days=np.full(config.shape, 999.0, dtype=np.float32),
        annual_precip_mm=np.full(config.shape, 111.0, dtype=np.float32),
        drought_index=np.full(config.shape, 0.9, dtype=np.float32),
        frost_free_days=np.full(config.shape, 80, dtype=np.int16),
    )
    engine.set_climate_scenario(baseline, {2: override})

    engine._update_climate(1)
    assert np.allclose(engine.climate.growing_degree_days, baseline.growing_degree_days)

    engine._update_climate(2)
    assert np.allclose(engine.climate.growing_degree_days, override.growing_degree_days)
    assert np.all(engine.climate.frost_free_days == 80)


def test_polygon_event_rasterization_is_deterministic_through_replay():
    config = LandscapeConfig((100.0, 100.0), 20.0, (0.0, 0.0), 32610)
    event = SimEvent(
        event_id="harvest-poly",
        event_type=EventType.HARVEST,
        year=3,
        polygon_vertices=[(10.0, 10.0), (70.0, 10.0), (70.0, 70.0), (10.0, 70.0)],
        params={"method": "clearcut", "retention_frac": 0.0},
    )
    engine = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[event]))
    engine.run(0, 5)
    first = engine.canopy_cover_grid().copy()

    replay = WattForestEngine.from_synthetic(config, event_log=EventLog(events=[event]))
    replay.run(0, 5)
    second = replay.canopy_cover_grid().copy()

    assert np.allclose(first, second)


def test_custom_event_can_delegate_to_supported_behavior():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    engine = WattForestEngine.from_synthetic(
        config,
        event_log=EventLog(
            events=[
                SimEvent(
                    event_id="custom-harvest",
                    event_type=EventType.CUSTOM,
                    year=0,
                    affected_cells=np.ones(config.shape, dtype=bool),
                    params={"delegate_event_type": "harvest", "method": "clearcut", "retention_frac": 0.0},
                )
            ]
        ),
    )

    engine.run(0, 0)

    assert any(record.area_harvested_ha > 0.0 for record in engine.history)


def test_invalid_custom_delegate_is_rejected():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    engine = WattForestEngine.from_synthetic(
        config,
        event_log=EventLog(
            events=[
                SimEvent(
                    event_id="custom-invalid",
                    event_type=EventType.CUSTOM,
                    year=0,
                    affected_cells=np.ones(config.shape, dtype=bool),
                    params={"delegate_event_type": "custom"},
                )
            ]
        ),
    )

    with pytest.raises(ValueError):
        engine.run(0, 0)


def test_pattern_oriented_calibration_accepts_only_all_metrics_within_tolerance():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)

    def engine_factory(params: dict[str, float]) -> WattForestEngine:
        engine = WattForestEngine.from_synthetic(config)
        original_run = engine.run

        def patched_run(start_year: int, end_year: int) -> None:
            original_run(start_year, end_year)
            for record in engine.history:
                record.fraction_in_gaps = params["gap_fraction"]
                record.n_species_present = int(params["species_richness"])
                record.total_biomass_kg = params["biomass"]

        engine.run = patched_run  # type: ignore[method-assign]
        return engine

    calibration = PatternOrientedCalibration(
        engine_factory=engine_factory,
        target_patterns={
            "mean_gap_fraction": {"value": 0.2},
            "species_richness": {"value": 99.0},
            "biomass_trajectory_shape": {"value": [1.0, 1.0, 1.0]},
        },
        param_ranges={
            "gap_fraction": {"min": 0.2, "max": 0.2},
            "species_richness": {"min": 2.0, "max": 2.0},
            "biomass": {"min": 1.0, "max": 1.0},
        },
    )

    accepted = calibration.run_abc(n_samples=1, tolerance=0.0)

    assert accepted.empty
