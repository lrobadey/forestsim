"""Local MTBS import for Phase 3 disturbance history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from ..config import LandscapeConfig
from ..events import EventType, SimEvent
from .geospatial import rasterize_mask, read_vector_layer


@dataclass
class MtbsImportResult:
    events: list[SimEvent]
    pre_start_fire_year: np.ndarray


def _resolve_year_column(columns: list[str]) -> str:
    lowered = {column.lower(): column for column in columns}
    for candidate in ("year", "fire_year", "ig_year", "fireyear", "incidentyear"):
        if candidate in lowered:
            return lowered[candidate]
    raise ValueError("MTBS layer requires a year field")


def _optional_date_column(columns: list[str]) -> str | None:
    lowered = {column.lower(): column for column in columns}
    for candidate in ("ig_date", "fire_date", "burnbnddt", "incident_date"):
        if candidate in lowered:
            return lowered[candidate]
    return None


def _date_to_day_of_year(value) -> int:
    if value is None or value == "":
        return 220
    if hasattr(value, "timetuple"):
        return int(value.timetuple().tm_yday)
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return int(datetime.strptime(text, fmt).timetuple().tm_yday)
        except ValueError:
            continue
    return 220


def _severity_from_row(row) -> float:
    for key in ("severity", "burn_severity", "severity_scalar"):
        if key in row and row[key] is not None:
            return float(np.clip(row[key], 0.05, 1.0))
    return 0.65


def load_mtbs_events(mtbs_path: str | Path, config: LandscapeConfig, start_year: int) -> MtbsImportResult:
    """Load local MTBS perimeters into event replay entries and pre-start seeding."""

    mtbs = read_vector_layer(mtbs_path, config.epsg)
    year_column = _resolve_year_column(list(mtbs.columns))
    date_column = _optional_date_column(list(mtbs.columns))

    events: list[SimEvent] = []
    pre_start_fire_year = np.full(config.shape, -1, dtype=np.int16)
    mtbs = mtbs.sort_values(year_column, kind="mergesort").reset_index(drop=True)

    for index, row in mtbs.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue
        year = int(row[year_column])
        mask = rasterize_mask([geometry], config, all_touched=True)
        if not np.any(mask):
            continue

        if year < start_year:
            pre_start_fire_year[mask] = np.maximum(pre_start_fire_year[mask], year)
            continue

        day_of_year = _date_to_day_of_year(row[date_column]) if date_column is not None else 220
        severity = _severity_from_row(row)
        events.append(
            SimEvent(
                event_id=f"mtbs-{year}-{index}",
                event_type=EventType.FIRE_IGNITION,
                year=year,
                day_of_year=day_of_year,
                priority=-10,
                affected_cells=mask,
                params={
                    "historical_footprint": True,
                    "severity": severity,
                    "source": "mtbs",
                },
                notes="Imported from local MTBS perimeter history",
            )
        )

    return MtbsImportResult(events=events, pre_start_fire_year=pre_start_fire_year)
