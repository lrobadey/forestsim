import json
from pathlib import Path

from wattforest import CalibrationSpec, Phase4CalibrationRun, Phase4PatternSnapshot
from wattforest.calibration import CalibrationSampleRecord, MetricTarget, ParameterRange
from wattforest.phase4 import main


def _dummy_sample(sample_index: int, *, accepted: bool) -> CalibrationSampleRecord:
    return CalibrationSampleRecord(
        sample_index=sample_index,
        parameters={"globals.recruitment_base_scalar": 1.05},
        simulated=Phase4PatternSnapshot(
            total_biomass_kg_ha=25000.0,
            mean_canopy_height_m=18.0,
            gap_fraction=0.2,
            gap_size_p50_ha=0.04,
            gap_size_p90_ha=0.12,
            dominant_pft_patch_p50_cells=1.0,
            dominant_pft_patch_p90_cells=2.0,
            morans_i_height=0.3,
            pft_biomass_fraction={"pioneer_conifer": 0.7, "shade_tolerant_hardwood": 0.3},
            age_distribution=[0.2, 0.2, 0.2, 0.2, 0.2],
        ),
        metric_errors={"total_biomass_kg_ha": 0.0},
        metric_passes={"total_biomass_kg_ha": accepted},
        family_passes={"biomass": accepted, "gap": accepted, "spatial": accepted},
        total_distance=0.0 if accepted else 1.0,
        accepted=accepted,
    )


def _dummy_result(tmp_path: Path) -> Phase4CalibrationRun:
    sample = _dummy_sample(0, accepted=True)
    return Phase4CalibrationRun(
        site_id="cli_phase4",
        manifest_path=tmp_path / "site_manifest.json",
        calibration_spec_path=tmp_path / "calibration_spec.json",
        start_year=0,
        end_year=2,
        calibration_spec=CalibrationSpec(
            parameter_space={"globals.recruitment_base_scalar": ParameterRange(1.0, 1.1, "linear")},
            metric_targets=[MetricTarget("total_biomass_kg_ha", "biomass", 25000.0, 0.1, 1.0)],
        ),
        sampled_runs=[sample],
        accepted_runs=[sample],
        best_run=sample,
        neutral_baseline=_dummy_sample(-1, accepted=False),
        oat_sensitivity=[{"parameter": "globals.recruitment_base_scalar", "quantile": 0.25, "value": 1.025, "total_distance": 0.1, "accepted": True, "passing_family_count": 3}],
        sobol_indices=[{"parameter": "globals.recruitment_base_scalar", "first_order": 0.4, "total_order": 0.6}],
    )


def test_phase4_cli_prints_payload_and_writes_outputs(tmp_path: Path, monkeypatch, capsys):
    result = _dummy_result(tmp_path)
    calls: list[tuple[str, str | None, int | None, int, int, int]] = []

    def _fake_run(manifest_path, calibration_spec_path=None, end_year=None, n_samples=250, seed=0, sobol_base_n=128):
        calls.append((manifest_path, calibration_spec_path, end_year, n_samples, seed, sobol_base_n))
        return result

    monkeypatch.setattr("wattforest.phase4.LandscapeInitializer.run_phase4_calibration", _fake_run)

    output_dir = tmp_path / "outputs"
    exit_code = main(
        [
            str(tmp_path / "site_manifest.json"),
            "--calibration-spec",
            str(tmp_path / "calibration_spec.json"),
            "--end-year",
            "2",
            "--n-samples",
            "4",
            "--seed",
            "9",
            "--sobol-base-n",
            "8",
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls == [
        (
            str(tmp_path / "site_manifest.json"),
            str(tmp_path / "calibration_spec.json"),
            2,
            4,
            9,
            8,
        )
    ]
    assert captured["site_id"] == "cli_phase4"
    assert captured["n_sampled_runs"] == 1
    assert captured["output_dir"] == str(output_dir.resolve())
    assert (output_dir / "calibration_spec_resolved.json").exists()
    assert (output_dir / "runs.csv").exists()
    assert (output_dir / "accepted_runs.csv").exists()
    assert (output_dir / "best_run.json").exists()
    assert (output_dir / "neutral_baseline.json").exists()
    assert (output_dir / "oat_sensitivity.csv").exists()
    assert (output_dir / "sobol_indices.csv").exists()
    assert (output_dir / "run_metadata.json").exists()
