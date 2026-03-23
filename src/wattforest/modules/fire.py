"""Fire spread module scaffold."""

from __future__ import annotations

from typing import List, Tuple

import heapq
import numpy as np

from ..config import LandscapeConfig
from ..terrain import TerrainLayers


class FireModule:
    def __init__(self, config: LandscapeConfig):
        self.cell_size = config.cell_size_m
        self.time_step_hr = 0.5

    def spread_fire(
        self,
        ignition_cells: List[Tuple[int, int]],
        duration_hr: float,
        wind_speed_ms: float,
        wind_dir_deg: float,
        fuel_load: np.ndarray,
        fuel_moisture: np.ndarray,
        terrain: TerrainLayers,
        vegetation_grid: np.ndarray,
        spread_scalar: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        # TODO: Vegetation structure is currently ignored. If this module is
        # meant to be more than an educational scaffold, fold canopy/fuel
        # structure into spread and severity instead of relying only on fuel
        # load, moisture, wind, and slope.
        _ = vegetation_grid
        burned = np.zeros(fuel_load.shape, dtype=bool)
        severity = np.zeros(fuel_load.shape, dtype=np.float32)
        time_of_arrival = np.full(fuel_load.shape, np.inf, dtype=np.float64)
        settled = np.zeros(fuel_load.shape, dtype=bool)
        heap: List[Tuple[float, int, int]] = []
        for row, col in ignition_cells:
            time_of_arrival[row, col] = 0.0
            heapq.heappush(heap, (0.0, row, col))
        wind_dx = wind_speed_ms * np.sin(np.radians(wind_dir_deg))
        wind_dy = wind_speed_ms * np.cos(np.radians(wind_dir_deg))
        neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        diag_dist = self.cell_size * np.sqrt(2.0)
        while heap:
            arrival, row, col = heapq.heappop(heap)
            if arrival > duration_hr:
                break
            if settled[row, col] or arrival > time_of_arrival[row, col]:
                continue
            settled[row, col] = True
            burned[row, col] = True
            for dr, dc in neighbors:
                nr = row + dr
                nc = col + dc
                if nr < 0 or nc < 0 or nr >= fuel_load.shape[0] or nc >= fuel_load.shape[1]:
                    continue
                if settled[nr, nc]:
                    continue
                ros = self._rate_of_spread(
                    row, col, nr, nc, dr, dc, fuel_load, fuel_moisture, terrain, wind_dx, wind_dy, spread_scalar
                )
                if ros <= 0.0:
                    continue
                dist = diag_dist if dr and dc else self.cell_size
                travel_time = dist / (ros * 3600.0)
                next_arrival = arrival + travel_time
                if next_arrival <= duration_hr and next_arrival < time_of_arrival[nr, nc]:
                    time_of_arrival[nr, nc] = next_arrival
                    heapq.heappush(heap, (next_arrival, nr, nc))
        severity[burned] = np.minimum(
            1.0,
            fuel_load[burned] * np.maximum(0.0, 1.0 - 1.6 * fuel_moisture[burned]) / 9000.0,
        )
        return burned, severity

    def _rate_of_spread(
        self,
        r0: int,
        c0: int,
        r1: int,
        c1: int,
        dr: int,
        dc: int,
        fuel_load: np.ndarray,
        fuel_moisture: np.ndarray,
        terrain: TerrainLayers,
        wind_dx: float,
        wind_dy: float,
        spread_scalar: float = 1.0,
    ) -> float:
        # TODO: Replace this heuristic ROS expression with a documented,
        # calibratable approximation to a standard fire spread model and add
        # tests against literature-informed benchmark scenarios.
        fuel = fuel_load[r1, c1]
        moisture = fuel_moisture[r1, c1]
        if fuel < 100.0 or moisture > 0.35:
            return 0.0
        base_ros = spread_scalar * 0.01 * (fuel / 10000.0) ** 0.5
        moisture_scalar = max(0.0, (0.35 - moisture) / 0.35) ** 2
        spread_dir_x = dc
        spread_dir_y = -dr
        wind_alignment = wind_dx * spread_dir_x + wind_dy * spread_dir_y
        wind_scalar = 1.0 + 3.0 * max(0.0, wind_alignment / max(1.0, (wind_dx**2 + wind_dy**2) ** 0.5))
        elev_diff = terrain.elevation[r1, c1] - terrain.elevation[r0, c0]
        slope_scalar = 1.0 + 2.0 * max(0.0, elev_diff / (self.cell_size * 0.5))
        return base_ros * moisture_scalar * wind_scalar * slope_scalar
