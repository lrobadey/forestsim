import json
from pathlib import Path

import numpy as np
import pytest

from wattforest import LandscapeConfig, LandscapeInitializer, Phase3BaselineRun, SitePatternSummary, WattForestEngine
from wattforest.modules.structure import recompute_cohort_structure
from wattforest.state import CellVegetation, Cohort
from wattforest.validation import compare_site_patterns, summarize_engine

try:
    import geopandas as gpd
    import rasterio
    import pysheds  # noqa: F401
    from rasterio.transform import from_origin
    from shapely.geometry import box
except ModuleNotFoundError:
    gpd = None
    rasterio = None
    from_origin = None
    box = None

HAS_PHASE3_GEOSPATIAL = all(value is not None for value in (gpd, rasterio, from_origin, box))


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


def test_summarize_engine_returns_phase3_pattern_metrics():
    config = LandscapeConfig((40.0, 40.0), 20.0, (0.0, 0.0), 32610)
    engine = WattForestEngine.from_synthetic(config)
    species = {entry.species_id: entry for entry in engine.species_table}

    engine.vegetation[0, 0] = CellVegetation(cohorts=[_cohort(species[0], age=35, biomass_kg_ha=6000.0, density_stems_ha=220.0)])
    engine.vegetation[0, 1] = CellVegetation(cohorts=[_cohort(species[1], age=60, biomass_kg_ha=9000.0, density_stems_ha=160.0)])
    engine.vegetation[1, 0] = CellVegetation()
    engine.vegetation[1, 1] = CellVegetation(cohorts=[_cohort(species[3], age=12, biomass_kg_ha=3000.0, density_stems_ha=340.0)])

    summary = summarize_engine(engine)

    assert summary.total_biomass_kg == pytest.approx((6000.0 + 9000.0 + 3000.0) * 0.04)
    assert summary.total_biomass_kg_ha == pytest.approx(18000.0)
    assert 0.0 < summary.gap_fraction < 1.0
    assert summary.mean_canopy_height_m > 0.0
    assert set(summary.pft_biomass_kg) == {species_entry.pft for species_entry in engine.species_table}
    assert summary.pft_biomass_fraction["shade_tolerant_hardwood"] > summary.pft_biomass_fraction["pioneer_hardwood"]
    assert sum(summary.pft_biomass_fraction.values()) == pytest.approx(1.0)


def test_compare_site_patterns_reports_aggregate_phase3_score():
    observed = SitePatternSummary(
        total_biomass_kg=1000.0,
        total_biomass_kg_ha=25000.0,
        gap_fraction=0.20,
        mean_canopy_height_m=18.0,
        morans_i_height=0.30,
        pft_biomass_kg={"pioneer_conifer": 700.0, "shade_tolerant_hardwood": 300.0},
        pft_biomass_fraction={"pioneer_conifer": 0.70, "shade_tolerant_hardwood": 0.30},
    )
    simulated = SitePatternSummary(
        total_biomass_kg=1100.0,
        total_biomass_kg_ha=24000.0,
        gap_fraction=0.26,
        mean_canopy_height_m=16.2,
        morans_i_height=0.36,
        pft_biomass_kg={"pioneer_conifer": 660.0, "shade_tolerant_hardwood": 440.0},
        pft_biomass_fraction={"pioneer_conifer": 0.60, "shade_tolerant_hardwood": 0.40},
    )

    comparison = compare_site_patterns(observed, simulated)

    assert comparison["total_biomass_kg_rel_error"] == pytest.approx(0.10)
    assert comparison["gap_fraction_abs_error"] == pytest.approx(0.06)
    assert comparison["pft_fraction_abs_error::pioneer_conifer"] == pytest.approx(0.10)
    assert comparison["mean_pft_fraction_abs_error"] == pytest.approx(0.10)
    assert comparison["phase3_validation_score"] > 0.0


def test_manifest_validation_targets_resolve_relative_paths(tmp_path: Path):
    targets_path = tmp_path / "site_targets.json"
    targets_path.write_text(
        json.dumps(
            {
                "total_biomass_kg": 1000.0,
                "total_biomass_kg_ha": 25000.0,
                "gap_fraction": 0.2,
                "mean_canopy_height_m": 18.0,
                "morans_i_height": 0.3,
                "pft_biomass_kg": {"pioneer_conifer": 700.0, "shade_tolerant_hardwood": 300.0},
                "pft_biomass_fraction": {"pioneer_conifer": 0.7, "shade_tolerant_hardwood": 0.3},
            }
        )
    )
    manifest = {
        "site_id": "synthetic_demo_fixture",
        "epsg": 32618,
        "origin_utm": [500000.0, 4500000.0],
        "extent_m": [40.0, 40.0],
        "cell_size_m": 20.0,
        "start_year": 2015,
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
        "validation": {"targets_path": "site_targets.json"},
    }
    manifest_path = tmp_path / "site_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    summary = LandscapeInitializer.validation_targets_from_manifest(manifest_path)

    assert summary is not None
    assert summary.total_biomass_kg == pytest.approx(1000.0)
    assert summary.pft_biomass_fraction["shade_tolerant_hardwood"] == pytest.approx(0.3)


def _write_raster(path: Path, array: np.ndarray, transform, epsg: int) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=array.dtype,
        transform=transform,
        crs=f"EPSG:{epsg}",
        nodata=None,
    ) as dataset:
        dataset.write(array, 1)


def _phase3_config() -> LandscapeConfig:
    return LandscapeConfig(extent_m=(40.0, 40.0), cell_size_m=10.0, origin_utm=(500000.0, 4100000.0), epsg=32618)


def _write_climate_stack(base_dir: Path, config: LandscapeConfig) -> dict[str, Path]:
    climate_dir = base_dir / "climate"
    climate_dir.mkdir()
    transform = from_origin(config.origin_utm[0], config.origin_utm[1] + config.extent_m[1], config.cell_size_m, config.cell_size_m)
    base = np.flipud(np.arange(config.n_cells, dtype=np.float32).reshape(config.shape))
    paths = {
        "gdd_path": climate_dir / "gdd.tif",
        "precip_path": climate_dir / "precip.tif",
        "drought_path": climate_dir / "drought.tif",
        "frost_free_path": climate_dir / "frost.tif",
    }
    _write_raster(paths["gdd_path"], 1200.0 + base, transform, config.epsg)
    _write_raster(paths["precip_path"], 800.0 + 2.0 * base, transform, config.epsg)
    _write_raster(paths["drought_path"], np.clip(0.15 + base / 100.0, 0.0, 1.0).astype(np.float32), transform, config.epsg)
    _write_raster(paths["frost_free_path"], (150.0 + base).astype(np.float32), transform, config.epsg)
    return paths


def _write_fia_tables(base_dir: Path, config: LandscapeConfig) -> dict[str, Path]:
    import pandas as pd

    fia_dir = base_dir / "fia"
    fia_dir.mkdir()
    plots = pd.DataFrame(
        [
            {"plot_id": "A", "x": config.origin_utm[0] + 8.0, "y": config.origin_utm[1] + 10.0},
            {"plot_id": "B", "x": config.origin_utm[0] + 32.0, "y": config.origin_utm[1] + 30.0},
        ]
    )
    trees = pd.DataFrame(
        [
            {"plot_id": "A", "condid": 1, "spcd": 12, "age": 18, "tpa_unadj": 55.0, "dia": 18.0},
            {"plot_id": "A", "condid": 1, "spcd": 241, "age": 42, "tpa_unadj": 24.0, "dia": 30.0},
            {"plot_id": "B", "condid": 1, "spcd": 951, "age": 16, "tpa_unadj": 70.0, "dia": 16.0},
            {"plot_id": "B", "condid": 1, "spcd": 621, "age": 55, "tpa_unadj": 18.0, "dia": 12.0},
        ]
    )
    conditions = pd.DataFrame(
        [
            {"plot_id": "A", "condid": 1, "condprop_unadj": 1.0, "stdage": 35},
            {"plot_id": "B", "condid": 1, "condprop_unadj": 1.0, "stdage": 30},
        ]
    )
    plots_path = fia_dir / "plots.csv"
    trees_path = fia_dir / "trees.csv"
    conditions_path = fia_dir / "conditions.csv"
    crosswalk_path = fia_dir / "crosswalk.csv"
    plots.to_csv(plots_path, index=False)
    trees.to_csv(trees_path, index=False)
    conditions.to_csv(conditions_path, index=False)
    crosswalk_path.write_text(
        "spcd,pft\n12,pioneer_conifer\n241,shade_tolerant_hardwood\n951,pioneer_hardwood\n621,subcanopy_specialist\n"
    )
    return {
        "plots_path": plots_path,
        "trees_path": trees_path,
        "conditions_path": conditions_path,
        "crosswalk_path": crosswalk_path,
    }


def _write_ssurgo(base_dir: Path, config: LandscapeConfig) -> Path:
    ssurgo_path = base_dir / "ssurgo.gpkg"
    midpoint = config.origin_utm[0] + config.extent_m[0] / 2.0
    west_poly = box(config.origin_utm[0], config.origin_utm[1], midpoint, config.origin_utm[1] + config.extent_m[1])
    east_poly = box(midpoint, config.origin_utm[1], config.origin_utm[0] + config.extent_m[0], config.origin_utm[1] + config.extent_m[1])
    gdf = gpd.GeoDataFrame(
        [
            {"awc": 110.0, "depth_to_restriction": 140.0, "texture_class": "loam", "rock_fraction": 0.12, "geometry": west_poly},
            {"awc": 75.0, "depth_to_restriction": 45.0, "texture_class": "sand", "rock_fraction": 0.35, "geometry": east_poly},
        ],
        crs=f"EPSG:{config.epsg}",
    )
    gdf.to_file(ssurgo_path, driver="GPKG")
    return ssurgo_path


def _write_mtbs(base_dir: Path, config: LandscapeConfig) -> Path:
    mtbs_path = base_dir / "mtbs.gpkg"
    older = box(config.origin_utm[0], config.origin_utm[1], config.origin_utm[0] + 15.0, config.origin_utm[1] + 15.0)
    newer = box(config.origin_utm[0] + 20.0, config.origin_utm[1] + 20.0, config.origin_utm[0] + 40.0, config.origin_utm[1] + 40.0)
    gdf = gpd.GeoDataFrame(
        [
            {"fire_year": 2010, "ig_date": "2010-07-20", "severity": 0.55, "geometry": older},
            {"fire_year": 2018, "ig_date": "2018-08-11", "severity": 0.80, "geometry": newer},
        ],
        crs=f"EPSG:{config.epsg}",
    )
    gdf.to_file(mtbs_path, driver="GPKG")
    return mtbs_path


def _write_manifest(
    tmp_path: Path,
    config: LandscapeConfig,
    *,
    include_targets: bool,
    baseline_end_year: int | None,
) -> Path:
    dem_path = tmp_path / "dem.tif"
    transform = from_origin(config.origin_utm[0], config.origin_utm[1] + config.extent_m[1], config.cell_size_m, config.cell_size_m)
    dem = np.flipud(
        np.array(
            [
                [100.0, 101.0, 102.0, 103.0],
                [101.0, 102.0, 103.0, 104.0],
                [102.0, 103.0, 104.0, 105.0],
                [103.0, 104.0, 105.0, 106.0],
            ],
            dtype=np.float32,
        )
    )
    _write_raster(dem_path, dem, transform, config.epsg)
    climate_paths = _write_climate_stack(tmp_path, config)
    fia_paths = _write_fia_tables(tmp_path, config)
    ssurgo_path = _write_ssurgo(tmp_path, config)
    mtbs_path = _write_mtbs(tmp_path, config)

    validation: dict[str, object] | None = None
    if include_targets or baseline_end_year is not None:
        validation = {}
        if baseline_end_year is not None:
            validation["baseline_end_year"] = baseline_end_year
        if include_targets:
            targets_path = tmp_path / "site_targets.json"
            targets_path.write_text(
                json.dumps(
                    {
                        "total_biomass_kg": 1000.0,
                        "total_biomass_kg_ha": 25000.0,
                        "gap_fraction": 0.2,
                        "mean_canopy_height_m": 18.0,
                        "morans_i_height": 0.3,
                        "pft_biomass_kg": {"pioneer_conifer": 700.0, "shade_tolerant_hardwood": 300.0},
                        "pft_biomass_fraction": {"pioneer_conifer": 0.7, "shade_tolerant_hardwood": 0.3},
                    }
                )
            )
            validation["targets_path"] = targets_path.name

    manifest = {
        "site_id": "tiny_phase3",
        "epsg": config.epsg,
        "origin_utm": list(config.origin_utm),
        "extent_m": list(config.extent_m),
        "cell_size_m": config.cell_size_m,
        "start_year": 2015,
        "dem_path": dem_path.name,
        "ssurgo_path": ssurgo_path.name,
        "climate": {key: path.relative_to(tmp_path).as_posix() for key, path in climate_paths.items()},
        "fia": {
            "plots_path": fia_paths["plots_path"].relative_to(tmp_path).as_posix(),
            "trees_path": fia_paths["trees_path"].relative_to(tmp_path).as_posix(),
            "conditions_path": fia_paths["conditions_path"].relative_to(tmp_path).as_posix(),
            "crosswalk_path": fia_paths["crosswalk_path"].relative_to(tmp_path).as_posix(),
        },
        "mtbs_path": mtbs_path.name,
    }
    if validation is not None:
        manifest["validation"] = validation

    manifest_path = tmp_path / "site_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


@pytest.mark.skipif(not HAS_PHASE3_GEOSPATIAL, reason="Phase 3 geospatial dependencies are not installed")
def test_run_phase3_baseline_executes_manifest_workflow_and_comparison(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _phase3_config(), include_targets=True, baseline_end_year=2017)

    result = LandscapeInitializer.run_phase3_baseline(manifest_path)

    assert isinstance(result, Phase3BaselineRun)
    assert result.site_id == "tiny_phase3"
    assert result.start_year == 2015
    assert result.end_year == 2017
    assert result.observed is not None
    assert result.comparison is not None
    assert result.engine.history[-1].year == 2017
    assert result.simulated.total_biomass_kg > 0.0
    assert "phase3_validation_score" in result.comparison


@pytest.mark.skipif(not HAS_PHASE3_GEOSPATIAL, reason="Phase 3 geospatial dependencies are not installed")
def test_run_phase3_baseline_accepts_explicit_end_year_without_targets(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _phase3_config(), include_targets=False, baseline_end_year=None)

    result = LandscapeInitializer.run_phase3_baseline(manifest_path, end_year=2016)

    assert result.end_year == 2016
    assert result.observed is None
    assert result.comparison is None
    assert result.engine.history[-1].year == 2016


@pytest.mark.skipif(not HAS_PHASE3_GEOSPATIAL, reason="Phase 3 geospatial dependencies are not installed")
def test_run_phase3_baseline_requires_end_year_if_manifest_omits_it(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _phase3_config(), include_targets=False, baseline_end_year=None)

    with pytest.raises(ValueError, match="requires end_year or validation.baseline_end_year"):
        LandscapeInitializer.run_phase3_baseline(manifest_path)
