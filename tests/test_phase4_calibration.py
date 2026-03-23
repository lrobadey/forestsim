import json
from pathlib import Path

import numpy as np
import pytest

from wattforest import CalibrationGlobals, LandscapeConfig, WattForestEngine, default_species_table
from wattforest.calibration import load_calibration_spec, run_phase4_calibration, write_phase4_outputs
from wattforest.modules.structure import recompute_cohort_structure
from wattforest.state import CellVegetation, Cohort
from wattforest.tuning import apply_parameter_overrides, sample_parameter_value
from wattforest.validation import summarize_phase4_engine


def _cohort(species, age: int, biomass_kg_ha: float, density_stems_ha: float) -> Cohort:
    cohort = Cohort(
        species_id=species.species_id,
        age=age,
        biomass_kg_ha=biomass_kg_ha,
        density_stems_ha=density_stems_ha,
        canopy_height_m=0.0,
        crown_cover_frac=0.0,
        vigor=0.85,
    )
    recompute_cohort_structure(cohort, species)
    return cohort


def _base_species_table():
    return [species for species in default_species_table()[:3]]


def _synthetic_engine_builder(manifest_path, species_table=None, calibration_globals=None):
    _ = manifest_path
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    species_table = list(species_table or _base_species_table())
    calibration_globals = calibration_globals or CalibrationGlobals()
    vegetation = np.empty(config.shape, dtype=object)
    for row in range(config.shape[0]):
        for col in range(config.shape[1]):
            vegetation[row, col] = CellVegetation()

    species = {entry.species_id: entry for entry in species_table}
    vegetation[0, 0] = CellVegetation(
        cohorts=[
            _cohort(species[0], age=18, biomass_kg_ha=6200.0, density_stems_ha=210.0),
            _cohort(species[1], age=52, biomass_kg_ha=2800.0, density_stems_ha=95.0),
        ]
    )
    vegetation[0, 1] = CellVegetation(
        cohorts=[_cohort(species[1], age=64, biomass_kg_ha=7900.0, density_stems_ha=145.0)]
    )
    vegetation[1, 0] = CellVegetation(
        cohorts=[_cohort(species[2], age=96, biomass_kg_ha=4800.0, density_stems_ha=105.0)]
    )
    vegetation[1, 1] = CellVegetation(
        cohorts=[_cohort(species[0], age=8, biomass_kg_ha=1800.0, density_stems_ha=320.0)]
    )
    return WattForestEngine.from_synthetic(
        config,
        species_table=species_table,
        initial_vegetation=vegetation,
        calibration_globals=calibration_globals,
    )


def _manifest_payload(spec_path: str, *, calibration_end_year: int | None = 1, validation_end_year: int | None = 4):
    payload = {
        "site_id": "phase4_fixture",
        "epsg": 32618,
        "origin_utm": [500000.0, 4500000.0],
        "extent_m": [40.0, 40.0],
        "cell_size_m": 20.0,
        "start_year": 0,
        "dem_path": "dem.tif",
        "ssurgo_path": "ssurgo.gpkg",
        "climate": {
            "gdd_path": "climate/gdd.tif",
            "precip_path": "climate/precip.tif",
            "drought_path": "climate/drought.tif",
            "frost_free_path": "climate/frost_free.tif",
        },
        "fia": {
            "plots_path": "fia/plots.csv",
            "trees_path": "fia/trees.csv",
            "conditions_path": "fia/conditions.csv",
            "crosswalk_path": "../../species/fia_species_to_pft.csv",
        },
        "mtbs_path": "mtbs.gpkg",
        "validation": {"baseline_end_year": validation_end_year},
        "calibration": {"spec_path": spec_path},
    }
    if calibration_end_year is not None:
        payload["calibration"]["end_year"] = calibration_end_year
    return payload


def _write_manifest_and_spec(tmp_path: Path, *, impossible_targets: bool = False) -> tuple[Path, Path]:
    target_parameters = {
        "species.pioneer_conifer.g_max_cm_yr": 1.1,
        "species.shade_tolerant_hardwood.background_mortality_yr": 0.011,
        "globals.recruitment_base_scalar": 1.05,
    }
    base_species = _base_species_table()
    target_species, target_globals = apply_parameter_overrides(base_species, CalibrationGlobals(), target_parameters)
    target_engine = _synthetic_engine_builder("fixture.json", species_table=target_species, calibration_globals=target_globals)
    target_engine.run(0, 1)
    # TODO: These targets are simulator-generated fixtures for regression
    # testing, not observed ecological targets. Keep using them for harness
    # tests, but add a separate test path once Phase 4 is calibrated against
    # externally justified site metrics.
    target_snapshot = summarize_phase4_engine(target_engine)

    observed_biomass = target_snapshot.total_biomass_kg_ha * (8.0 if impossible_targets else 1.0)
    spec_payload = {
        "parameter_space": {
            "species.pioneer_conifer.g_max_cm_yr": {"min": 1.1, "max": 1.1, "scale": "linear"},
            "species.shade_tolerant_hardwood.background_mortality_yr": {"min": 0.011, "max": 0.011, "scale": "linear"},
            "globals.recruitment_base_scalar": {"min": 1.05, "max": 1.05, "scale": "linear"},
        },
        "metric_targets": [
            {
                "metric": "total_biomass_kg_ha",
                "family": "biomass",
                "observed": observed_biomass,
                "tolerance": 1e-9,
                "weight": 1.0,
            },
            {
                "metric": "gap_fraction",
                "family": "gap",
                "observed": target_snapshot.gap_fraction,
                "tolerance": 1e-9,
                "weight": 1.0,
            },
            {
                "metric": "morans_i_height",
                "family": "spatial",
                "observed": target_snapshot.morans_i_height,
                "tolerance": 1e-9,
                "weight": 1.0,
            },
            {
                "metric": "pft_biomass_fraction",
                "family": "composition",
                "observed": target_snapshot.pft_biomass_fraction,
                "tolerance": 1e-9,
                "weight": 1.0,
            },
            {
                "metric": "age_distribution",
                "family": "age",
                "observed": target_snapshot.age_distribution,
                "tolerance": 1e-9,
                "weight": 1.0,
            },
        ],
        "gap_threshold": 0.3,
        "age_bins": [0, 20, 40, 80, 120, 999],
        "min_pattern_families": 5 if impossible_targets else 3,
    }
    spec_path = tmp_path / "calibration_spec.json"
    manifest_path = tmp_path / "site_manifest.json"
    spec_path.write_text(json.dumps(spec_payload))
    manifest_path.write_text(json.dumps(_manifest_payload(spec_path.name)))
    return manifest_path, spec_path


def test_phase4_spec_validates_parameter_paths(tmp_path: Path):
    _, spec_path = _write_manifest_and_spec(tmp_path)
    spec = load_calibration_spec(spec_path, _base_species_table())

    assert spec.parameter_names == [
        "globals.recruitment_base_scalar",
        "species.pioneer_conifer.g_max_cm_yr",
        "species.shade_tolerant_hardwood.background_mortality_yr",
    ]

    invalid_spec = tmp_path / "invalid_spec.json"
    invalid_spec.write_text(
        json.dumps(
            {
                "parameter_space": {"species.unknown_pft.g_max_cm_yr": {"min": 0.5, "max": 1.5, "scale": "linear"}},
                "metric_targets": [],
            }
        )
    )
    with pytest.raises(ValueError):
        load_calibration_spec(invalid_spec, _base_species_table())


def test_sample_parameter_value_stays_within_linear_and_log_bounds():
    rng = np.random.default_rng(17)
    linear = [sample_parameter_value(rng, 1.0, 2.0, "linear") for _ in range(20)]
    log_values = [sample_parameter_value(rng, 1e-3, 1e-1, "log") for _ in range(20)]

    assert all(1.0 <= value <= 2.0 for value in linear)
    assert all(1e-3 <= value <= 1e-1 for value in log_values)


def test_phase4_end_year_prefers_calibration_block(tmp_path: Path):
    manifest_path, spec_path = _write_manifest_and_spec(tmp_path)
    payload = json.loads(manifest_path.read_text())
    payload["calibration"]["end_year"] = 2
    payload["validation"]["baseline_end_year"] = 7
    manifest_path.write_text(json.dumps(payload))

    result = run_phase4_calibration(manifest_path, n_samples=1, seed=4, sobol_base_n=4, engine_builder=_synthetic_engine_builder)

    assert result.calibration_spec_path == spec_path.resolve()
    assert result.end_year == 2


def test_phase4_calibration_recovers_known_target_and_is_repeatable(tmp_path: Path):
    manifest_path, _ = _write_manifest_and_spec(tmp_path)

    result_a = run_phase4_calibration(
        manifest_path,
        n_samples=3,
        seed=11,
        sobol_base_n=4,
        engine_builder=_synthetic_engine_builder,
    )
    result_b = run_phase4_calibration(
        manifest_path,
        n_samples=3,
        seed=11,
        sobol_base_n=4,
        engine_builder=_synthetic_engine_builder,
    )

    assert len(result_a.accepted_runs) == 3
    assert result_a.best_run.total_distance == pytest.approx(0.0)
    assert result_a.best_run.parameters == result_b.best_run.parameters
    assert result_a.best_run.total_distance == pytest.approx(result_b.best_run.total_distance)
    assert len(result_a.oat_sensitivity) == 2 * len(result_a.calibration_spec.parameter_names)
    assert {row["parameter"] for row in result_a.sobol_indices} == set(result_a.calibration_spec.parameter_names)
    assert result_a.neutral_baseline.total_distance > result_a.best_run.total_distance


def test_phase4_no_accepted_run_still_emits_outputs(tmp_path: Path):
    manifest_path, _ = _write_manifest_and_spec(tmp_path, impossible_targets=True)
    result = run_phase4_calibration(
        manifest_path,
        n_samples=2,
        seed=3,
        sobol_base_n=4,
        engine_builder=_synthetic_engine_builder,
    )

    assert result.accepted_runs == []
    assert result.best_run.total_distance > 0.0
    assert len(result.oat_sensitivity) == 2 * len(result.calibration_spec.parameter_names)
    output_dir = tmp_path / "outputs"
    write_phase4_outputs(output_dir, result)
    assert (output_dir / "best_run.json").exists()
    assert (output_dir / "neutral_baseline.json").exists()
    assert (output_dir / "oat_sensitivity.csv").exists()
    assert (output_dir / "sobol_indices.csv").exists()


def test_phase4_rejects_sample_when_any_single_metric_fails(tmp_path: Path):
    manifest_path, spec_path = _write_manifest_and_spec(tmp_path)
    payload = json.loads(spec_path.read_text())
    payload["metric_targets"][0]["tolerance"] = 1e-9
    payload["metric_targets"][1]["observed"] += 0.05
    spec_path.write_text(json.dumps(payload))

    result = run_phase4_calibration(
        manifest_path,
        n_samples=1,
        seed=2,
        sobol_base_n=4,
        engine_builder=_synthetic_engine_builder,
    )

    assert result.accepted_runs == []
    assert result.sampled_runs[0].metric_passes["gap_fraction"] is False
    assert result.sampled_runs[0].accepted is False
