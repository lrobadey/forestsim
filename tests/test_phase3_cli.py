import json
from pathlib import Path

from wattforest import LandscapeConfig, Phase3BaselineRun, SitePatternSummary, WattForestEngine
from wattforest.phase3 import main


def _dummy_result(tmp_path: Path) -> Phase3BaselineRun:
    engine = WattForestEngine.from_synthetic(LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610))
    observed = SitePatternSummary(
        total_biomass_kg=1000.0,
        total_biomass_kg_ha=25000.0,
        gap_fraction=0.2,
        mean_canopy_height_m=18.0,
        morans_i_height=0.3,
        pft_biomass_kg={"pioneer_conifer": 700.0, "shade_tolerant_hardwood": 300.0},
        pft_biomass_fraction={"pioneer_conifer": 0.7, "shade_tolerant_hardwood": 0.3},
    )
    simulated = SitePatternSummary(
        total_biomass_kg=1100.0,
        total_biomass_kg_ha=24000.0,
        gap_fraction=0.26,
        mean_canopy_height_m=16.2,
        morans_i_height=0.36,
        pft_biomass_kg={"pioneer_conifer": 660.0, "shade_tolerant_hardwood": 440.0},
        pft_biomass_fraction={"pioneer_conifer": 0.6, "shade_tolerant_hardwood": 0.4},
    )
    return Phase3BaselineRun(
        manifest_path=tmp_path / "site_manifest.json",
        site_id="cli_phase3",
        start_year=2015,
        end_year=2017,
        engine=engine,
        simulated=simulated,
        observed=observed,
        comparison={"phase3_validation_score": 0.12},
    )


def test_phase3_cli_prints_payload_and_writes_outputs(tmp_path: Path, monkeypatch, capsys):
    result = _dummy_result(tmp_path)

    monkeypatch.setattr(
        "wattforest.phase3.LandscapeInitializer.run_phase3_baseline",
        lambda manifest_path, end_year=None: result,
    )

    output_dir = tmp_path / "outputs"
    exit_code = main([str(tmp_path / "site_manifest.json"), "--end-year", "2017", "--output-dir", str(output_dir)])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["site_id"] == "cli_phase3"
    assert captured["end_year"] == 2017
    assert captured["output_dir"] == str(output_dir.resolve())
    assert (output_dir / "simulated_summary.json").exists()
    assert (output_dir / "observed_summary.json").exists()
    assert (output_dir / "comparison.json").exists()
    assert (output_dir / "run_metadata.json").exists()


def test_phase3_cli_allows_manifest_defined_end_year(tmp_path: Path, monkeypatch, capsys):
    result = _dummy_result(tmp_path)
    calls: list[tuple[str, int | None]] = []

    def _fake_run(manifest_path, end_year=None):
        calls.append((manifest_path, end_year))
        return result

    monkeypatch.setattr("wattforest.phase3.LandscapeInitializer.run_phase3_baseline", _fake_run)

    exit_code = main([str(tmp_path / "site_manifest.json")])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls == [(str(tmp_path / "site_manifest.json"), None)]
    assert captured["start_year"] == 2015
