"""FastAPI request/response models for the Phase 5 backend."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field

from ..events import EventType

SUPPORTED_EVENT_TYPES = {
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
}

SUPPORTED_LAYERS = {
    "canopy_height",
    "dominant_pft",
    "mean_age",
    "gap_mask",
    "disturbance_type_last",
    "recent_fire_severity",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BranchCreateRequest(BaseModel):
    name: str | None = None
    source_branch_id: str = "main"


class BranchEventPayload(BaseModel):
    event_type: str
    year: int
    day_of_year: int = 180
    priority: int = 0
    affected_cells: list[list[int]] | None = None
    center_xy: tuple[float, float] | None = None
    radius_m: float | None = None
    polygon_vertices: list[tuple[float, float]] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    created_at: str = ""
    event_id: str | None = None


class ReplayRequest(BaseModel):
    year: int | None = Field(default=None, validation_alias=AliasChoices("year", "from_year"))


class ExportRequest(BaseModel):
    branch_id: str
    year: int
    layer: str
    output_path: str | None = None


class BranchInfo(BaseModel):
    branch_id: str
    name: str
    source_branch_id: str | None = None
    created_at: str
    updated_at: str
    revision: int
    start_year: int
    latest_replay_year: int | None = None
    latest_event_year: int | None = None
    event_count: int
    workspace_path: str


class TileSnapshot(BaseModel):
    branch_id: str
    layer: str
    year: int
    z: int
    x: int
    y: int
    path: str | None = None


class ReplayResponse(BaseModel):
    branch_id: str
    year: int
    cache_path: str
    latest_snapshot: dict[str, Any]


class MetricsResponse(BaseModel):
    branch_id: str
    replay_year: int
    history: list[dict[str, Any]]
    latest_snapshot: dict[str, Any]
