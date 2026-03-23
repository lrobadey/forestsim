"""Workspace-backed service layer for the Phase 5 API."""

from __future__ import annotations

import copy
import json
import math
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

import numpy as np

from ..config import LandscapeConfig
from ..engine import WattForestEngine
from ..events import EventLog, EventType, SimEvent
from ..io.export import export_geotiff, export_netcdf
from ..io.geospatial import cell_center_xy
from ..metrics import YearRecord
from .schemas import SUPPORTED_EVENT_TYPES, SUPPORTED_LAYERS, utc_now_iso


@dataclass(frozen=True)
class BranchRecord:
    branch_id: str
    name: str
    source_branch_id: str | None
    created_at: str
    updated_at: str
    revision: int
    start_year: int
    latest_replay_year: int | None
    latest_event_year: int | None
    event_count: int
    global_seed: int
    base_checkpoint_path: str
    workspace_path: str
    events_path: str
    replay_cache_dir: str

    def to_dict(self) -> dict[str, object]:
        return {
            "branch_id": self.branch_id,
            "name": self.name,
            "source_branch_id": self.source_branch_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision": self.revision,
            "start_year": self.start_year,
            "latest_replay_year": self.latest_replay_year,
            "latest_event_year": self.latest_event_year,
            "event_count": self.event_count,
            "workspace_path": self.workspace_path,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "BranchRecord":
        latest_replay_year = payload.get("latest_replay_year")
        latest_event_year = payload.get("latest_event_year")
        return cls(
            branch_id=str(payload["branch_id"]),
            name=str(payload["name"]),
            source_branch_id=payload.get("source_branch_id") and str(payload["source_branch_id"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            revision=int(payload["revision"]),
            start_year=int(payload["start_year"]),
            latest_replay_year=int(latest_replay_year) if latest_replay_year is not None else None,
            latest_event_year=int(latest_event_year) if latest_event_year is not None else None,
            event_count=int(payload["event_count"]),
            global_seed=int(payload["global_seed"]),
            base_checkpoint_path=str(payload["base_checkpoint_path"]),
            workspace_path=str(payload["workspace_path"]),
            events_path=str(payload["events_path"]),
            replay_cache_dir=str(payload["replay_cache_dir"]),
        )


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _json_load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def _event_to_payload(event: SimEvent) -> dict[str, object]:
    affected_cells = None
    if event.affected_cells is not None:
        array = np.asarray(event.affected_cells)
        if array.ndim == 2 and array.dtype == bool:
            rows, cols = np.where(array)
            affected_cells = [[int(row), int(col)] for row, col in zip(rows.tolist(), cols.tolist())]
        else:
            affected_cells = [[int(row), int(col)] for row, col in np.asarray(array).reshape(-1, 2)]

    payload: dict[str, object] = {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "year": int(event.year),
        "day_of_year": int(event.day_of_year),
        "priority": int(event.priority),
        "params": copy.deepcopy(event.params),
        "branch_id": event.branch_id,
        "created_at": event.created_at,
        "notes": event.notes,
    }
    if affected_cells is not None:
        payload["affected_cells"] = affected_cells
    if event.center_xy is not None:
        payload["center_xy"] = [float(event.center_xy[0]), float(event.center_xy[1])]
    if event.radius_m is not None:
        payload["radius_m"] = float(event.radius_m)
    if event.polygon_vertices is not None:
        payload["polygon_vertices"] = [[float(x), float(y)] for x, y in event.polygon_vertices]
    return payload


def _payload_to_event(payload: Mapping[str, object], config: LandscapeConfig, *, branch_id: str) -> SimEvent:
    event_type_value = payload["event_type"]
    if isinstance(event_type_value, EventType):
        event_type_value = event_type_value.value
    event_type = EventType(str(event_type_value))
    event = SimEvent(
        event_id=str(payload.get("event_id") or uuid4().hex),
        event_type=event_type,
        year=int(payload["year"]),
        day_of_year=int(payload.get("day_of_year", 180)),
        priority=int(payload.get("priority", 0)),
        affected_cells=None,
        center_xy=tuple(float(value) for value in payload["center_xy"]) if payload.get("center_xy") is not None else None,
        radius_m=float(payload["radius_m"]) if payload.get("radius_m") is not None else None,
        polygon_vertices=[
            (float(x), float(y))
            for x, y in payload.get("polygon_vertices", [])
        ]
        if payload.get("polygon_vertices") is not None
        else None,
        params=dict(payload.get("params", {})),
        branch_id=branch_id,
        created_at=str(payload.get("created_at") or utc_now_iso()),
        notes=str(payload.get("notes", "")),
    )
    if payload.get("affected_cells") is not None:
        event.affected_cells = _mask_from_payload(payload["affected_cells"], config)
    _validate_event_geometry(event)
    if event.event_type not in SUPPORTED_EVENT_TYPES:
        raise NotImplementedError(f"Unsupported event type: {event.event_type.value}")
    return event


def _mask_from_payload(payload: object, config: LandscapeConfig) -> np.ndarray:
    mask = np.zeros(config.shape, dtype=bool)
    if isinstance(payload, np.ndarray):
        array = payload
    else:
        array = np.asarray(payload)

    if array.ndim == 2 and array.shape == config.shape and array.dtype == bool:
        return array.astype(bool, copy=True)

    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, (list, tuple, np.ndarray)) and len(first) == 2:
            for row, col in payload:
                r = int(row)
                c = int(col)
                if 0 <= r < config.shape[0] and 0 <= c < config.shape[1]:
                    mask[r, c] = True
            return mask
        if len(payload) == config.shape[0] and all(isinstance(row, (list, tuple, np.ndarray)) for row in payload):
            candidate = np.asarray(payload, dtype=bool)
            if candidate.shape == config.shape:
                return candidate.astype(bool, copy=True)

    if array.ndim == 2 and array.shape[-1] == 2:
        for row, col in array.reshape(-1, 2):
            r = int(row)
            c = int(col)
            if 0 <= r < config.shape[0] and 0 <= c < config.shape[1]:
                mask[r, c] = True
        return mask
    raise ValueError(f"affected_cells must be a mask or a list of row/col coordinates; got {type(payload).__name__}: {payload!r}")


def _polygon_vertices_to_mask(vertices: Iterable[tuple[float, float]], config: LandscapeConfig) -> np.ndarray:
    vertices = list(vertices)
    if len(vertices) < 3:
        raise ValueError("polygon_vertices must contain at least three points")
    xx, yy = cell_center_xy(config)
    x = xx.ravel()
    y = yy.ravel()
    verts = np.asarray(vertices, dtype=float)
    inside = np.zeros_like(x, dtype=bool)
    x0, y0 = verts[-1]
    for x1, y1 in verts:
        denom = y1 - y0
        denom = denom if abs(denom) > 1e-12 else 1e-12
        intersects = ((y0 > y) != (y1 > y)) & (x < ((x1 - x0) * (y - y0) / denom) + x0)
        inside ^= intersects
        x0, y0 = x1, y1
    return inside.reshape(config.shape)


def _validate_event_geometry(event: SimEvent) -> None:
    geometry_count = 0
    if event.affected_cells is not None:
        geometry_count += 1
    if event.center_xy is not None or event.radius_m is not None:
        if event.center_xy is None or event.radius_m is None:
            raise ValueError("circle events require center_xy and radius_m together")
        geometry_count += 1
    if event.polygon_vertices is not None:
        geometry_count += 1
    if geometry_count == 0 and event.event_type in {EventType.CLIMATE_SHIFT, EventType.CUSTOM}:
        return
    if geometry_count != 1:
        raise ValueError("events must define exactly one geometry: mask, circle, or polygon")


def _event_from_payload(payload: Mapping[str, object], config: LandscapeConfig, *, branch_id: str) -> SimEvent:
    return _payload_to_event(payload, config, branch_id=branch_id)


def _event_payload_from_event(event: SimEvent) -> dict[str, object]:
    return _event_to_payload(event)


def _dominant_pft_grid(engine: WattForestEngine) -> np.ndarray:
    pft_to_index = {pft: idx for idx, pft in enumerate(sorted({species.pft for species in engine.species_table}))}
    grid = np.full(engine.config.shape, -1, dtype=np.int16)
    for row in range(engine.config.shape[0]):
        for col in range(engine.config.shape[1]):
            cell = engine.vegetation[row, col]
            if not cell.cohorts:
                continue
            biomass_by_pft: dict[str, float] = {}
            for cohort in cell.cohorts:
                pft = engine.species[cohort.species_id].pft
                biomass_by_pft[pft] = biomass_by_pft.get(pft, 0.0) + float(cohort.biomass_kg_ha)
            if biomass_by_pft:
                dominant_pft = max(sorted(biomass_by_pft), key=lambda key: biomass_by_pft[key])
                grid[row, col] = pft_to_index[dominant_pft]
    return grid


def _layer_grid(engine: WattForestEngine, layer: str) -> np.ndarray:
    if layer == "canopy_height":
        return engine.dominant_height_grid().astype(np.float32)
    if layer == "dominant_pft":
        return _dominant_pft_grid(engine)
    if layer == "mean_age":
        return engine.mean_age_grid().astype(np.float32)
    if layer == "gap_mask":
        return (engine.canopy_cover_grid() < 0.3).astype(np.uint8)
    if layer == "disturbance_type_last":
        return np.asarray([[int(cell.disturbance_type_last) for cell in row] for row in engine.vegetation], dtype=np.int16)
    if layer == "recent_fire_severity":
        return np.asarray([[float(cell.recent_fire_severity) for cell in row] for row in engine.vegetation], dtype=np.float32)
    raise KeyError(layer)


def _layer_metadata(engine: WattForestEngine, layer: str) -> dict[str, object]:
    if layer != "dominant_pft":
        return {}
    pfts = sorted({species.pft for species in engine.species_table})
    return {"pft_legend": json.dumps({index: pft for index, pft in enumerate(pfts)}, sort_keys=True)}


def _year_record_to_dict(record: YearRecord) -> dict[str, object]:
    return {
        "year": record.year,
        "total_biomass_kg": record.total_biomass_kg,
        "mean_canopy_height_m": record.mean_canopy_height_m,
        "fraction_in_gaps": record.fraction_in_gaps,
        "n_gaps": record.n_gaps,
        "species_basal_area": dict(record.species_basal_area),
        "morans_i_height": record.morans_i_height,
        "morans_i_age": record.morans_i_age,
        "area_burned_ha": record.area_burned_ha,
        "area_harvested_ha": record.area_harvested_ha,
        "area_blown_down_ha": record.area_blown_down_ha,
        "n_species_present": record.n_species_present,
    }


def _history_series(history: list[YearRecord], config: LandscapeConfig) -> list[dict[str, float | int]]:
    cell_area_ha = (config.cell_size_m**2) / 10000.0
    total_area_ha = config.n_cells * cell_area_ha
    max_biomass = max((record.total_biomass_kg for record in history), default=0.0)
    series: list[dict[str, float | int]] = []
    for record in history:
        mean_gap_size_ha = 0.0
        if record.n_gaps > 0:
            mean_gap_size_ha = (record.fraction_in_gaps * total_area_ha) / record.n_gaps
        biomass_shape = 0.0 if max_biomass <= 0.0 else record.total_biomass_kg / max_biomass
        series.append(
            {
                "year": record.year,
                "mean_gap_fraction": float(record.fraction_in_gaps),
                "mean_gap_size_ha": float(mean_gap_size_ha),
                "morans_i_canopy_height": float(record.morans_i_height),
                "species_richness": int(record.n_species_present),
                "biomass_trajectory_shape": float(biomass_shape),
            }
        )
    return series


def _recent_fire_severity_max(engine: WattForestEngine) -> float:
    recent_fire = np.asarray([[float(cell.recent_fire_severity) for cell in row] for row in engine.vegetation], dtype=np.float32)
    return float(np.max(recent_fire)) if recent_fire.size else 0.0


def _resize_nearest(array: np.ndarray, height: int = 256, width: int = 256) -> np.ndarray:
    if array.size == 0:
        return np.zeros((height, width), dtype=array.dtype)
    row_idx = np.linspace(0, array.shape[0] - 1, height).round().astype(int)
    col_idx = np.linspace(0, array.shape[1] - 1, width).round().astype(int)
    return array[row_idx[:, None], col_idx[None, :]]


def _rgba_from_layer(layer: str, array: np.ndarray) -> np.ndarray:
    values = np.asarray(array)
    if layer == "gap_mask":
        mask = values.astype(bool)
        rgba = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
        rgba[..., :3] = np.where(mask[..., None], np.array([235, 178, 77], dtype=np.uint8), np.array([24, 34, 38], dtype=np.uint8))
        rgba[..., 3] = 255
        return rgba

    if values.dtype.kind in {"i", "u", "b"} or layer in {"dominant_pft", "disturbance_type_last"}:
        categories = values.astype(np.int32, copy=False)
        palette = np.array(
            [
                [35, 41, 52, 255],
                [72, 122, 67, 255],
                [140, 96, 56, 255],
                [62, 115, 173, 255],
                [203, 121, 54, 255],
                [163, 71, 102, 255],
                [88, 171, 176, 255],
                [193, 201, 79, 255],
            ],
            dtype=np.uint8,
        )
        rgba = np.zeros(categories.shape + (4,), dtype=np.uint8)
        flat = categories.ravel()
        mapped = np.empty((flat.size, 4), dtype=np.uint8)
        for index, value in enumerate(flat.tolist()):
            if value < 0:
                mapped[index] = np.array([18, 24, 28, 0], dtype=np.uint8)
            else:
                mapped[index] = palette[int(value) % len(palette)]
        rgba[:] = mapped.reshape(categories.shape + (4,))
        return rgba

    numeric = values.astype(np.float32, copy=False)
    valid = np.isfinite(numeric)
    if not np.any(valid):
        normalized = np.zeros_like(numeric, dtype=np.float32)
    else:
        minimum = float(np.nanmin(numeric))
        maximum = float(np.nanmax(numeric))
        if math.isclose(minimum, maximum):
            normalized = np.full_like(numeric, 0.5, dtype=np.float32)
        else:
            normalized = (numeric - minimum) / max(maximum - minimum, 1e-9)
            normalized = np.clip(normalized, 0.0, 1.0)
    rgba = np.zeros(numeric.shape + (4,), dtype=np.uint8)
    rgba[..., 0] = np.rint(24 + normalized * 170).astype(np.uint8)
    rgba[..., 1] = np.rint(54 + normalized * 120).astype(np.uint8)
    rgba[..., 2] = np.rint(34 + normalized * 60).astype(np.uint8)
    rgba[..., 3] = 255
    return rgba


def _encode_png(rgba: np.ndarray) -> bytes:
    if rgba.ndim != 3 or rgba.shape[-1] != 4:
        raise ValueError("PNG encoder requires RGBA input")
    height, width, _ = rgba.shape
    raw = bytearray()
    for row in rgba:
        raw.append(0)
        raw.extend(np.asarray(row, dtype=np.uint8).tobytes(order="C"))
    compressed = zlib.compress(bytes(raw), level=6)

    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def _tile_png_bytes(array: np.ndarray, layer: str, z: int, x: int, y: int) -> bytes:
    raster = np.flipud(np.asarray(array))
    if raster.ndim != 2:
        raise ValueError("Tile extraction requires a 2D layer")
    tiles_per_axis = 1 << max(0, int(z))
    if not (0 <= x < tiles_per_axis and 0 <= y < tiles_per_axis):
        raise ValueError("tile coordinates out of range")
    row_start = int(math.floor(y * raster.shape[0] / tiles_per_axis))
    row_end = int(math.floor((y + 1) * raster.shape[0] / tiles_per_axis))
    col_start = int(math.floor(x * raster.shape[1] / tiles_per_axis))
    col_end = int(math.floor((x + 1) * raster.shape[1] / tiles_per_axis))
    window = raster[row_start:max(row_start + 1, row_end), col_start:max(col_start + 1, col_end)]
    rgba = _rgba_from_layer(layer, _resize_nearest(window))
    return _encode_png(rgba)


class BranchRepository:
    """Persist branch state, replay caches, and the baseline checkpoint."""

    def __init__(
        self,
        workspace_root: str | Path,
        base_engine: WattForestEngine,
        *,
        start_year: int = 0,
        main_branch_name: str = "main",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.branches_root = self.workspace_root / "branches"
        self.branches_root.mkdir(parents=True, exist_ok=True)
        self.base_checkpoint_path = self.workspace_root / "baseline_engine.pkl"
        if not self.base_checkpoint_path.exists():
            base_engine.save_checkpoint(self.base_checkpoint_path)
        self._base_engine_config = base_engine.config
        self.base_global_seed = int(base_engine.event_log.global_seed)
        self.start_year = int(start_year)
        self._engine_cache: dict[tuple[str, int, int], WattForestEngine] = {}
        self._bootstrap_main_branch(main_branch_name)

    def _bootstrap_main_branch(self, name: str) -> None:
        if (self.branches_root / "main" / "branch.json").exists():
            return
        self._write_branch_record(
            BranchRecord(
                branch_id="main",
                name=name,
                source_branch_id=None,
                created_at=utc_now_iso(),
                updated_at=utc_now_iso(),
                revision=0,
                start_year=self.start_year,
                latest_replay_year=None,
                latest_event_year=None,
                event_count=0,
                global_seed=self.base_global_seed,
                base_checkpoint_path=str(self.base_checkpoint_path),
                workspace_path=str(self.branches_root / "main"),
                events_path=str(self.branches_root / "main" / "events.json"),
                replay_cache_dir=str(self.branches_root / "main" / "replay_cache"),
            )
        )
        self._write_events_file("main", EventLog(events=[], global_seed=self.base_global_seed))

    def _branch_dir(self, branch_id: str) -> Path:
        return self.branches_root / branch_id

    def _branch_path(self, branch_id: str) -> Path:
        return self._branch_dir(branch_id) / "branch.json"

    def _events_path(self, branch_id: str) -> Path:
        return self._branch_dir(branch_id) / "events.json"

    def _replay_cache_dir(self, branch_id: str) -> Path:
        return self._branch_dir(branch_id) / "replay_cache"

    def _load_branch_record(self, branch_id: str) -> BranchRecord:
        path = self._branch_path(branch_id)
        if not path.exists():
            raise KeyError(branch_id)
        return BranchRecord.from_dict(_json_load(path))

    def _write_branch_record(self, record: BranchRecord) -> None:
        branch_dir = self._branch_dir(record.branch_id)
        branch_dir.mkdir(parents=True, exist_ok=True)
        _json_dump(branch_dir / "branch.json", record.to_dict() | {
            "global_seed": record.global_seed,
            "base_checkpoint_path": record.base_checkpoint_path,
            "events_path": record.events_path,
            "replay_cache_dir": record.replay_cache_dir,
        })

    def _load_events(self, branch_id: str) -> EventLog:
        payload = _json_load(self._events_path(branch_id))
        events = [self._load_event(event_payload, branch_id) for event_payload in payload.get("events", [])]
        return EventLog(events=events, global_seed=int(payload.get("global_seed", self.base_global_seed)))

    def _write_events_file(self, branch_id: str, event_log: EventLog) -> None:
        _json_dump(
            self._events_path(branch_id),
            {
                "global_seed": int(event_log.global_seed),
                "events": [_event_to_payload(event) for event in event_log.events],
            },
        )

    def _load_event(self, payload: Mapping[str, object], branch_id: str) -> SimEvent:
        event = _event_from_payload(payload, self.base_engine_config, branch_id=branch_id)
        return event

    @property
    def base_engine_config(self) -> LandscapeConfig:
        return self._base_engine_config

    def _current_year(self, record: BranchRecord) -> int:
        if record.latest_replay_year is not None:
            return int(record.latest_replay_year)
        if record.latest_event_year is not None:
            return int(record.latest_event_year)
        return int(record.start_year)

    def _layers_payload(self) -> list[str]:
        return [
            "canopy_height",
            "dominant_pft",
            "mean_age",
            "gap_mask",
            "disturbance_type_last",
            "recent_fire_severity",
        ]

    def _branch_metrics_payload(
        self,
        record: BranchRecord,
        engine: WattForestEngine,
        event_log: EventLog,
    ) -> dict[str, object]:
        latest_snapshot = _year_record_to_dict(engine.history[-1]) if engine.history else {}
        return {
            "latest_year": self._current_year(record),
            "series": _history_series(engine.history, engine.config),
            "endpoint_snapshots": {
                "canopy_height_mean": float(latest_snapshot.get("mean_canopy_height_m", 0.0)),
                "recent_fire_severity_max": _recent_fire_severity_max(engine),
                "event_count": len(event_log.events),
            },
            "latest_snapshot": latest_snapshot,
            "history": self._history_payload(engine),
        }

    def _branch_payload(self, branch_id: str, *, include_layers: bool = False) -> dict[str, object]:
        record = self._load_branch_record(branch_id)
        event_log = self._load_events(branch_id)
        target_year = self._current_year(record)
        record, engine, _ = self.replay_branch(branch_id, target_year)
        metrics = self._branch_metrics_payload(record, engine, event_log)
        payload: dict[str, object] = {
            "branch_id": record.branch_id,
            "name": record.name,
            "source_branch_id": record.source_branch_id,
            "workspace_path": record.workspace_path,
            "start_year": record.start_year,
            "current_year": metrics["latest_year"],
            "event_count": len(event_log.events),
            "updated_at": record.updated_at,
            "extent_m": [float(self.base_engine_config.extent_m[0]), float(self.base_engine_config.extent_m[1])],
            "origin_xy": [float(self.base_engine_config.origin_utm[0]), float(self.base_engine_config.origin_utm[1])],
            "cell_size_m": float(self.base_engine_config.cell_size_m),
            "metrics": metrics,
        }
        if include_layers:
            payload["layers"] = self._layers_payload()
            payload["description"] = "Workspace-backed scenario branch"
        return payload

    def list_branches(self) -> list[BranchRecord]:
        return [self._load_branch_record(path.parent.name) for path in sorted(self.branches_root.glob("*/branch.json"))]

    def get_branch(self, branch_id: str) -> BranchRecord:
        return self._load_branch_record(branch_id)

    def create_branch(self, source_branch_id: str, name: str | None = None) -> BranchRecord:
        source = self._load_branch_record(source_branch_id)
        branch_id = uuid4().hex[:12]
        branch_dir = self._branch_dir(branch_id)
        branch_dir.mkdir(parents=True, exist_ok=False)
        if self._branch_path(branch_id).exists():
            raise ValueError(f"Branch already exists: {branch_id}")
        events_payload = _json_load(self._events_path(source_branch_id))
        _json_dump(self._events_path(branch_id), events_payload)
        record = BranchRecord(
            branch_id=branch_id,
            name=name or f"{source.name}-copy",
            source_branch_id=source.branch_id,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            revision=source.revision,
            start_year=source.start_year,
            latest_replay_year=source.latest_replay_year,
            latest_event_year=source.latest_event_year,
            event_count=source.event_count,
            global_seed=source.global_seed,
            base_checkpoint_path=source.base_checkpoint_path,
            workspace_path=str(branch_dir),
            events_path=str(self._events_path(branch_id)),
            replay_cache_dir=str(self._replay_cache_dir(branch_id)),
        )
        self._write_branch_record(record)
        return record

    def list_events(self, branch_id: str) -> list[dict[str, object]]:
        record = self._load_branch_record(branch_id)
        event_log = self._load_events(branch_id)
        return [_event_to_payload(event) | {"branch_revision": record.revision} for event in event_log.events]

    def _save_branch_state(self, record: BranchRecord, event_log: EventLog) -> BranchRecord:
        latest_event_year = max((event.year for event in event_log.events), default=None)
        updated = BranchRecord(
            branch_id=record.branch_id,
            name=record.name,
            source_branch_id=record.source_branch_id,
            created_at=record.created_at,
            updated_at=utc_now_iso(),
            revision=record.revision,
            start_year=record.start_year,
            latest_replay_year=record.latest_replay_year,
            latest_event_year=latest_event_year,
            event_count=len(event_log.events),
            global_seed=event_log.global_seed,
            base_checkpoint_path=record.base_checkpoint_path,
            workspace_path=record.workspace_path,
            events_path=record.events_path,
            replay_cache_dir=record.replay_cache_dir,
        )
        self._write_branch_record(updated)
        self._write_events_file(record.branch_id, event_log)
        return updated

    def _invalidate_cache(self, branch_id: str, revision: int) -> None:
        self._engine_cache = {
            key: value for key, value in self._engine_cache.items() if key[0] != branch_id or key[1] == revision
        }

    def _build_branch_engine(self, record: BranchRecord, event_log: EventLog, year: int) -> WattForestEngine:
        engine = WattForestEngine.load_checkpoint(record.base_checkpoint_path)
        engine.event_log = EventLog(events=event_log.events, global_seed=event_log.global_seed)
        engine.start_year = record.start_year
        engine.history = []
        engine.checkpoints = {}
        engine.run(record.start_year, year)
        return engine

    def _cache_path(self, record: BranchRecord, year: int) -> Path:
        cache_dir = Path(record.replay_cache_dir) / f"r{record.revision}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"year-{year}.pkl"

    def replay_branch(self, branch_id: str, year: int | None = None) -> tuple[BranchRecord, WattForestEngine, Path]:
        record = self._load_branch_record(branch_id)
        event_log = self._load_events(branch_id)
        target_year = int(year if year is not None else max((event.year for event in event_log.events), default=record.start_year))
        if target_year < record.start_year:
            raise ValueError(f"Replay year {target_year} precedes branch start_year {record.start_year}")
        cache_path = self._cache_path(record, target_year)
        cache_key = (record.branch_id, record.revision, target_year)
        if cache_key in self._engine_cache:
            if record.latest_replay_year != target_year:
                record = BranchRecord(
                    branch_id=record.branch_id,
                    name=record.name,
                    source_branch_id=record.source_branch_id,
                    created_at=record.created_at,
                    updated_at=utc_now_iso(),
                    revision=record.revision,
                    start_year=record.start_year,
                    latest_replay_year=target_year,
                    latest_event_year=record.latest_event_year,
                    event_count=record.event_count,
                    global_seed=record.global_seed,
                    base_checkpoint_path=record.base_checkpoint_path,
                    workspace_path=record.workspace_path,
                    events_path=record.events_path,
                    replay_cache_dir=record.replay_cache_dir,
                )
                self._write_branch_record(record)
            return record, self._engine_cache[cache_key], cache_path
        if cache_path.exists():
            engine = WattForestEngine.load_checkpoint(cache_path)
            self._engine_cache[cache_key] = engine
            if record.latest_replay_year != target_year:
                record = BranchRecord(
                    branch_id=record.branch_id,
                    name=record.name,
                    source_branch_id=record.source_branch_id,
                    created_at=record.created_at,
                    updated_at=utc_now_iso(),
                    revision=record.revision,
                    start_year=record.start_year,
                    latest_replay_year=target_year,
                    latest_event_year=record.latest_event_year,
                    event_count=record.event_count,
                    global_seed=record.global_seed,
                    base_checkpoint_path=record.base_checkpoint_path,
                    workspace_path=record.workspace_path,
                    events_path=record.events_path,
                    replay_cache_dir=record.replay_cache_dir,
                )
                self._write_branch_record(record)
            return record, engine, cache_path

        engine = self._build_branch_engine(record, event_log, target_year)
        engine.save_checkpoint(cache_path)
        self._engine_cache[cache_key] = engine
        record = BranchRecord(
            branch_id=record.branch_id,
            name=record.name,
            source_branch_id=record.source_branch_id,
            created_at=record.created_at,
            updated_at=utc_now_iso(),
            revision=record.revision,
            start_year=record.start_year,
            latest_replay_year=target_year,
            latest_event_year=record.latest_event_year,
            event_count=record.event_count,
            global_seed=record.global_seed,
            base_checkpoint_path=record.base_checkpoint_path,
            workspace_path=record.workspace_path,
            events_path=record.events_path,
            replay_cache_dir=record.replay_cache_dir,
        )
        self._write_branch_record(record)
        return record, engine, cache_path

    def add_event(self, branch_id: str, payload: Mapping[str, object]) -> SimEvent:
        record = self._load_branch_record(branch_id)
        event_log = self._load_events(branch_id)
        event = _event_from_payload(payload, self.base_engine_config, branch_id=branch_id)
        event.event_id = event.event_id or uuid4().hex
        event.created_at = event.created_at or utc_now_iso()
        event_log.events.append(event)
        record = BranchRecord(
            branch_id=record.branch_id,
            name=record.name,
            source_branch_id=record.source_branch_id,
            created_at=record.created_at,
            updated_at=utc_now_iso(),
            revision=record.revision + 1,
            start_year=record.start_year,
            latest_replay_year=None,
            latest_event_year=max(record.latest_event_year or event.year, event.year),
            event_count=len(event_log.events),
            global_seed=event_log.global_seed,
            base_checkpoint_path=record.base_checkpoint_path,
            workspace_path=record.workspace_path,
            events_path=record.events_path,
            replay_cache_dir=record.replay_cache_dir,
        )
        self._write_events_file(branch_id, event_log)
        self._write_branch_record(record)
        self._invalidate_cache(branch_id, record.revision)
        return event

    def update_event(self, branch_id: str, event_id: str, payload: Mapping[str, object]) -> SimEvent:
        record = self._load_branch_record(branch_id)
        event_log = self._load_events(branch_id)
        updated_event: SimEvent | None = None
        for index, event in enumerate(event_log.events):
            if event.event_id != event_id:
                continue
            payload = dict(payload)
            payload["event_id"] = event_id
            payload["branch_id"] = branch_id
            updated_event = _event_from_payload(payload, self.base_engine_config, branch_id=branch_id)
            event_log.events[index] = updated_event
            break
        if updated_event is None:
            raise KeyError(event_id)
        record = BranchRecord(
            branch_id=record.branch_id,
            name=record.name,
            source_branch_id=record.source_branch_id,
            created_at=record.created_at,
            updated_at=utc_now_iso(),
            revision=record.revision + 1,
            start_year=record.start_year,
            latest_replay_year=None,
            latest_event_year=max((event.year for event in event_log.events), default=None),
            event_count=len(event_log.events),
            global_seed=event_log.global_seed,
            base_checkpoint_path=record.base_checkpoint_path,
            workspace_path=record.workspace_path,
            events_path=record.events_path,
            replay_cache_dir=record.replay_cache_dir,
        )
        self._write_events_file(branch_id, event_log)
        self._write_branch_record(record)
        self._invalidate_cache(branch_id, record.revision)
        return updated_event

    def delete_event(self, branch_id: str, event_id: str) -> None:
        record = self._load_branch_record(branch_id)
        event_log = self._load_events(branch_id)
        original_count = len(event_log.events)
        event_log.events = [event for event in event_log.events if event.event_id != event_id]
        if len(event_log.events) == original_count:
            raise KeyError(event_id)
        record = BranchRecord(
            branch_id=record.branch_id,
            name=record.name,
            source_branch_id=record.source_branch_id,
            created_at=record.created_at,
            updated_at=utc_now_iso(),
            revision=record.revision + 1,
            start_year=record.start_year,
            latest_replay_year=None,
            latest_event_year=max((event.year for event in event_log.events), default=None),
            event_count=len(event_log.events),
            global_seed=event_log.global_seed,
            base_checkpoint_path=record.base_checkpoint_path,
            workspace_path=record.workspace_path,
            events_path=record.events_path,
            replay_cache_dir=record.replay_cache_dir,
        )
        self._write_events_file(branch_id, event_log)
        self._write_branch_record(record)
        self._invalidate_cache(branch_id, record.revision)

    def branch_info(self, branch_id: str) -> BranchRecord:
        return self._load_branch_record(branch_id)

    def _history_payload(self, engine: WattForestEngine) -> list[dict[str, object]]:
        return [_year_record_to_dict(record) for record in engine.history]

    def branch_metrics(self, branch_id: str) -> dict[str, object]:
        record = self._load_branch_record(branch_id)
        target_year = self._current_year(record)
        record, engine, _ = self.replay_branch(branch_id, target_year)
        return self._branch_metrics_payload(record, engine, self._load_events(branch_id))

    def export_layer(
        self,
        *,
        branch_id: str,
        layer: str,
        year: int,
        output_path: str | Path | None = None,
        format_name: str,
    ) -> Path:
        if layer not in SUPPORTED_LAYERS:
            raise KeyError(layer)
        record, engine, _ = self.replay_branch(branch_id, year)
        array = _layer_grid(engine, layer)
        suffix = "tif" if format_name == "geotiff" else "nc"
        out_path = Path(output_path) if output_path is not None else Path(record.workspace_path) / "exports" / f"{layer}-{year}.{suffix}"
        metadata = {"branch_id": branch_id, "layer": layer, "year": int(year)}
        if format_name == "geotiff":
            return export_geotiff(
                out_path,
                array,
                engine.config,
                layer_name=layer,
                year=year,
                branch_id=branch_id,
                metadata=metadata | _layer_metadata(engine, layer),
            )
        if format_name == "netcdf":
            return export_netcdf(
                out_path,
                array,
                engine.config,
                layer_name=layer,
                year=year,
                branch_id=branch_id,
                metadata=metadata | _layer_metadata(engine, layer),
            )
        raise ValueError(f"Unsupported export format: {format_name}")

    def tile_bytes(self, branch_id: str, layer: str, year: int, z: int, x: int, y: int) -> bytes:
        if layer not in SUPPORTED_LAYERS:
            raise KeyError(layer)
        _, engine, _ = self.replay_branch(branch_id, year)
        array = _layer_grid(engine, layer)
        return _tile_png_bytes(array, layer, z, x, y)

    def tile_snapshot(self, branch_id: str, layer: str, year: int, z: int, x: int, y: int) -> dict[str, object]:
        return {
            "branch_id": branch_id,
            "layer": layer,
            "year": year,
            "z": z,
            "x": x,
            "y": y,
        }
