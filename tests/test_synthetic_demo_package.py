from pathlib import Path
import json

import pytest


DEMO_DIR = Path(__file__).resolve().parents[1] / "data/sites/synthetic_demo"


def test_synthetic_demo_package_structure():
    manifest = json.loads((DEMO_DIR / "site_manifest.json").read_text())
    targets = json.loads((DEMO_DIR / "site_targets.json").read_text())

    assert manifest["site_id"] == "synthetic_demo"
    assert manifest["validation"]["targets_path"] == "site_targets.json"
    assert set(manifest["climate"]["baseline"]) == {"gdd_path", "precip_path", "drought_path", "frost_free_path"}
    assert set(manifest["climate"]["yearly_overrides"]) == {"2021", "2024"}
    assert set(manifest["landfire"]) == {"evt", "bps", "fuel_model"}

    assert set(targets) == {
        "total_biomass_kg",
        "total_biomass_kg_ha",
        "gap_fraction",
        "mean_canopy_height_m",
        "morans_i_height",
        "pft_biomass_kg",
        "pft_biomass_fraction",
    }

    phase3_files = {
        "comparison.json",
        "observed_summary.json",
        "run_metadata.json",
        "simulated_summary.json",
    }
    phase4_files = {
        "accepted_runs.csv",
        "best_run.json",
        "calibration_spec_resolved.json",
        "neutral_baseline.json",
        "oat_sensitivity.csv",
        "run_metadata.json",
        "runs.csv",
        "sobol_indices.csv",
    }

    assert phase3_files <= {path.name for path in (DEMO_DIR / "expected/phase3").iterdir()}
    assert phase4_files <= {path.name for path in (DEMO_DIR / "expected/phase4").iterdir()}


def test_synthetic_demo_manifest_is_initializer_friendly():
    pytest.importorskip("rasterio")
    pytest.importorskip("geopandas")

    from wattforest import LandscapeInitializer

    engine = LandscapeInitializer.from_site_manifest(DEMO_DIR / "site_manifest.json")

    assert engine.config.cell_size_m == 20.0
    assert hasattr(engine, "climate_baseline")
    assert getattr(engine, "climate_yearly_overrides", None)
    assert getattr(engine, "landfire_layers", None) is not None
