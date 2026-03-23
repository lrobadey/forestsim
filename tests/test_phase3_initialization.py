from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

gpd = pytest.importorskip("geopandas")
rasterio = pytest.importorskip("rasterio")
pytest.importorskip("pysheds")
from rasterio.transform import from_origin
from shapely.geometry import box

from wattforest import LandscapeConfig, LandscapeInitializer, default_species_table
from wattforest.io.fia import FiaPaths, load_fia_plots
from wattforest.io.geospatial import read_raster_to_grid
from wattforest.io.mtbs import load_mtbs_events
from wattforest.state import DisturbanceType


@pytest.fixture
def phase3_config() -> LandscapeConfig:
    return LandscapeConfig(extent_m=(40.0, 40.0), cell_size_m=10.0, origin_utm=(500000.0, 4100000.0), epsg=32618)


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


def _write_landfire_stack(base_dir: Path, config: LandscapeConfig) -> dict[str, Path]:
    landfire_dir = base_dir / "landfire"
    landfire_dir.mkdir()
    transform = from_origin(config.origin_utm[0], config.origin_utm[1] + config.extent_m[1], config.cell_size_m, config.cell_size_m)
    evt = np.flipud(np.array([[1, 0, 0, 1], [0, 1, 1, 0], [0, 0, 1, 0], [1, 0, 0, 1]], dtype=np.uint8))
    disturbance = np.flipud(np.full(config.shape, 0.3, dtype=np.float32))
    fuel_model = np.flipud(np.full(config.shape, 2.0, dtype=np.float32))
    paths = {
        "evt": landfire_dir / "evt.tif",
        "disturbance": landfire_dir / "disturbance.tif",
        "fuel_model": landfire_dir / "fuel_model.tif",
    }
    _write_raster(paths["evt"], evt, transform, config.epsg)
    _write_raster(paths["disturbance"], disturbance, transform, config.epsg)
    _write_raster(paths["fuel_model"], fuel_model, transform, config.epsg)
    return paths


def _write_fia_tables(base_dir: Path, config: LandscapeConfig, *, include_extra_species: bool = False) -> tuple[dict[str, Path], Path]:
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
    if include_extra_species:
        trees.loc[len(trees)] = {"plot_id": "B", "condid": 1, "spcd": 9999, "age": 28, "tpa_unadj": 12.0, "dia": 14.0}
    conditions = pd.DataFrame(
        [
            {"plot_id": "A", "condid": 1, "condprop_unadj": 1.0, "stdage": 35},
            {"plot_id": "B", "condid": 1, "condprop_unadj": 1.0, "stdage": 30},
        ]
    )
    plots_path = fia_dir / "plots.csv"
    trees_path = fia_dir / "trees.csv"
    conditions_path = fia_dir / "conditions.csv"
    plots.to_csv(plots_path, index=False)
    trees.to_csv(trees_path, index=False)
    conditions.to_csv(conditions_path, index=False)

    crosswalk_path = fia_dir / "crosswalk.csv"
    crosswalk_path.write_text(
        "spcd,pft\n12,pioneer_conifer\n241,shade_tolerant_hardwood\n951,pioneer_hardwood\n621,subcanopy_specialist\n"
    )
    return {
        "plots_path": plots_path,
        "trees_path": trees_path,
        "conditions_path": conditions_path,
        "crosswalk_path": crosswalk_path,
    }, crosswalk_path


def _write_ssurgo(base_dir: Path, config: LandscapeConfig, *, include_rock_fraction: bool = True) -> Path:
    ssurgo_path = base_dir / "ssurgo.gpkg"
    midpoint = config.origin_utm[0] + config.extent_m[0] / 2.0
    west_poly = box(config.origin_utm[0], config.origin_utm[1], midpoint, config.origin_utm[1] + config.extent_m[1])
    east_poly = box(midpoint, config.origin_utm[1], config.origin_utm[0] + config.extent_m[0], config.origin_utm[1] + config.extent_m[1])
    records = [
        {"awc": 110.0, "depth_to_restriction": 140.0, "texture_class": "loam", "geometry": west_poly},
        {"awc": 75.0, "depth_to_restriction": 45.0, "texture_class": "sand", "geometry": east_poly},
    ]
    if include_rock_fraction:
        records[0]["rock_fraction"] = 0.12
        records[1]["rock_fraction"] = 0.35
    gdf = gpd.GeoDataFrame(records, crs=f"EPSG:{config.epsg}")
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


def test_raster_reprojection_uses_bilinear_for_continuous_and_nearest_for_categorical(tmp_path: Path, phase3_config: LandscapeConfig):
    coarse = np.array([[0, 100], [0, 100]], dtype=np.float32)
    coarse_transform = from_origin(
        phase3_config.origin_utm[0],
        phase3_config.origin_utm[1] + phase3_config.extent_m[1],
        phase3_config.extent_m[0] / 2.0,
        phase3_config.extent_m[1] / 2.0,
    )
    raster_path = tmp_path / "coarse.tif"
    _write_raster(raster_path, coarse, coarse_transform, phase3_config.epsg)

    continuous = read_raster_to_grid(raster_path, phase3_config, categorical=False, dtype=np.float32, fail_on_nodata=True)
    categorical = read_raster_to_grid(raster_path, phase3_config, categorical=True, dtype=np.uint8, fail_on_nodata=True)

    assert continuous.shape == phase3_config.shape
    assert categorical.shape == phase3_config.shape
    assert len(np.unique(np.round(continuous, 3))) > 2
    assert set(np.unique(categorical).tolist()) <= {0, 100}


def test_dem_soils_and_climate_loaders_align_to_engine_grid(tmp_path: Path, phase3_config: LandscapeConfig):
    dem_path = tmp_path / "dem.tif"
    transform = from_origin(phase3_config.origin_utm[0], phase3_config.origin_utm[1] + phase3_config.extent_m[1], phase3_config.cell_size_m, phase3_config.cell_size_m)
    dem = np.flipud(np.array([[100.0, 101.0, 102.0, 103.0], [101.0, 102.0, 103.0, 104.0], [102.0, 103.0, 104.0, 105.0], [103.0, 104.0, 105.0, 106.0]], dtype=np.float32))
    _write_raster(dem_path, dem, transform, phase3_config.epsg)

    terrain = LandscapeInitializer.terrain_from_dem(dem_path, phase3_config)
    soils = LandscapeInitializer.soils_from_ssurgo(_write_ssurgo(tmp_path, phase3_config, include_rock_fraction=False), phase3_config)
    climate = LandscapeInitializer.climate_from_rasters(_write_climate_stack(tmp_path, phase3_config), phase3_config)

    assert terrain.elevation.shape == phase3_config.shape
    assert terrain.slope.dtype == np.float32
    assert np.all(terrain.flow_accumulation >= 0.0)
    assert soils.texture_class.dtype == np.uint8
    assert np.all(soils.rock_fraction > 0.0)
    assert climate.frost_free_days.dtype == np.int16
    assert climate.growing_degree_days.shape == phase3_config.shape


def test_climate_manifest_supports_yearly_overrides_and_landfire_ingestion(tmp_path: Path, phase3_config: LandscapeConfig):
    climate_paths = _write_climate_stack(tmp_path, phase3_config)
    override_dir = tmp_path / "climate_overrides"
    override_dir.mkdir()
    transform = from_origin(phase3_config.origin_utm[0], phase3_config.origin_utm[1] + phase3_config.extent_m[1], phase3_config.cell_size_m, phase3_config.cell_size_m)
    override_gdd = np.flipud(np.full(phase3_config.shape, 999.0, dtype=np.float32))
    override_precip = np.flipud(np.full(phase3_config.shape, 444.0, dtype=np.float32))
    override_drought = np.flipud(np.full(phase3_config.shape, 0.8, dtype=np.float32))
    override_frost = np.flipud(np.full(phase3_config.shape, 120.0, dtype=np.float32))
    _write_raster(override_dir / "gdd.tif", override_gdd, transform, phase3_config.epsg)
    _write_raster(override_dir / "precip.tif", override_precip, transform, phase3_config.epsg)
    _write_raster(override_dir / "drought.tif", override_drought, transform, phase3_config.epsg)
    _write_raster(override_dir / "frost.tif", override_frost, transform, phase3_config.epsg)
    climate_bundle = LandscapeInitializer.climate_from_manifest(
        {
            "baseline": {key: path for key, path in climate_paths.items()},
            "yearly_overrides": {
                2020: {
                    "gdd_path": override_dir / "gdd.tif",
                    "precip_path": override_dir / "precip.tif",
                    "drought_path": override_dir / "drought.tif",
                    "frost_free_path": override_dir / "frost.tif",
                }
            },
        },
        phase3_config,
    )
    landfire_layers = LandscapeInitializer.landfire_from_manifest(_write_landfire_stack(tmp_path, phase3_config), phase3_config)

    assert 2020 in climate_bundle.yearly_overrides
    assert np.allclose(climate_bundle.yearly_overrides[2020].growing_degree_days, 999.0)
    assert landfire_layers is not None
    assert set(landfire_layers) == {"evt", "disturbance", "fuel_model"}


def test_fia_ingestion_is_deterministic_and_combines_nearby_plots(tmp_path: Path, phase3_config: LandscapeConfig):
    species_table = default_species_table()
    fia_paths, crosswalk_path = _write_fia_tables(tmp_path, phase3_config)

    grid_a = load_fia_plots(FiaPaths(**{key: Path(value) for key, value in fia_paths.items() if key != "crosswalk_path"}), species_table, crosswalk_path, phase3_config, search_radius_m=25.0)
    grid_b = load_fia_plots(FiaPaths(**{key: Path(value) for key, value in fia_paths.items() if key != "crosswalk_path"}), species_table, crosswalk_path, phase3_config, search_radius_m=25.0)

    southwest = grid_a[0, 0]
    northeast = grid_a[-1, -1]
    middle = grid_a[1, 1]

    assert [cohort.species_id for cohort in southwest.cohorts] == [cohort.species_id for cohort in grid_b[0, 0].cohorts]
    assert pytest.approx(southwest.total_biomass_kg_ha) == grid_b[0, 0].total_biomass_kg_ha
    assert any(cohort.species_id == 0 for cohort in southwest.cohorts)
    assert any(cohort.species_id == 3 for cohort in northeast.cohorts)
    assert len(middle.cohorts) >= 2


def test_fia_ingestion_fails_on_missing_crosswalk_mapping(tmp_path: Path, phase3_config: LandscapeConfig):
    species_table = default_species_table()
    fia_paths, crosswalk_path = _write_fia_tables(tmp_path, phase3_config, include_extra_species=True)
    paths = FiaPaths(plots_path=fia_paths["plots_path"], trees_path=fia_paths["trees_path"], conditions_path=fia_paths["conditions_path"])

    with pytest.raises(ValueError, match="Missing FIA SPCD"):
        load_fia_plots(paths, species_table, crosswalk_path, phase3_config)


def test_mtbs_import_creates_post_start_events_and_prestart_seed(tmp_path: Path, phase3_config: LandscapeConfig):
    mtbs_path = _write_mtbs(tmp_path, phase3_config)
    result = load_mtbs_events(mtbs_path, phase3_config, start_year=2015)

    assert len(result.events) == 1
    assert result.events[0].year == 2018
    assert result.events[0].params["historical_footprint"] is True
    assert np.max(result.pre_start_fire_year) == 2010


def test_manifest_builds_engine_and_runs_short_baseline(tmp_path: Path, phase3_config: LandscapeConfig):
    dem_path = tmp_path / "dem.tif"
    transform = from_origin(phase3_config.origin_utm[0], phase3_config.origin_utm[1] + phase3_config.extent_m[1], phase3_config.cell_size_m, phase3_config.cell_size_m)
    dem = np.flipud(np.array([[100.0, 101.0, 102.0, 103.0], [101.0, 102.0, 103.0, 104.0], [102.0, 103.0, 104.0, 105.0], [103.0, 104.0, 105.0, 106.0]], dtype=np.float32))
    _write_raster(dem_path, dem, transform, phase3_config.epsg)
    climate_paths = _write_climate_stack(tmp_path, phase3_config)
    fia_paths, _ = _write_fia_tables(tmp_path, phase3_config)
    ssurgo_path = _write_ssurgo(tmp_path, phase3_config)
    mtbs_path = _write_mtbs(tmp_path, phase3_config)

    manifest = {
        "site_id": "tiny_phase3",
        "epsg": phase3_config.epsg,
        "origin_utm": list(phase3_config.origin_utm),
        "extent_m": list(phase3_config.extent_m),
        "cell_size_m": phase3_config.cell_size_m,
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
    manifest_path = tmp_path / "site_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    engine = LandscapeInitializer.from_site_manifest(manifest_path)
    engine.run(2015, 2017)

    assert engine.terrain.elevation.shape == phase3_config.shape
    assert engine.soils.awc.shape == phase3_config.shape
    assert engine.climate.growing_degree_days.shape == phase3_config.shape
    assert engine.history[-1].year == 2017
    assert any(
        cell.disturbance_type_last == DisturbanceType.FIRE and cell.time_since_disturbance >= 5
        for cell in engine.vegetation.ravel()
    )
