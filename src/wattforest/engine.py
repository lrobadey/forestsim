"""Main simulation engine scaffold."""

from __future__ import annotations

import copy
import pickle
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .climate import ClimateLayers, ClimateScenario
from .config import LandscapeConfig
from .events import EventLog, EventType, SimEvent
from .io.checkpoint import load_checkpoint as load_engine_checkpoint
from .io.checkpoint import save_checkpoint as save_engine_checkpoint
from .metrics import PatternMetrics, YearRecord
from .modules import FireModule, GrazingModule, GrowthModule, HarvestModule, HydrologyModule
from .modules import LightModule, MortalityModule, RecruitmentModule, WindthrowModule
from .modules import recompute_cohort_structure
from .rng import DeterministicRNG
from .soils import SoilLayers
from .species import SpeciesParams, default_species_table
from .state import CellVegetation, Cohort, DisturbanceType
from .terrain import TerrainLayers
from .tuning import CalibrationGlobals


class WattForestEngine:
    """Deterministic, event-sourced forest landscape simulator scaffold."""

    def __init__(
        self,
        config: LandscapeConfig,
        species_table: List[SpeciesParams],
        terrain: TerrainLayers,
        soils: SoilLayers,
        climate: ClimateLayers,
        event_log: EventLog,
        initial_vegetation: Optional[np.ndarray] = None,
        calibration_globals: CalibrationGlobals | None = None,
    ):
        self.config = config
        self.species_table = list(species_table or default_species_table())
        self.species = {species.species_id: species for species in self.species_table}
        self.terrain = terrain
        self.soils = soils
        self._climate_scenario = ClimateScenario.from_baseline(climate)
        self.climate = self._climate_scenario.for_year(0)
        self._active_climate_year: Optional[int] = None
        self.event_log = event_log
        self.calibration_globals = calibration_globals or CalibrationGlobals()
        self.rng = DeterministicRNG(event_log.global_seed)
        self.vegetation = self._init_vegetation(initial_vegetation)
        self._initial_vegetation = copy.deepcopy(self.vegetation)
        self.checkpoints: Dict[int, bytes] = {}
        self.checkpoint_interval = 50
        self.history: List[YearRecord] = []
        self.start_year: Optional[int] = None
        self._ground_light = np.ones(self.config.shape, dtype=np.float32)
        self._cohort_light = np.empty(self.config.shape, dtype=object)
        self.light_module = LightModule()
        self.growth_module = GrowthModule()
        self.mortality_module = MortalityModule()
        self.recruitment_module = RecruitmentModule()
        self.fire_module = FireModule(config)
        self.windthrow_module = WindthrowModule()
        self.harvest_module = HarvestModule()
        self.grazing_module = GrazingModule()
        self.hydrology_module = HydrologyModule()
        self._river_moisture_bonus = np.zeros(self.config.shape, dtype=np.float32)
        self._river_recruitment_scalar = np.ones(self.config.shape, dtype=np.float32)
        self._climate_shift_gdd_delta = np.zeros(self.config.shape, dtype=np.float32)
        self._climate_shift_precip_delta = np.zeros(self.config.shape, dtype=np.float32)
        self._climate_shift_drought_delta = np.zeros(self.config.shape, dtype=np.float32)
        self._climate_shift_frost_free_delta = np.zeros(self.config.shape, dtype=np.int16)
        self._area_burned_ha = 0.0
        self._area_harvested_ha = 0.0
        self._area_blown_down_ha = 0.0

    @classmethod
    def from_synthetic(
        cls,
        config: LandscapeConfig,
        species_table: Optional[List[SpeciesParams]] = None,
        event_log: Optional[EventLog] = None,
        initial_vegetation: Optional[np.ndarray] = None,
        calibration_globals: CalibrationGlobals | None = None,
    ) -> "WattForestEngine":
        """Create a phase-0 engine with synthetic terrain, soils, climate, and PFTs."""

        terrain = TerrainLayers.synthetic(config)
        soils = SoilLayers.synthetic(config, terrain=terrain)
        climate = ClimateLayers.synthetic(config, terrain=terrain)
        resolved_species_table = species_table or default_species_table()
        return cls(
            config=config,
            species_table=resolved_species_table,
            terrain=terrain,
            soils=soils,
            climate=climate,
            event_log=event_log or EventLog(),
            initial_vegetation=initial_vegetation
            if initial_vegetation is not None
            else (cls._synthetic_seed_mosaic(config, resolved_species_table) if config.n_cells > 1 else None),
            calibration_globals=calibration_globals,
        )

    @staticmethod
    def _synthetic_seed_mosaic(
        config: LandscapeConfig,
        species_table: List[SpeciesParams],
    ) -> np.ndarray:
        grid = np.empty(config.shape, dtype=object)
        species_lookup = {species.species_id: species for species in species_table}
        pioneer = species_table[0]
        for row in range(config.shape[0]):
            for col in range(config.shape[1]):
                cell = CellVegetation()
                if (row + col) % 3 == 0:
                    cohort = Cohort(
                        species_id=pioneer.species_id,
                        age=4 + ((row * 3 + col) % 4),
                        biomass_kg_ha=120.0 + 25.0 * ((row + col) % 5),
                        density_stems_ha=55.0 + 8.0 * ((row * 2 + col) % 4),
                        canopy_height_m=0.0,
                        crown_cover_frac=0.0,
                        vigor=0.8,
                    )
                    recompute_cohort_structure(cohort, species_lookup[cohort.species_id])
                    cell.cohorts.append(cohort)
                    cell.mineral_soil_exposed_frac = 0.3
                grid[row, col] = cell
        return grid

    def set_climate_scenario(
        self,
        baseline: ClimateLayers,
        yearly_overrides: Optional[Dict[int, ClimateLayers]] = None,
    ) -> None:
        self._climate_scenario = ClimateScenario.from_baseline(baseline, yearly_overrides)
        active_year = 0 if self._active_climate_year is None else self._active_climate_year
        self.climate = self._climate_scenario.for_year(active_year)
        self._active_climate_year = active_year

    def _init_vegetation(self, initial_vegetation: Optional[np.ndarray]) -> np.ndarray:
        if initial_vegetation is not None:
            return initial_vegetation
        grid = np.empty(self.config.shape, dtype=object)
        for row in range(self.config.shape[0]):
            for col in range(self.config.shape[1]):
                grid[row, col] = CellVegetation()
        return grid

    def run(self, start_year: int, end_year: int) -> None:
        self.start_year = start_year if self.start_year is None else self.start_year
        self.history = [record for record in self.history if record.year < start_year]
        for year in range(start_year, end_year + 1):
            self._reset_year_counters()
            for event in self.event_log.events_for_year(year):
                self._apply_event(event, year)
            self._update_climate(year)
            self._compute_light_field()
            self._grow_cohorts(year)
            self._apply_mortality(year)
            self._recruit_new_cohorts(year)
            self._update_fuels(year)
            self._record_year(year)
            if year % self.checkpoint_interval == 0:
                self._save_checkpoint(year)

    def replay_from(self, edit_year: int, end_year: int) -> None:
        valid_checkpoints = [year for year in self.checkpoints if year < edit_year]
        if valid_checkpoints:
            restore_year = max(valid_checkpoints)
            self._restore_checkpoint(restore_year)
            rerun_start = restore_year + 1
        else:
            self._reset_to_initial()
            restore_year = self.start_year or edit_year
            self.history = []
            rerun_start = restore_year
        if rerun_start <= end_year:
            self.run(rerun_start, end_year)

    def save_checkpoint(self, path: str | Path) -> None:
        save_engine_checkpoint(path, self._export_engine_state())

    @classmethod
    def load_checkpoint(cls, path: str | Path) -> "WattForestEngine":
        state = load_engine_checkpoint(path)
        engine = cls(
            config=state["config"],
            species_table=state["species_table"],
            terrain=state["terrain"],
            soils=state["soils"],
            climate=state["baseline_climate"],
            event_log=state["event_log"],
            initial_vegetation=copy.deepcopy(state["initial_vegetation"]),
            calibration_globals=copy.deepcopy(state.get("calibration_globals", CalibrationGlobals())),
        )
        engine.set_climate_scenario(
            state["baseline_climate"],
            state.get("yearly_climate_overrides", {}),
        )
        engine.vegetation = copy.deepcopy(state["vegetation"])
        engine._initial_vegetation = copy.deepcopy(state["initial_vegetation"])
        engine.checkpoints = copy.deepcopy(state.get("checkpoints", {}))
        engine.checkpoint_interval = int(state.get("checkpoint_interval", 50))
        engine.history = copy.deepcopy(state["history"])
        engine.start_year = state["start_year"]
        engine._area_burned_ha = float(state.get("area_burned_ha", 0.0))
        engine._area_harvested_ha = float(state.get("area_harvested_ha", 0.0))
        engine._area_blown_down_ha = float(state.get("area_blown_down_ha", 0.0))
        engine._active_climate_year = state.get("active_climate_year")
        if engine._active_climate_year is not None:
            engine.climate = engine._climate_scenario.for_year(engine._active_climate_year)
        engine.grazing_module.active_grazing = copy.deepcopy(state.get("grazing_state", {}))
        engine._river_moisture_bonus = copy.deepcopy(
            state.get("river_moisture_bonus", np.zeros(engine.config.shape, dtype=np.float32))
        )
        engine._river_recruitment_scalar = copy.deepcopy(
            state.get("river_recruitment_scalar", np.ones(engine.config.shape, dtype=np.float32))
        )
        engine._climate_shift_gdd_delta = copy.deepcopy(
            state.get("climate_shift_gdd_delta", np.zeros(engine.config.shape, dtype=np.float32))
        )
        engine._climate_shift_precip_delta = copy.deepcopy(
            state.get("climate_shift_precip_delta", np.zeros(engine.config.shape, dtype=np.float32))
        )
        engine._climate_shift_drought_delta = copy.deepcopy(
            state.get("climate_shift_drought_delta", np.zeros(engine.config.shape, dtype=np.float32))
        )
        engine._climate_shift_frost_free_delta = copy.deepcopy(
            state.get("climate_shift_frost_free_delta", np.zeros(engine.config.shape, dtype=np.int16))
        )
        return engine

    def _apply_event(self, event: SimEvent, year: int) -> None:
        if event.event_type not in {
            EventType.FIRE_IGNITION,
            EventType.PRESCRIBED_BURN,
            EventType.WINDSTORM,
            EventType.HARVEST,
            EventType.GRAZING_START,
            EventType.GRAZING_END,
            EventType.RIVER_SHIFT,
            EventType.FLOOD,
            EventType.CLIMATE_SHIFT,
            EventType.PLANTING,
            EventType.INSECT_OUTBREAK,
            EventType.CUSTOM,
        }:
            raise NotImplementedError(f"Event type {event.event_type.value} is not implemented in the spec-backed engine")

        event_params = event.params or {}
        if event.event_type in {EventType.FIRE_IGNITION, EventType.PRESCRIBED_BURN}:
            if bool(event_params.get("historical_footprint", False)):
                affected_mask = self._resolve_event_mask(event)
                severity_value = float(event_params.get("severity", 0.65))
                severity = np.zeros(self.config.shape, dtype=np.float32)
                severity[affected_mask] = np.clip(severity_value, 0.05, 1.0)
                self._apply_fire_effects(affected_mask, severity, year)
                return

            ignition_cells = self._resolve_ignition_cells(event)
            duration_hr = float(event_params.get("duration_hr", 6.0))
            wind_speed_ms = float(event_params.get("wind_speed_ms", 4.0))
            wind_dir_deg = float(event_params.get("wind_dir_deg", 90.0))
            moisture_offset = float(event_params.get("fuel_moisture_offset", 0.0))
            fuel_scale = 0.7 if event.event_type is EventType.PRESCRIBED_BURN else 1.0

            burned, severity = self.fire_module.spread_fire(
                ignition_cells=ignition_cells,
                duration_hr=duration_hr,
                wind_speed_ms=wind_speed_ms,
                wind_dir_deg=wind_dir_deg,
                fuel_load=self._fuel_load_grid(fuel_scale=fuel_scale),
                fuel_moisture=self._fuel_moisture_grid(moisture_offset=moisture_offset),
                terrain=self.terrain,
                vegetation_grid=self.vegetation,
                spread_scalar=self.calibration_globals.fire_spread_scalar,
            )
            ignition_buffer = np.zeros(self.config.shape, dtype=bool)
            ignition_severity = np.zeros(self.config.shape, dtype=np.float32)
            for row, col in ignition_cells:
                for nr in range(max(0, row - 1), min(self.config.shape[0], row + 2)):
                    for nc in range(max(0, col - 1), min(self.config.shape[1], col + 2)):
                        ignition_buffer[nr, nc] = True
                        ignition_severity[nr, nc] = 0.35
            if not np.any(burned):
                burned = ignition_buffer
                severity = ignition_severity
            else:
                severity = np.maximum(severity, ignition_severity * ignition_buffer.astype(np.float32))
                burned = burned | ignition_buffer
            self._apply_fire_effects(burned, severity, year)
            return

        if event.event_type is EventType.WINDSTORM:
            affected_mask = self._resolve_event_mask(event)
            damage = self.windthrow_module.apply_windstorm(
                wind_speed_ms=float(event_params.get("wind_speed_ms", 18.0)),
                wind_dir_deg=float(event_params.get("wind_dir_deg", 90.0)),
                affected_mask=affected_mask,
                vegetation_grid=self.vegetation,
                terrain=self.terrain,
                soil=self.soils,
                species=self.species,
                rng=self.rng,
                year=year,
                damage_scalar=self.calibration_globals.windthrow_damage_scalar,
            )
            self._apply_windthrow_effects(damage, year)
            return

        affected_mask = (
            self._resolve_event_mask_or_full(event)
            if event.event_type in {EventType.CLIMATE_SHIFT, EventType.CUSTOM}
            else self._resolve_event_mask(event)
        )

        if event.event_type is EventType.HARVEST:
            summary = self.harvest_module.apply_harvest(
                affected_mask=affected_mask,
                method=str(event_params.get("method", "selection")),
                retention_frac=float(event_params.get("retention_frac", 0.15)),
                species_filter=event_params.get("species_filter"),
                min_biomass_kg_ha=float(event_params.get("min_biomass_kg_ha", 0.0)),
                vegetation_grid=self.vegetation,
                species_lookup=self.species,
            )
            cell_area_ha = (self.config.cell_size_m**2) / 10000.0
            self._area_harvested_ha += float(summary["cells_treated"]) * cell_area_ha
            return

        if event.event_type is EventType.GRAZING_START:
            self.grazing_module.activate(affected_mask, float(event_params.get("intensity", 0.5)))
            return

        if event.event_type is EventType.GRAZING_END:
            self.grazing_module.deactivate(affected_mask)
            return

        if event.event_type is EventType.RIVER_SHIFT:
            scour_frac = float(event_params.get("scour_frac", 0.45))
            moisture_bonus = float(event_params.get("moisture_bonus", 0.25))
            recruitment_scalar = float(event_params.get("recruitment_scalar", 1.35))
            self.hydrology_module.apply_river_shift(
                affected_mask=affected_mask,
                scour_frac=scour_frac,
                moisture_bonus=moisture_bonus,
                recruitment_scalar=recruitment_scalar,
                river_moisture_bonus=self._river_moisture_bonus,
                river_recruitment_scalar=self._river_recruitment_scalar,
            )
            self._apply_river_shift_effects(affected_mask, scour_frac, year)
            return

        if event.event_type is EventType.FLOOD:
            severity = float(np.clip(event_params.get("severity", 0.55), 0.0, 1.0))
            mortality_frac = float(np.clip(event_params.get("mortality_frac", 0.2 + 0.55 * severity), 0.0, 0.98))
            moisture_bonus = float(event_params.get("moisture_bonus", 0.12 + 0.28 * severity))
            recruitment_scalar = float(event_params.get("recruitment_scalar", 1.0 + 0.35 * severity))
            self.hydrology_module.apply_river_shift(
                affected_mask=affected_mask,
                scour_frac=mortality_frac,
                moisture_bonus=moisture_bonus,
                recruitment_scalar=recruitment_scalar,
                river_moisture_bonus=self._river_moisture_bonus,
                river_recruitment_scalar=self._river_recruitment_scalar,
            )
            self._apply_flood_effects(affected_mask, mortality_frac, severity, year)
            return

        if event.event_type is EventType.CLIMATE_SHIFT:
            affected_mask = self._resolve_event_mask_or_full(event)
            self._apply_climate_shift_effects(
                affected_mask=affected_mask,
                gdd_delta=float(event_params.get("gdd_delta", 0.0)),
                precip_delta_mm=float(event_params.get("precip_delta_mm", 0.0)),
                drought_delta=float(event_params.get("drought_delta", 0.0)),
                frost_free_delta=int(round(float(event_params.get("frost_free_delta", 0.0)))),
            )
            return

        if event.event_type is EventType.PLANTING:
            self._apply_planting_effects(
                affected_mask=affected_mask,
                year=year,
                species_id=event_params.get("species_id"),
                species_ids=event_params.get("species_ids"),
                age=int(event_params.get("age", 0)),
                biomass_kg_ha=float(event_params.get("biomass_kg_ha", 40.0)),
                density_stems_ha=float(event_params.get("density_stems_ha", 160.0)),
                vigor=float(np.clip(event_params.get("vigor", 0.95), 0.0, 1.0)),
            )
            return

        if event.event_type is EventType.INSECT_OUTBREAK:
            self._apply_insect_outbreak_effects(
                affected_mask=affected_mask,
                year=year,
                severity=float(np.clip(event_params.get("severity", 0.55), 0.0, 1.0)),
                species_filter=event_params.get("species_filter"),
                min_age=int(event_params.get("min_age", 0)),
                max_age=int(event_params["max_age"]) if "max_age" in event_params else None,
            )
            return

        if event.event_type is EventType.CUSTOM:
            self._apply_custom_event(event, year)
            return

    def _update_climate(self, year: int) -> None:
        base = self._climate_scenario.for_year(year)
        base.growing_degree_days = np.maximum(
            base.growing_degree_days + self._climate_shift_gdd_delta,
            0.0,
        ).astype(np.float32)
        base.annual_precip_mm = np.maximum(
            base.annual_precip_mm + self._climate_shift_precip_delta,
            0.0,
        ).astype(np.float32)
        base.drought_index = np.clip(
            base.drought_index + self._climate_shift_drought_delta,
            0.0,
            1.0,
        ).astype(np.float32)
        base.frost_free_days = np.clip(
            base.frost_free_days.astype(np.int32) + self._climate_shift_frost_free_delta.astype(np.int32),
            0,
            366,
        ).astype(np.int16)
        self.climate = base
        self._active_climate_year = int(year)

    def _reset_year_counters(self) -> None:
        self._area_burned_ha = 0.0
        self._area_harvested_ha = 0.0
        self._area_blown_down_ha = 0.0

    def _resolve_ignition_cells(self, event: SimEvent) -> List[tuple[int, int]]:
        if event.affected_cells is not None:
            rows, cols = np.where(self._resolve_event_mask(event))
            return list(zip(rows.tolist(), cols.tolist()))

        ignition_cells = event.params.get("ignition_cells") if event.params else None
        if ignition_cells:
            resolved: List[tuple[int, int]] = []
            for row, col in ignition_cells:
                if 0 <= row < self.config.shape[0] and 0 <= col < self.config.shape[1]:
                    resolved.append((int(row), int(col)))
            return resolved

        if event.center_xy is not None:
            center_col = int((event.center_xy[0] - self.config.origin_utm[0]) / self.config.cell_size_m)
            center_row = int((event.center_xy[1] - self.config.origin_utm[1]) / self.config.cell_size_m)
            radius_m = event.radius_m or self.config.cell_size_m * 0.5
            radius_cells = max(0, int(np.ceil(radius_m / self.config.cell_size_m)))
            resolved = []
            for row in range(max(0, center_row - radius_cells), min(self.config.shape[0], center_row + radius_cells + 1)):
                for col in range(max(0, center_col - radius_cells), min(self.config.shape[1], center_col + radius_cells + 1)):
                    dx = (col - center_col) * self.config.cell_size_m
                    dy = (row - center_row) * self.config.cell_size_m
                    if dx * dx + dy * dy <= radius_m * radius_m:
                        resolved.append((row, col))
            return resolved

        rows, cols = np.where(self._resolve_event_mask(event))
        resolved = list(zip(rows.tolist(), cols.tolist()))
        if not resolved:
            raise ValueError(f"Event {event.event_id} resolved to an empty ignition footprint")
        return resolved

    def _resolve_event_mask(self, event: SimEvent) -> np.ndarray:
        explicit_mask = event.affected_cells is not None
        circle = event.center_xy is not None or event.radius_m is not None
        polygon = bool(event.polygon_vertices)
        methods = int(explicit_mask) + int(circle) + int(polygon)
        if methods != 1:
            raise ValueError(
                f"Event {event.event_id} must define exactly one geometry: affected_cells, center_xy+radius_m, or polygon_vertices"
            )

        if explicit_mask:
            mask = np.asarray(event.affected_cells, dtype=bool)
            if mask.shape != self.config.shape:
                raise ValueError(f"Affected cell mask shape {mask.shape} does not match landscape shape {self.config.shape}")
            return mask.copy()

        if polygon:
            mask = self._polygon_to_mask(event.polygon_vertices)
            if not np.any(mask):
                raise ValueError(f"Event {event.event_id} polygon_vertices rasterized to an empty mask")
            return mask

        if event.center_xy is None or event.radius_m is None:
            raise ValueError(f"Event {event.event_id} circle geometry requires both center_xy and radius_m")

        center_col = int((event.center_xy[0] - self.config.origin_utm[0]) / self.config.cell_size_m)
        center_row = int((event.center_xy[1] - self.config.origin_utm[1]) / self.config.cell_size_m)
        radius_cells = max(0, int(np.ceil(event.radius_m / self.config.cell_size_m)))
        mask = np.zeros(self.config.shape, dtype=bool)
        for row in range(max(0, center_row - radius_cells), min(self.config.shape[0], center_row + radius_cells + 1)):
            for col in range(max(0, center_col - radius_cells), min(self.config.shape[1], center_col + radius_cells + 1)):
                dx = (col - center_col) * self.config.cell_size_m
                dy = (row - center_row) * self.config.cell_size_m
                if dx * dx + dy * dy <= event.radius_m * event.radius_m:
                    mask[row, col] = True
        if not np.any(mask):
            raise ValueError(f"Event {event.event_id} circle geometry resolved to an empty mask")
        return mask

    def _resolve_event_mask_or_full(self, event: SimEvent) -> np.ndarray:
        if event.affected_cells is None and event.center_xy is None and event.radius_m is None and not event.polygon_vertices:
            return np.ones(self.config.shape, dtype=bool)
        return self._resolve_event_mask(event)

    def _polygon_to_mask(self, vertices: List[tuple[float, float]] | None) -> np.ndarray:
        if not vertices or len(vertices) < 3:
            raise ValueError("polygon_vertices must contain at least three coordinates")
        polygon = [(float(x), float(y)) for x, y in vertices]
        mask = np.zeros(self.config.shape, dtype=bool)
        for row in range(self.config.shape[0]):
            y = self.config.origin_utm[1] + (row + 0.5) * self.config.cell_size_m
            for col in range(self.config.shape[1]):
                x = self.config.origin_utm[0] + (col + 0.5) * self.config.cell_size_m
                mask[row, col] = self._point_in_polygon(x, y, polygon)
        return mask

    @staticmethod
    def _point_in_polygon(x: float, y: float, polygon: List[tuple[float, float]]) -> bool:
        inside = False
        n = len(polygon)
        for index in range(n):
            x1, y1 = polygon[index]
            x2, y2 = polygon[(index + 1) % n]
            intersects = ((y1 > y) != (y2 > y)) and (
                x <= (x2 - x1) * (y - y1) / max(y2 - y1, 1e-12) + x1
            )
            if intersects:
                inside = not inside
        return inside

    def _fuel_load_grid(self, fuel_scale: float = 1.0) -> np.ndarray:
        fuel = np.zeros(self.config.shape, dtype=np.float32)
        for row in range(self.config.shape[0]):
            for col in range(self.config.shape[1]):
                cell = self.vegetation[row, col]
                canopy_fuel = 0.0
                for cohort in cell.cohorts:
                    species = self.species[cohort.species_id]
                    canopy_fuel += cohort.biomass_kg_ha * (0.02 + 0.08 * species.flammability)
                fuel[row, col] = fuel_scale * (
                    300.0
                    + cell.litter_kg_ha * 0.65
                    + cell.coarse_woody_debris_kg_ha * 0.45
                    + canopy_fuel
                )
        return fuel

    def _fuel_moisture_grid(self, moisture_offset: float = 0.0) -> np.ndarray:
        dryness = np.clip(self.climate.drought_index, 0.0, 1.0)
        canopy = self.canopy_cover_grid()
        moisture = 0.28 - 0.18 * dryness + 0.06 * canopy + moisture_offset
        return np.clip(moisture.astype(np.float32), 0.03, 0.45)

    def _apply_fire_effects(self, burned: np.ndarray, severity: np.ndarray, year: int) -> None:
        if not np.any(burned):
            return

        cell_area_ha = (self.config.cell_size_m**2) / 10000.0
        self._area_burned_ha += float(np.count_nonzero(burned)) * cell_area_ha

        rows, cols = np.where(burned)
        for row, col in zip(rows.tolist(), cols.tolist()):
            cell = self.vegetation[row, col]
            burn_severity = float(severity[row, col])
            total_killed = 0.0
            if not cell.cohorts:
                cell.time_since_disturbance = 0
                cell.disturbance_type_last = DisturbanceType.FIRE
                cell.mineral_soil_exposed_frac = min(1.0, cell.mineral_soil_exposed_frac + 0.5 * burn_severity)
                cell.recent_fire_severity = max(cell.recent_fire_severity, burn_severity)
                cell.recent_disturbance_severity = max(cell.recent_disturbance_severity, burn_severity)
                cell.regeneration_delay_yr = max(cell.regeneration_delay_yr, 2 + int(round(3.0 * burn_severity)))
                continue

            for idx, cohort in enumerate(list(cell.cohorts)):
                species = self.species[cohort.species_id]
                flammability = 0.35 + 0.65 * species.flammability
                mortality_frac = min(0.98, burn_severity * flammability)
                mortality_frac = min(0.98, mortality_frac + 0.12 + 0.08 * species.flammability)
                if self.rng.uniform("fire_survival", year, row, col, cohort.species_id, cohort.age) < 0.08:
                    mortality_frac *= 0.6
                killed = self.mortality_module.apply_cohort_mortality(cell, idx, mortality_frac, species)
                total_killed += killed
                cohort.vigor *= max(0.1, 1.0 - mortality_frac)
                cell.coarse_woody_debris_kg_ha = max(0.0, cell.coarse_woody_debris_kg_ha - killed * burn_severity * 0.35)

            cell.remove_empty_cohorts()
            if burn_severity > 0.05:
                residual_scalar = max(0.2, 1.0 - 0.45 * burn_severity)
                density_scalar = max(0.25, 1.0 - 0.35 * burn_severity)
                for cohort in cell.cohorts:
                    cohort.biomass_kg_ha *= residual_scalar
                    cohort.density_stems_ha *= density_scalar
                    recompute_cohort_structure(cohort, self.species[cohort.species_id])
                cell.remove_empty_cohorts()
            cell.time_since_disturbance = 0
            cell.disturbance_type_last = DisturbanceType.FIRE
            cell.litter_kg_ha *= max(0.0, 1.0 - 0.92 * burn_severity)
            cell.coarse_woody_debris_kg_ha *= max(0.05, 1.0 - 0.55 * burn_severity)
            cell.mineral_soil_exposed_frac = min(1.0, 0.45 + burn_severity * 0.55)
            cell.recent_fire_severity = max(cell.recent_fire_severity, burn_severity)
            cell.recent_disturbance_severity = max(
                cell.recent_disturbance_severity,
                min(1.0, burn_severity + total_killed / 6000.0),
            )
            cell.regeneration_delay_yr = max(cell.regeneration_delay_yr, 2 + int(round(4.0 * burn_severity)))

    def _apply_windthrow_effects(self, damage: np.ndarray, year: int) -> None:
        affected = damage > 0.0
        if not np.any(affected):
            return

        cell_area_ha = (self.config.cell_size_m**2) / 10000.0
        self._area_blown_down_ha += float(np.count_nonzero(affected)) * cell_area_ha

        rows, cols = np.where(affected)
        for row, col in zip(rows.tolist(), cols.tolist()):
            cell = self.vegetation[row, col]
            if not cell.cohorts:
                continue

            damage_frac = float(damage[row, col])
            dominant_height = max(1.0, cell.dominant_height_m)
            impacted_indices = [
                idx
                for idx, cohort in enumerate(cell.cohorts)
                if cohort.canopy_height_m >= max(2.0, dominant_height * 0.75)
            ]
            if not impacted_indices:
                impacted_indices = [int(np.argmax([cohort.canopy_height_m for cohort in cell.cohorts]))]

            total_killed = 0.0
            for idx in sorted(set(impacted_indices), reverse=True):
                cohort = cell.cohorts[idx]
                species = self.species[cohort.species_id]
                dominance = cohort.canopy_height_m / dominant_height
                mortality_frac = min(0.98, damage_frac * (0.55 + 0.35 * dominance))
                killed = self.mortality_module.apply_cohort_mortality(cell, idx, mortality_frac, species)
                total_killed += killed
                cohort.vigor *= max(0.15, 1.0 - 0.65 * damage_frac)

            cell.remove_empty_cohorts()
            cell.time_since_disturbance = 0
            cell.disturbance_type_last = DisturbanceType.WINDTHROW
            cell.mineral_soil_exposed_frac = min(1.0, cell.mineral_soil_exposed_frac + 0.12 + 0.18 * damage_frac)
            cell.recent_disturbance_severity = max(
                cell.recent_disturbance_severity,
                min(1.0, 0.2 + damage_frac + total_killed / 5000.0),
            )
            cell.regeneration_delay_yr = max(cell.regeneration_delay_yr, 2 + int(round(4.0 * damage_frac)))
        _ = year

    def _apply_river_shift_effects(self, affected_mask: np.ndarray, scour_frac: float, year: int) -> None:
        rows, cols = np.where(affected_mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            cell = self.vegetation[row, col]
            total_killed = 0.0
            for idx in range(len(cell.cohorts) - 1, -1, -1):
                cohort = cell.cohorts[idx]
                species = self.species[cohort.species_id]
                mortality_frac = min(0.98, scour_frac * (0.7 if cohort.canopy_height_m < 5.0 else 0.45))
                killed = self.mortality_module.apply_cohort_mortality(cell, idx, mortality_frac, species)
                total_killed += killed
                cohort.vigor *= max(0.2, 1.0 - 0.5 * scour_frac)
            cell.remove_empty_cohorts()
            cell.time_since_disturbance = 0
            cell.disturbance_type_last = DisturbanceType.RIVER_SHIFT
            cell.mineral_soil_exposed_frac = min(1.0, cell.mineral_soil_exposed_frac + 0.35 + 0.55 * scour_frac)
            cell.recent_disturbance_severity = max(
                cell.recent_disturbance_severity,
                min(1.0, 0.25 + 0.75 * scour_frac + total_killed / 6500.0),
            )
            cell.regeneration_delay_yr = max(cell.regeneration_delay_yr, 1 + int(round(3.0 * scour_frac)))
        _ = year

    def _apply_flood_effects(self, affected_mask: np.ndarray, mortality_frac: float, severity: float, year: int) -> None:
        rows, cols = np.where(affected_mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            cell = self.vegetation[row, col]
            total_killed = 0.0
            for idx in range(len(cell.cohorts) - 1, -1, -1):
                cohort = cell.cohorts[idx]
                species = self.species[cohort.species_id]
                height_scalar = 0.7 if cohort.canopy_height_m < 5.0 else 0.45
                vigor_scalar = 1.0 + 0.35 * max(0.0, 0.7 - cohort.vigor)
                applied_frac = min(0.98, mortality_frac * height_scalar * vigor_scalar)
                if applied_frac <= 0.0:
                    continue
                killed = self.mortality_module.apply_cohort_mortality(cell, idx, applied_frac, species)
                total_killed += killed
                cohort.vigor *= max(0.2, 1.0 - 0.45 * applied_frac)
            cell.remove_empty_cohorts()
            cell.time_since_disturbance = 0
            cell.disturbance_type_last = DisturbanceType.FLOOD
            cell.litter_kg_ha *= max(0.15, 1.0 - 0.55 * severity)
            cell.coarse_woody_debris_kg_ha *= max(0.2, 1.0 - 0.25 * severity)
            cell.mineral_soil_exposed_frac = min(1.0, cell.mineral_soil_exposed_frac + 0.12 + 0.25 * severity)
            cell.recent_disturbance_severity = max(
                cell.recent_disturbance_severity,
                min(1.0, 0.18 + 0.7 * severity + total_killed / 5500.0),
            )
            cell.regeneration_delay_yr = max(cell.regeneration_delay_yr, 1 + int(round(2.0 * severity)))
        _ = year

    def _apply_climate_shift_effects(
        self,
        *,
        affected_mask: np.ndarray,
        gdd_delta: float,
        precip_delta_mm: float,
        drought_delta: float,
        frost_free_delta: int,
    ) -> None:
        self._climate_shift_gdd_delta[affected_mask] += np.float32(gdd_delta)
        self._climate_shift_precip_delta[affected_mask] += np.float32(precip_delta_mm)
        self._climate_shift_drought_delta[affected_mask] += np.float32(drought_delta)
        updated = self._climate_shift_frost_free_delta.astype(np.int32)
        updated[affected_mask] += int(frost_free_delta)
        self._climate_shift_frost_free_delta = np.clip(updated, -366, 366).astype(np.int16)

    def _apply_planting_effects(
        self,
        *,
        affected_mask: np.ndarray,
        year: int,
        species_id: object = None,
        species_ids: object = None,
        age: int = 0,
        biomass_kg_ha: float = 40.0,
        density_stems_ha: float = 160.0,
        vigor: float = 0.95,
    ) -> None:
        candidates: list[int] = []
        if species_id is not None:
            candidates.append(int(species_id))
        if species_ids is not None:
            candidates.extend(int(value) for value in species_ids)
        if not candidates:
            candidates = [self.species_table[0].species_id]
        for candidate in candidates:
            if candidate not in self.species:
                raise ValueError(f"Unknown planting species_id {candidate}")

        rows, cols = np.where(affected_mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            selected_id = candidates[0]
            if len(candidates) > 1:
                selected_index = min(
                    len(candidates) - 1,
                    int(self.rng.uniform("planting_species", year, row, col) * len(candidates)),
                )
                selected_id = candidates[selected_index]
            species = self.species[selected_id]
            cohort = Cohort(
                species_id=selected_id,
                age=max(0, int(age)),
                biomass_kg_ha=max(1.0, float(biomass_kg_ha)),
                density_stems_ha=max(1.0, float(density_stems_ha)),
                canopy_height_m=0.0,
                crown_cover_frac=0.0,
                vigor=float(np.clip(vigor, 0.0, 1.0)),
            )
            recompute_cohort_structure(cohort, species)
            cell = self.vegetation[row, col]
            cell.add_or_merge_cohort(cohort, age_window=3, species=species)
            cell.time_since_disturbance = 0
            cell.disturbance_type_last = DisturbanceType.PLANTING
            cell.mineral_soil_exposed_frac = max(0.0, cell.mineral_soil_exposed_frac - 0.12)
            cell.recent_disturbance_severity = max(cell.recent_disturbance_severity, 0.08)

    def _apply_insect_outbreak_effects(
        self,
        *,
        affected_mask: np.ndarray,
        year: int,
        severity: float,
        species_filter: object = None,
        min_age: int = 0,
        max_age: int | None = None,
    ) -> None:
        allowed_species = {int(value) for value in species_filter} if species_filter else None
        rows, cols = np.where(affected_mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            cell = self.vegetation[row, col]
            total_killed = 0.0
            for idx in range(len(cell.cohorts) - 1, -1, -1):
                cohort = cell.cohorts[idx]
                if allowed_species is not None and cohort.species_id not in allowed_species:
                    continue
                if cohort.age < min_age:
                    continue
                if max_age is not None and cohort.age > max_age:
                    continue
                species = self.species[cohort.species_id]
                age_scalar = cohort.age / max(species.age_max_yr, 1)
                susceptibility = 0.55 + 0.35 * age_scalar + 0.2 * max(0.0, 1.0 - cohort.vigor)
                if allowed_species is None and species.pft.startswith("pioneer"):
                    susceptibility += 0.1
                mortality_frac = min(0.98, severity * susceptibility)
                if mortality_frac <= 0.0:
                    continue
                killed = self.mortality_module.apply_cohort_mortality(cell, idx, mortality_frac, species)
                total_killed += killed
                cohort.vigor *= max(0.1, 1.0 - 0.6 * mortality_frac)
            if total_killed <= 0.0:
                continue
            cell.remove_empty_cohorts()
            cell.time_since_disturbance = 0
            cell.disturbance_type_last = DisturbanceType.INSECT_OUTBREAK
            cell.recent_disturbance_severity = max(
                cell.recent_disturbance_severity,
                min(1.0, 0.14 + 0.72 * severity + total_killed / 7000.0),
            )
            cell.regeneration_delay_yr = max(cell.regeneration_delay_yr, 1 + int(round(3.0 * severity)))

    def _apply_custom_event(self, event: SimEvent, year: int) -> None:
        event_params = dict(event.params or {})
        delegate = event_params.pop("delegate_event_type", None)
        if delegate is not None:
            delegate_type = EventType(str(delegate))
            if delegate_type is EventType.CUSTOM:
                raise ValueError("custom events cannot delegate to custom")
            delegated_event = copy.deepcopy(event)
            delegated_event.event_type = delegate_type
            delegated_event.params = event_params
            self._apply_event(delegated_event, year)
            return

        affected_mask = self._resolve_event_mask_or_full(event)
        recognized = False
        if any(key in event_params for key in {"gdd_delta", "precip_delta_mm", "drought_delta", "frost_free_delta"}):
            self._apply_climate_shift_effects(
                affected_mask=affected_mask,
                gdd_delta=float(event_params.get("gdd_delta", 0.0)),
                precip_delta_mm=float(event_params.get("precip_delta_mm", 0.0)),
                drought_delta=float(event_params.get("drought_delta", 0.0)),
                frost_free_delta=int(round(float(event_params.get("frost_free_delta", 0.0)))),
            )
            recognized = True
        if any(key in event_params for key in {"plant_species_id", "plant_species_ids", "plant_biomass_kg_ha", "plant_density_stems_ha"}):
            self._apply_planting_effects(
                affected_mask=affected_mask,
                year=year,
                species_id=event_params.get("plant_species_id"),
                species_ids=event_params.get("plant_species_ids"),
                age=int(event_params.get("plant_age", 0)),
                biomass_kg_ha=float(event_params.get("plant_biomass_kg_ha", 40.0)),
                density_stems_ha=float(event_params.get("plant_density_stems_ha", 160.0)),
                vigor=float(np.clip(event_params.get("plant_vigor", 0.95), 0.0, 1.0)),
            )
            recognized = True
        if "mortality_frac" in event_params:
            mortality_frac = float(np.clip(event_params["mortality_frac"], 0.0, 0.98))
            species_filter = {int(value) for value in event_params.get("species_filter", [])} if event_params.get("species_filter") else None
            min_age = int(event_params.get("min_age", 0))
            max_age = int(event_params["max_age"]) if "max_age" in event_params else None
            rows, cols = np.where(affected_mask)
            for row, col in zip(rows.tolist(), cols.tolist()):
                cell = self.vegetation[row, col]
                total_killed = 0.0
                for idx in range(len(cell.cohorts) - 1, -1, -1):
                    cohort = cell.cohorts[idx]
                    if species_filter is not None and cohort.species_id not in species_filter:
                        continue
                    if cohort.age < min_age:
                        continue
                    if max_age is not None and cohort.age > max_age:
                        continue
                    species = self.species[cohort.species_id]
                    total_killed += self.mortality_module.apply_cohort_mortality(cell, idx, mortality_frac, species)
                if total_killed > 0.0:
                    cell.remove_empty_cohorts()
                    cell.time_since_disturbance = 0
                    cell.disturbance_type_last = DisturbanceType.CUSTOM
                    cell.recent_disturbance_severity = max(
                        cell.recent_disturbance_severity,
                        min(1.0, mortality_frac + total_killed / 7000.0),
                    )
            recognized = True
        if any(key in event_params for key in {"litter_delta_kg_ha", "cwd_delta_kg_ha", "mineral_soil_delta", "mineral_soil_exposed_frac", "recent_disturbance_severity"}):
            rows, cols = np.where(affected_mask)
            for row, col in zip(rows.tolist(), cols.tolist()):
                cell = self.vegetation[row, col]
                if "litter_delta_kg_ha" in event_params:
                    cell.litter_kg_ha = max(0.0, cell.litter_kg_ha + float(event_params["litter_delta_kg_ha"]))
                if "cwd_delta_kg_ha" in event_params:
                    cell.coarse_woody_debris_kg_ha = max(0.0, cell.coarse_woody_debris_kg_ha + float(event_params["cwd_delta_kg_ha"]))
                if "mineral_soil_delta" in event_params:
                    cell.mineral_soil_exposed_frac = float(
                        np.clip(cell.mineral_soil_exposed_frac + float(event_params["mineral_soil_delta"]), 0.0, 1.0)
                    )
                if "mineral_soil_exposed_frac" in event_params:
                    cell.mineral_soil_exposed_frac = float(np.clip(event_params["mineral_soil_exposed_frac"], 0.0, 1.0))
                if "recent_disturbance_severity" in event_params:
                    cell.recent_disturbance_severity = max(
                        cell.recent_disturbance_severity,
                        float(np.clip(event_params["recent_disturbance_severity"], 0.0, 1.0)),
                    )
                cell.disturbance_type_last = DisturbanceType.CUSTOM
            recognized = True
        if not recognized:
            raise ValueError("custom event must define delegate_event_type or recognized effect params")

    def _compute_light_field(self) -> None:
        rows, cols = self.config.shape
        for row in range(rows):
            for col in range(cols):
                cell = self.vegetation[row, col]
                self._cohort_light[row, col] = self.light_module.compute_light(cell, self.species)
                self._ground_light[row, col] = self.light_module.ground_light(cell, self.species)

    def _grow_cohorts(self, year: int) -> None:
        rows, cols = self.config.shape
        for row in range(rows):
            for col in range(cols):
                cell = self.vegetation[row, col]
                light_by_cohort = self._cohort_light[row, col]
                for idx, cohort in enumerate(cell.cohorts):
                    species = self.species[cohort.species_id]
                    available_light = light_by_cohort.get(idx, 1.0)
                    delta_biomass = self.growth_module.grow_cohort(
                        cohort,
                        species,
                        available_light,
                        self.climate,
                        self.soils,
                        row,
                        col,
                    )
                    self.growth_module.update_allometry(cohort, species, delta_biomass)
                    normalized_growth = delta_biomass / max(1.0, species.g_max_cm_yr * 220.0)
                    cohort.vigor = float(np.clip(0.65 * cohort.vigor + 0.35 * normalized_growth, 0.0, 1.0))
        _ = year

    def _apply_mortality(self, year: int) -> None:
        rows, cols = self.config.shape
        for row in range(rows):
            for col in range(cols):
                cell = self.vegetation[row, col]
                if not cell.cohorts:
                    cell.time_since_disturbance += 1
                    continue

                had_major_mortality = False
                total_killed = 0.0
                site_stress = float(self.climate.drought_index[row, col] + self.soils.rock_fraction[row, col])
                gap_turnover = False
                if (
                    self.config.n_cells > 1
                    and cell.total_canopy_cover > 0.65
                    and cell.dominant_height_m > 10.0
                    and cell.mean_age > 18.0
                ):
                    gap_turnover_prob = (
                        0.04
                        + 0.08 * max(0.0, site_stress - 0.35)
                        + 0.08 * max(0.0, cell.total_canopy_cover - 0.65)
                    )
                    gap_turnover = self.rng.uniform("gap_turnover", year, row, col) < gap_turnover_prob
                for idx, cohort in enumerate(list(cell.cohorts)):
                    species = self.species[cohort.species_id]
                    mortality_prob = self.mortality_module.compute_mortality_probability(
                        cohort,
                        species,
                        stress_scalar=self.calibration_globals.mortality_stress_scalar,
                    )
                    mortality_frac = min(0.65, mortality_prob)
                    if site_stress > 0.45 and cohort.crown_cover_frac > 0.3:
                        mortality_frac = min(0.8, mortality_frac + 0.1 * (site_stress - 0.45) / 0.55)
                    if cohort.age > species.maturity_age_yr and cohort.vigor < species.stress_mortality_threshold:
                        mortality_frac = min(0.9, mortality_frac + 0.2)
                    if (
                        cohort.age > 2 * species.maturity_age_yr
                        and site_stress > 0.55
                        and self.rng.uniform("site_gap", year, row, col, cohort.species_id) < 0.06 * site_stress
                    ):
                        mortality_frac = min(0.98, mortality_frac + 0.35)
                    if gap_turnover and cohort.canopy_height_m >= cell.dominant_height_m * 0.85:
                        mortality_frac = min(0.98, max(mortality_frac, 0.62 + 0.25 * site_stress))
                    if self.rng.uniform("mortality", year, row, col, cohort.species_id, cohort.age) < mortality_prob * 0.15:
                        mortality_frac = min(0.98, mortality_frac + 0.45)
                    if mortality_frac <= 0.0:
                        continue
                    killed = self.mortality_module.apply_cohort_mortality(cell, idx, mortality_frac, species)
                    total_killed += killed
                    had_major_mortality = had_major_mortality or killed > 300.0 or gap_turnover

                cell.remove_empty_cohorts()
                if had_major_mortality and self.config.n_cells > 1:
                    if gap_turnover or total_killed > 1000.0:
                        biomass_scalar = 0.4 if gap_turnover else 0.6
                        density_scalar = 0.6 if gap_turnover else 0.75
                        for cohort in cell.cohorts:
                            if cohort.canopy_height_m > 2.0:
                                cohort.biomass_kg_ha *= biomass_scalar
                                cohort.density_stems_ha *= density_scalar
                                cohort.vigor *= 0.9
                                recompute_cohort_structure(cohort, self.species[cohort.species_id])
                        cell.remove_empty_cohorts()
                    cell.time_since_disturbance = 0
                    cell.mineral_soil_exposed_frac = min(1.0, cell.mineral_soil_exposed_frac + 0.2 + 0.08 * float(gap_turnover))
                    cell.recent_disturbance_severity = max(
                        cell.recent_disturbance_severity,
                        min(1.0, 0.2 + total_killed / 3500.0),
                    )
                    cell.regeneration_delay_yr = max(
                        cell.regeneration_delay_yr,
                        5 + 2 * int(gap_turnover) + int(total_killed > 1200.0),
                    )
                else:
                    cell.time_since_disturbance += 1

    def _recruit_new_cohorts(self, year: int) -> None:
        rows, cols = self.config.shape
        terrain_bonus = np.clip(
            (self.terrain.twi - self.terrain.twi.min()) / max(1e-6, float(np.ptp(self.terrain.twi))),
            0.0,
            1.0,
        )
        climate_bonus = 1.0 - self.climate.drought_index
        recruitment_scalar = self._grazing_modifier_grid() * self._river_recruitment_scalar
        disturbance_opening = np.zeros(self.config.shape, dtype=np.float32)
        for row in range(rows):
            for col in range(cols):
                cell = self.vegetation[row, col]
                disturbance_opening[row, col] = np.clip(
                    0.7 * cell.recent_fire_severity
                    + 0.45 * cell.recent_disturbance_severity
                    + 0.08 * cell.regeneration_delay_yr,
                    0.0,
                    1.0,
                )

        for species_id, species in self.species.items():
            local_seed_rain = self.recruitment_module.compute_seed_rain(
                species_id=species_id,
                species=species,
                vegetation_grid=self.vegetation,
                config=self.config,
            )
            immigration = (
                1.25
                + 1.0 * (1.0 - species.shade_tolerance / 5.0)
                + 0.3 * terrain_bonus
                + 0.2 * climate_bonus
            ).astype(np.float32)
            if species.shade_tolerance < 3.0:
                colonization_scalar = 1.0 + disturbance_opening * (2.6 + 1.4 * max(0.0, 1.0 - species.seed_mass_g / 1.5))
                immigration = immigration * colonization_scalar
            else:
                immigration = immigration * np.clip(1.0 - 0.65 * disturbance_opening, 0.2, 1.0)
            seed_rain = local_seed_rain + immigration
            recruits = self.recruitment_module.establish_recruits(
                seed_rain=seed_rain,
                species=species,
                ground_light=self._ground_light,
                terrain=self.terrain,
                soil=self.soils,
                climate=self.climate,
                vegetation_grid=self.vegetation,
                rng=self.rng,
                year=year,
                establishment_scalar=recruitment_scalar,
                moisture_bonus=self._river_moisture_bonus,
                recruitment_base_scalar=self.calibration_globals.recruitment_base_scalar,
                recruitment_disturbance_scalar=self.calibration_globals.recruitment_disturbance_scalar,
            )
            for row, col, cohort in recruits:
                self.vegetation[row, col].add_or_merge_cohort(
                    cohort,
                    age_window=3,
                    species=species,
                )
        for row in range(rows):
            for col in range(cols):
                self.vegetation[row, col].remove_empty_cohorts()

    def _update_fuels(self, year: int) -> None:
        rows, cols = self.config.shape
        for row in range(rows):
            for col in range(cols):
                cell = self.vegetation[row, col]
                canopy_cover = cell.total_canopy_cover
                litter_input = 0.018 * cell.total_biomass_kg_ha
                cell.litter_kg_ha = max(0.0, cell.litter_kg_ha * 0.82 + litter_input)
                cell.coarse_woody_debris_kg_ha = max(0.0, cell.coarse_woody_debris_kg_ha * 0.96)
                exposure_target = 0.07 + 0.58 * (1.0 - canopy_cover)
                cell.mineral_soil_exposed_frac = float(
                    np.clip(0.75 * cell.mineral_soil_exposed_frac + 0.25 * exposure_target, 0.02, 1.0)
                )
                cell.recent_disturbance_severity *= 0.84
                cell.recent_fire_severity *= 0.72
                cell.regeneration_delay_yr = max(0, cell.regeneration_delay_yr - 1)
        _ = year

    def _grazing_modifier_grid(self) -> np.ndarray:
        modifier = np.ones(self.config.shape, dtype=np.float32)
        for row, col in self.grazing_module.active_grazing:
            if 0 <= row < self.config.shape[0] and 0 <= col < self.config.shape[1]:
                modifier[row, col] = self.grazing_module.recruitment_modifier(row, col)
        return modifier

    def _export_engine_state(self) -> Dict[str, object]:
        return {
            "config": copy.deepcopy(self.config),
            "species_table": copy.deepcopy(self.species_table),
            "terrain": copy.deepcopy(self.terrain),
            "soils": copy.deepcopy(self.soils),
            "baseline_climate": copy.deepcopy(self._climate_scenario.baseline),
            "yearly_climate_overrides": copy.deepcopy(self._climate_scenario.yearly_overrides),
            "active_climate_year": self._active_climate_year,
            "event_log": copy.deepcopy(self.event_log),
            "calibration_globals": copy.deepcopy(self.calibration_globals),
            "vegetation": copy.deepcopy(self.vegetation),
            "initial_vegetation": copy.deepcopy(self._initial_vegetation),
            "checkpoints": copy.deepcopy(self.checkpoints),
            "checkpoint_interval": self.checkpoint_interval,
            "history": copy.deepcopy(self.history),
            "start_year": self.start_year,
            "area_burned_ha": self._area_burned_ha,
            "area_harvested_ha": self._area_harvested_ha,
            "area_blown_down_ha": self._area_blown_down_ha,
            "grazing_state": copy.deepcopy(self.grazing_module.active_grazing),
            "river_moisture_bonus": copy.deepcopy(self._river_moisture_bonus),
            "river_recruitment_scalar": copy.deepcopy(self._river_recruitment_scalar),
            "climate_shift_gdd_delta": copy.deepcopy(self._climate_shift_gdd_delta),
            "climate_shift_precip_delta": copy.deepcopy(self._climate_shift_precip_delta),
            "climate_shift_drought_delta": copy.deepcopy(self._climate_shift_drought_delta),
            "climate_shift_frost_free_delta": copy.deepcopy(self._climate_shift_frost_free_delta),
        }

    def _record_year(self, year: int) -> None:
        canopy_cover = self.canopy_cover_grid()
        dominant_height = self.dominant_height_grid()
        mean_age = self.mean_age_grid()
        cell_area_ha = (self.config.cell_size_m**2) / 10000.0
        gap_metrics = PatternMetrics.gap_size_distribution(
            canopy_cover,
            cell_area_ha=cell_area_ha,
        )
        fraction_in_gaps = float(gap_metrics["fraction_in_gaps"])
        n_gaps = int(gap_metrics["n_gaps"])

        total_biomass_kg = 0.0
        species_basal_area: Dict[int, float] = {species_id: 0.0 for species_id in self.species}
        present_species: set[int] = set()
        for row in range(self.config.shape[0]):
            for col in range(self.config.shape[1]):
                cell = self.vegetation[row, col]
                total_biomass_kg += cell.total_biomass_kg_ha * cell_area_ha
                for cohort in cell.cohorts:
                    species_basal_area[cohort.species_id] += cohort.biomass_kg_ha / max(
                        1.0,
                        self.species[cohort.species_id].wood_density_kg_m3 * 8.0,
                    )
                    present_species.add(cohort.species_id)

        self.history.append(
            YearRecord(
                year=year,
                total_biomass_kg=total_biomass_kg,
                mean_canopy_height_m=float(dominant_height.mean()),
                fraction_in_gaps=fraction_in_gaps,
                n_gaps=n_gaps,
                species_basal_area=species_basal_area,
                morans_i_height=PatternMetrics.morans_i(dominant_height),
                morans_i_age=PatternMetrics.morans_i(mean_age),
                area_burned_ha=self._area_burned_ha,
                area_harvested_ha=self._area_harvested_ha,
                area_blown_down_ha=self._area_blown_down_ha,
                n_species_present=len(present_species),
            )
        )

    def _save_checkpoint(self, year: int) -> None:
        self.checkpoints[year] = pickle.dumps(
            {
                "vegetation": copy.deepcopy(self.vegetation),
                "history": copy.deepcopy(self.history),
                "area_burned_ha": self._area_burned_ha,
                "area_harvested_ha": self._area_harvested_ha,
                "area_blown_down_ha": self._area_blown_down_ha,
                "active_climate_year": self._active_climate_year,
                "grazing_state": copy.deepcopy(self.grazing_module.active_grazing),
                "river_moisture_bonus": copy.deepcopy(self._river_moisture_bonus),
                "river_recruitment_scalar": copy.deepcopy(self._river_recruitment_scalar),
                "climate_shift_gdd_delta": copy.deepcopy(self._climate_shift_gdd_delta),
                "climate_shift_precip_delta": copy.deepcopy(self._climate_shift_precip_delta),
                "climate_shift_drought_delta": copy.deepcopy(self._climate_shift_drought_delta),
                "climate_shift_frost_free_delta": copy.deepcopy(self._climate_shift_frost_free_delta),
            }
        )

    def _restore_checkpoint(self, year: int) -> None:
        restored = pickle.loads(self.checkpoints[year])
        self.vegetation = restored["vegetation"]
        self.history = restored["history"]
        self._area_burned_ha = restored.get("area_burned_ha", 0.0)
        self._area_harvested_ha = restored.get("area_harvested_ha", 0.0)
        self._area_blown_down_ha = restored.get("area_blown_down_ha", 0.0)
        self._active_climate_year = restored.get("active_climate_year")
        if self._active_climate_year is not None:
            self.climate = self._climate_scenario.for_year(self._active_climate_year)
        self.grazing_module.active_grazing = copy.deepcopy(restored.get("grazing_state", {}))
        self._river_moisture_bonus = copy.deepcopy(
            restored.get("river_moisture_bonus", np.zeros(self.config.shape, dtype=np.float32))
        )
        self._river_recruitment_scalar = copy.deepcopy(
            restored.get("river_recruitment_scalar", np.ones(self.config.shape, dtype=np.float32))
        )
        self._climate_shift_gdd_delta = copy.deepcopy(
            restored.get("climate_shift_gdd_delta", np.zeros(self.config.shape, dtype=np.float32))
        )
        self._climate_shift_precip_delta = copy.deepcopy(
            restored.get("climate_shift_precip_delta", np.zeros(self.config.shape, dtype=np.float32))
        )
        self._climate_shift_drought_delta = copy.deepcopy(
            restored.get("climate_shift_drought_delta", np.zeros(self.config.shape, dtype=np.float32))
        )
        self._climate_shift_frost_free_delta = copy.deepcopy(
            restored.get("climate_shift_frost_free_delta", np.zeros(self.config.shape, dtype=np.int16))
        )

    def _reset_to_initial(self) -> None:
        self.vegetation = copy.deepcopy(self._initial_vegetation)
        self.grazing_module.active_grazing = {}
        self._river_moisture_bonus = np.zeros(self.config.shape, dtype=np.float32)
        self._river_recruitment_scalar = np.ones(self.config.shape, dtype=np.float32)
        self._climate_shift_gdd_delta = np.zeros(self.config.shape, dtype=np.float32)
        self._climate_shift_precip_delta = np.zeros(self.config.shape, dtype=np.float32)
        self._climate_shift_drought_delta = np.zeros(self.config.shape, dtype=np.float32)
        self._climate_shift_frost_free_delta = np.zeros(self.config.shape, dtype=np.int16)
        self._active_climate_year = None
        self.climate = self._climate_scenario.for_year(0)
        self._reset_year_counters()

    def canopy_cover_grid(self) -> np.ndarray:
        canopy = np.zeros(self.config.shape, dtype=np.float32)
        for row in range(self.config.shape[0]):
            for col in range(self.config.shape[1]):
                canopy[row, col] = self.vegetation[row, col].total_canopy_cover
        return canopy

    def dominant_height_grid(self) -> np.ndarray:
        heights = np.zeros(self.config.shape, dtype=np.float32)
        for row in range(self.config.shape[0]):
            for col in range(self.config.shape[1]):
                heights[row, col] = self.vegetation[row, col].dominant_height_m
        return heights

    def mean_age_grid(self) -> np.ndarray:
        ages = np.zeros(self.config.shape, dtype=np.float32)
        for row in range(self.config.shape[0]):
            for col in range(self.config.shape[1]):
                ages[row, col] = self.vegetation[row, col].mean_age
        return ages
