"""Manifest-driven real-data landscape initialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .climate import ClimateLayers
from .config import LandscapeConfig
from .engine import WattForestEngine
from .events import EventLog, SimEvent
from .io.fia import FiaPaths, load_fia_plots
from .io.geospatial import read_raster_to_grid, rasterize_shapes, read_vector_layer, target_transform
from .io.landfire import load_landfire_layers
from .io.mtbs import load_mtbs_events
from .soils import SoilLayers
from .species import SpeciesParams, default_species_table
from .state import Cohort, DisturbanceType
from .terrain import TerrainLayers
from .tuning import CalibrationGlobals
from .validation import SitePatternSummary, compare_site_patterns, load_site_pattern_summary, summarize_engine


def _resolve_manifest_path(base_dir: Path, path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _load_manifest(manifest_path: str | Path) -> tuple[dict, Path]:
    manifest_file = Path(manifest_path).resolve()
    payload = json.loads(manifest_file.read_text())
    required = {
        "site_id",
        "epsg",
        "origin_utm",
        "extent_m",
        "cell_size_m",
        "start_year",
        "dem_path",
        "ssurgo_path",
        "climate",
        "fia",
        "mtbs_path",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"Site manifest is missing required keys: {missing}")
    return payload, manifest_file.parent


def _landscape_config_from_manifest(manifest: Mapping[str, object]) -> LandscapeConfig:
    return LandscapeConfig(
        extent_m=tuple(float(value) for value in manifest["extent_m"]),
        cell_size_m=float(manifest["cell_size_m"]),
        origin_utm=tuple(float(value) for value in manifest["origin_utm"]),
        epsg=int(manifest["epsg"]),
    )


@dataclass(frozen=True)
class ClimateManifestBundle:
    baseline: ClimateLayers
    yearly_overrides: dict[int, ClimateLayers]


def _resolve_nested_paths(base_dir: Path, payload: Mapping[str, object]) -> dict[str, object]:
    resolved: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, Mapping):
            resolved[str(key)] = _resolve_nested_paths(base_dir, value)
        else:
            resolved[str(key)] = _resolve_manifest_path(base_dir, value)
    return resolved


def _compute_flow_accumulation(elevation: np.ndarray, config: LandscapeConfig) -> np.ndarray:
    try:
        from pysheds.grid import Grid
        from rasterio.io import MemoryFile
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Phase 3 terrain initialization requires pysheds and rasterio"
        ) from exc

    north_up = np.flipud(elevation).astype(np.float32)
    profile = {
        "driver": "GTiff",
        "height": config.shape[0],
        "width": config.shape[1],
        "count": 1,
        "dtype": "float32",
        "transform": target_transform(config),
        "crs": f"EPSG:{config.epsg}",
        "nodata": -9999.0,
    }

    with MemoryFile() as memfile:
        with memfile.open(**profile) as dataset:
            dataset.write(north_up, 1)
        grid = Grid.from_raster(memfile.name)
        dem = grid.read_raster(memfile.name)
        dem = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dem)))
        flow_direction = grid.flowdir(dem)
        accumulation = np.asarray(grid.accumulation(flow_direction), dtype=np.float32)
    return np.flipud(accumulation)


def _terrain_from_array(elevation: np.ndarray, config: LandscapeConfig) -> TerrainLayers:
    grad_y, grad_x = np.gradient(elevation, config.cell_size_m)
    slope = np.degrees(np.arctan(np.hypot(grad_x, grad_y))).astype(np.float32)
    aspect = (np.degrees(np.arctan2(-grad_x, -grad_y)) + 360.0).astype(np.float32) % 360.0
    dyy, _ = np.gradient(grad_y, config.cell_size_m)
    _, dxx = np.gradient(grad_x, config.cell_size_m)
    curvature = (dxx + dyy).astype(np.float32)

    flow_accumulation = _compute_flow_accumulation(elevation, config)
    contributing_area = np.maximum(flow_accumulation, 1.0) * config.cell_size_m
    slope_radians = np.maximum(np.radians(slope), np.radians(0.5))
    twi = np.log(contributing_area / np.tan(slope_radians)).astype(np.float32)
    twi = np.clip(twi, 0.0, None)

    return TerrainLayers(
        elevation=elevation.astype(np.float32),
        slope=slope,
        aspect=aspect,
        twi=twi,
        flow_accumulation=flow_accumulation.astype(np.float32),
        curvature=curvature,
    )


def _texture_codes(texture_values) -> np.ndarray:
    if np.issubdtype(texture_values.dtype, np.number):
        return np.rint(texture_values).astype(np.uint8)
    normalized = np.array([str(value).strip().lower() for value in texture_values], dtype=object)
    categories = {name: index + 1 for index, name in enumerate(sorted(set(normalized)))}
    return np.array([categories[name] for name in normalized], dtype=np.uint8)


def _seed_prestart_fire_state(vegetation: np.ndarray, pre_start_fire_year: np.ndarray, start_year: int) -> None:
    rows, cols = np.where(pre_start_fire_year >= 0)
    for row, col in zip(rows.tolist(), cols.tolist()):
        fire_year = int(pre_start_fire_year[row, col])
        cell = vegetation[row, col]
        cell.time_since_disturbance = max(0, start_year - fire_year)
        cell.disturbance_type_last = DisturbanceType.FIRE
        cell.recent_disturbance_severity = max(cell.recent_disturbance_severity, 0.15)
        cell.recent_fire_severity = max(cell.recent_fire_severity, 0.15)


def _apply_landfire_context(
    vegetation: np.ndarray,
    landfire_layers: Mapping[str, np.ndarray],
    species_table: Sequence[SpeciesParams],
) -> None:
    evt = np.asarray(landfire_layers.get("evt")) if "evt" in landfire_layers else None
    disturbance = np.asarray(landfire_layers.get("disturbance")) if "disturbance" in landfire_layers else None
    fuel_model = np.asarray(landfire_layers.get("fuel_model")) if "fuel_model" in landfire_layers else None
    pioneer_species = next((species for species in species_table if "pioneer" in species.pft), None)
    for row in range(vegetation.shape[0]):
        for col in range(vegetation.shape[1]):
            cell = vegetation[row, col]
            if disturbance is not None:
                disturbance_value = float(disturbance[row, col])
                if disturbance_value > 0.0:
                    cell.recent_disturbance_severity = max(cell.recent_disturbance_severity, min(1.0, disturbance_value))
            if fuel_model is not None:
                fuel_value = float(fuel_model[row, col])
                cell.litter_kg_ha += 20.0 * max(0.0, fuel_value)
            if evt is not None and not cell.cohorts and pioneer_species is not None and int(evt[row, col]) > 0:
                cell.add_or_merge_cohort(
                    Cohort(
                        species_id=pioneer_species.species_id,
                        age=5,
                        biomass_kg_ha=250.0,
                        density_stems_ha=90.0,
                        canopy_height_m=1.5,
                        crown_cover_frac=0.03,
                        vigor=0.8,
                    ),
                    species=pioneer_species,
                )


@dataclass(frozen=True)
class Phase3BaselineRun:
    """End-to-end Phase 3 result for one manifest-driven baseline run."""

    manifest_path: Path
    site_id: str
    start_year: int
    end_year: int
    engine: WattForestEngine
    simulated: SitePatternSummary
    observed: SitePatternSummary | None
    comparison: dict[str, float] | None


class LandscapeInitializer:
    """Build a real-data engine from a local site package."""

    @classmethod
    def from_site_manifest(
        cls,
        manifest_path: str | Path,
        *,
        species_table: Sequence[SpeciesParams] | None = None,
        calibration_globals: CalibrationGlobals | None = None,
    ) -> WattForestEngine:
        manifest, base_dir = _load_manifest(manifest_path)
        config = _landscape_config_from_manifest(manifest)
        resolved_species_table = list(species_table or default_species_table())

        terrain = cls.terrain_from_dem(_resolve_manifest_path(base_dir, manifest["dem_path"]), config)
        soils = cls.soils_from_ssurgo(_resolve_manifest_path(base_dir, manifest["ssurgo_path"]), config)
        climate_bundle = cls.climate_from_manifest(_resolve_nested_paths(base_dir, dict(manifest["climate"])), config)
        vegetation = cls.vegetation_from_fia(
            {
                "plots_path": _resolve_manifest_path(base_dir, manifest["fia"]["plots_path"]),
                "trees_path": _resolve_manifest_path(base_dir, manifest["fia"]["trees_path"]),
                "conditions_path": _resolve_manifest_path(base_dir, manifest["fia"]["conditions_path"]),
            },
            resolved_species_table,
            _resolve_manifest_path(base_dir, manifest["fia"]["crosswalk_path"]),
            config,
        )

        mtbs_result = load_mtbs_events(
            _resolve_manifest_path(base_dir, manifest["mtbs_path"]),
            config,
            start_year=int(manifest["start_year"]),
        )
        _seed_prestart_fire_state(vegetation, mtbs_result.pre_start_fire_year, int(manifest["start_year"]))

        landfire_layers = cls.landfire_from_manifest(
            _resolve_nested_paths(base_dir, dict(manifest["landfire"]))
            if isinstance(manifest.get("landfire"), Mapping)
            else None,
            config,
        )
        if landfire_layers is not None:
            _apply_landfire_context(vegetation, landfire_layers, resolved_species_table)

        engine = WattForestEngine(
            config=config,
            species_table=resolved_species_table,
            terrain=terrain,
            soils=soils,
            climate=climate_bundle.baseline,
            event_log=EventLog(events=mtbs_result.events),
            initial_vegetation=vegetation,
            calibration_globals=calibration_globals,
        )
        engine.set_climate_scenario(climate_bundle.baseline, climate_bundle.yearly_overrides)
        return engine

    @staticmethod
    def terrain_from_dem(dem_path: str | Path, config: LandscapeConfig) -> TerrainLayers:
        elevation = read_raster_to_grid(
            dem_path,
            config,
            categorical=False,
            dtype=np.float32,
            fail_on_nodata=True,
        )
        if np.isnan(elevation).any():
            raise ValueError(f"DEM {dem_path} contains nodata holes inside the target extent")
        return _terrain_from_array(elevation, config)

    @staticmethod
    def soils_from_ssurgo(ssurgo_path: str | Path, config: LandscapeConfig) -> SoilLayers:
        ssurgo = read_vector_layer(ssurgo_path, config.epsg)
        required = ("awc", "depth_to_restriction", "texture_class")
        missing = [column for column in required if column not in ssurgo.columns]
        if missing:
            raise ValueError(f"SSURGO layer is missing required fields: {missing}")

        if "rock_fraction" not in ssurgo.columns:
            depth = ssurgo["depth_to_restriction"].astype(float).to_numpy()
            ssurgo = ssurgo.copy()
            ssurgo["rock_fraction"] = np.clip(0.05 + np.maximum(0.0, 50.0 - depth) / 100.0, 0.05, 0.60)

        coverage = rasterize_shapes(((geometry, 1) for geometry in ssurgo.geometry if geometry is not None and not geometry.is_empty), config, fill=0, dtype=np.uint8, all_touched=True)
        if np.any(coverage == 0):
            raise ValueError("SSURGO polygons do not fully cover the target extent")

        awc = rasterize_shapes(
            ((geometry, float(value)) for geometry, value in zip(ssurgo.geometry, ssurgo["awc"].astype(float)) if geometry is not None and not geometry.is_empty),
            config,
            fill=np.nan,
            dtype=np.float32,
            all_touched=True,
        )
        depth = rasterize_shapes(
            ((geometry, float(value)) for geometry, value in zip(ssurgo.geometry, ssurgo["depth_to_restriction"].astype(float)) if geometry is not None and not geometry.is_empty),
            config,
            fill=np.nan,
            dtype=np.float32,
            all_touched=True,
        )
        rock = rasterize_shapes(
            ((geometry, float(value)) for geometry, value in zip(ssurgo.geometry, ssurgo["rock_fraction"].astype(float)) if geometry is not None and not geometry.is_empty),
            config,
            fill=np.nan,
            dtype=np.float32,
            all_touched=True,
        )
        texture_values = _texture_codes(ssurgo["texture_class"].to_numpy())
        texture = rasterize_shapes(
            ((geometry, int(value)) for geometry, value in zip(ssurgo.geometry, texture_values) if geometry is not None and not geometry.is_empty),
            config,
            fill=0,
            dtype=np.uint8,
            all_touched=True,
        )
        if np.isnan(awc).any() or np.isnan(depth).any() or np.isnan(rock).any() or np.any(texture == 0):
            raise ValueError("SSURGO rasterization left uncovered cells in the target extent")

        return SoilLayers(
            awc=awc.astype(np.float32),
            depth_to_restriction=depth.astype(np.float32),
            texture_class=texture.astype(np.uint8),
            rock_fraction=rock.astype(np.float32),
        )

    @staticmethod
    def climate_from_rasters(climate_paths: Mapping[str, str | Path], config: LandscapeConfig) -> ClimateLayers:
        required = {"gdd_path", "precip_path", "drought_path", "frost_free_path"}
        missing = sorted(required - set(climate_paths))
        if missing:
            raise ValueError(f"Climate input is missing required rasters: {missing}")

        gdd = read_raster_to_grid(climate_paths["gdd_path"], config, dtype=np.float32, fail_on_nodata=True)
        precip = read_raster_to_grid(climate_paths["precip_path"], config, dtype=np.float32, fail_on_nodata=True)
        drought = read_raster_to_grid(climate_paths["drought_path"], config, dtype=np.float32, fail_on_nodata=True)
        frost = read_raster_to_grid(climate_paths["frost_free_path"], config, dtype=np.float32, fail_on_nodata=True)

        if any(layer.shape != config.shape for layer in (gdd, precip, drought, frost)):
            raise ValueError("Climate rasters did not align to the landscape shape")

        return ClimateLayers(
            growing_degree_days=gdd.astype(np.float32),
            annual_precip_mm=precip.astype(np.float32),
            drought_index=drought.astype(np.float32),
            frost_free_days=np.rint(frost).astype(np.int16),
        )

    @staticmethod
    def climate_from_manifest(climate_manifest: Mapping[str, object], config: LandscapeConfig) -> ClimateManifestBundle:
        if "baseline" in climate_manifest:
            baseline_block = climate_manifest["baseline"]
            if not isinstance(baseline_block, Mapping):
                raise ValueError("climate.baseline must be an object containing the four baseline rasters")
            baseline_paths = baseline_block
            overrides_block = climate_manifest.get("yearly_overrides", {})
        else:
            baseline_paths = climate_manifest
            overrides_block = {}

        baseline = LandscapeInitializer.climate_from_rasters(baseline_paths, config)
        yearly_overrides: dict[int, ClimateLayers] = {}

        if overrides_block:
            if not isinstance(overrides_block, Mapping):
                raise ValueError("climate.yearly_overrides must be an object keyed by year")
            for year_key, override_block in overrides_block.items():
                if not isinstance(override_block, Mapping):
                    raise ValueError("Each climate yearly override must be an object containing the four rasters")
                yearly_overrides[int(year_key)] = LandscapeInitializer.climate_from_rasters(override_block, config)

        return ClimateManifestBundle(baseline=baseline, yearly_overrides=yearly_overrides)

    @staticmethod
    def landfire_from_manifest(
        landfire_manifest: Mapping[str, object] | None,
        config: LandscapeConfig,
    ) -> dict[str, np.ndarray] | None:
        if not landfire_manifest:
            return None
        if not isinstance(landfire_manifest, Mapping):
            raise ValueError("landfire block must be an object mapping layer names to raster paths")
        return load_landfire_layers({name: path for name, path in landfire_manifest.items()}, config)

    @staticmethod
    def vegetation_from_fia(
        fia_paths: Mapping[str, str | Path],
        species_table: Sequence[SpeciesParams],
        crosswalk_path: str | Path,
        config: LandscapeConfig,
    ) -> np.ndarray:
        return load_fia_plots(
            FiaPaths(
                plots_path=Path(fia_paths["plots_path"]),
                trees_path=Path(fia_paths["trees_path"]),
                conditions_path=Path(fia_paths["conditions_path"]),
            ),
            species_table=species_table,
            crosswalk_path=crosswalk_path,
            config=config,
        )

    @staticmethod
    def events_from_mtbs(mtbs_path: str | Path, config: LandscapeConfig, start_year: int) -> list[SimEvent]:
        return load_mtbs_events(mtbs_path, config, start_year).events

    @staticmethod
    def validation_targets_from_manifest(manifest_path: str | Path) -> SitePatternSummary | None:
        manifest, base_dir = _load_manifest(manifest_path)
        validation = manifest.get("validation")
        if validation is None:
            return None
        if not isinstance(validation, Mapping):
            raise ValueError("Manifest validation block must be an object")
        targets_path = validation.get("targets_path")
        if not targets_path:
            raise ValueError("Manifest validation block must define targets_path")
        return load_site_pattern_summary(_resolve_manifest_path(base_dir, targets_path))

    @classmethod
    def run_phase3_baseline(
        cls,
        manifest_path: str | Path,
        *,
        end_year: int | None = None,
    ) -> Phase3BaselineRun:
        manifest, _ = _load_manifest(manifest_path)
        start_year = int(manifest["start_year"])

        resolved_end_year = end_year
        validation = manifest.get("validation")
        if resolved_end_year is None and isinstance(validation, Mapping) and "baseline_end_year" in validation:
            resolved_end_year = int(validation["baseline_end_year"])
        if resolved_end_year is None:
            raise ValueError(
                "Phase 3 baseline run requires end_year or validation.baseline_end_year in the manifest"
            )
        if resolved_end_year < start_year:
            raise ValueError(
                f"Phase 3 baseline end_year {resolved_end_year} is earlier than manifest start_year {start_year}"
            )

        engine = cls.from_site_manifest(manifest_path)
        observed = cls.validation_targets_from_manifest(manifest_path)
        engine.run(start_year, resolved_end_year)
        simulated = summarize_engine(engine)
        comparison = compare_site_patterns(observed, simulated) if observed is not None else None

        return Phase3BaselineRun(
            manifest_path=Path(manifest_path).resolve(),
            site_id=str(manifest["site_id"]),
            start_year=start_year,
            end_year=resolved_end_year,
            engine=engine,
            simulated=simulated,
            observed=observed,
            comparison=comparison,
        )

    @classmethod
    def run_phase4_calibration(
        cls,
        manifest_path: str | Path,
        *,
        calibration_spec_path: str | Path | None = None,
        end_year: int | None = None,
        n_samples: int = 250,
        seed: int = 0,
        sobol_base_n: int = 128,
    ):
        from .calibration import run_phase4_calibration

        return run_phase4_calibration(
            manifest_path,
            calibration_spec_path=calibration_spec_path,
            end_year=end_year,
            n_samples=n_samples,
            seed=seed,
            sobol_base_n=sobol_base_n,
            engine_builder=cls.from_site_manifest,
        )
