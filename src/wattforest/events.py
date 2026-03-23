"""Event-sourced simulation timeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import copy
import hashlib
import json
from typing import Dict, List, Optional, Tuple

import numpy as np


class EventType(Enum):
    FIRE_IGNITION = "fire_ignition"
    PRESCRIBED_BURN = "prescribed_burn"
    WINDSTORM = "windstorm"
    HARVEST = "harvest"
    GRAZING_START = "grazing_start"
    GRAZING_END = "grazing_end"
    RIVER_SHIFT = "river_shift"
    FLOOD = "flood"
    CLIMATE_SHIFT = "climate_shift"
    PLANTING = "planting"
    INSECT_OUTBREAK = "insect_outbreak"
    CUSTOM = "custom"


@dataclass
class SimEvent:
    """A single event in the timeline."""

    event_id: str
    event_type: EventType
    year: int
    day_of_year: int = 180
    priority: int = 0
    affected_cells: Optional[np.ndarray] = None
    center_xy: Optional[Tuple[float, float]] = None
    radius_m: Optional[float] = None
    polygon_vertices: Optional[List[Tuple[float, float]]] = None
    params: Dict = field(default_factory=dict)
    branch_id: str = "main"
    created_at: str = ""
    notes: str = ""

    def fingerprint(self) -> str:
        blob = json.dumps(
            {
                "type": self.event_type.value,
                "year": self.year,
                "day": self.day_of_year,
                "params": self.params,
            },
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


@dataclass
class EventLog:
    """The complete ordered event history for a scenario branch."""

    events: List[SimEvent] = field(default_factory=list)
    global_seed: int = 42

    def events_for_year(self, year: int) -> List[SimEvent]:
        return sorted(
            [event for event in self.events if event.year == year],
            key=lambda event: (event.day_of_year, event.priority),
        )

    def earliest_affected_year(self, after_year: int = -999999) -> int:
        years = [event.year for event in self.events if event.year > after_year]
        return min(years) if years else after_year

    def branch(self, new_branch_id: str) -> "EventLog":
        branched = copy.deepcopy(self)
        for event in branched.events:
            event.branch_id = new_branch_id
        return branched
