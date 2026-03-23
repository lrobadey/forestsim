import heapq

import numpy as np

from wattforest.config import LandscapeConfig
from wattforest.modules.fire import FireModule
from wattforest.state import CellVegetation
from wattforest.terrain import TerrainLayers, _aspect_from_gradient


def _empty_vegetation(config: LandscapeConfig) -> np.ndarray:
    vegetation = np.empty(config.shape, dtype=object)
    for row in range(config.shape[0]):
        for col in range(config.shape[1]):
            vegetation[row, col] = CellVegetation()
    return vegetation


def _flat_terrain(config: LandscapeConfig) -> TerrainLayers:
    return TerrainLayers(
        elevation=np.zeros(config.shape),
        slope=np.zeros(config.shape),
        aspect=np.zeros(config.shape),
        twi=np.zeros(config.shape),
        flow_accumulation=np.zeros(config.shape),
        curvature=np.zeros(config.shape),
    )


def _spread_fire_first_enqueue(
    module: FireModule,
    ignition_cells: list[tuple[int, int]],
    duration_hr: float,
    wind_speed_ms: float,
    wind_dir_deg: float,
    fuel_load: np.ndarray,
    fuel_moisture: np.ndarray,
    terrain: TerrainLayers,
) -> np.ndarray:
    burned = np.zeros(fuel_load.shape, dtype=bool)
    time_of_arrival = np.full(fuel_load.shape, np.inf, dtype=np.float64)
    heap: list[tuple[float, int, int]] = []
    for row, col in ignition_cells:
        burned[row, col] = True
        time_of_arrival[row, col] = 0.0
        heapq.heappush(heap, (0.0, row, col))

    wind_dx = wind_speed_ms * np.sin(np.radians(wind_dir_deg))
    wind_dy = wind_speed_ms * np.cos(np.radians(wind_dir_deg))
    neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    diag_dist = module.cell_size * np.sqrt(2.0)

    while heap:
        arrival, row, col = heapq.heappop(heap)
        if arrival > duration_hr:
            break
        if arrival > time_of_arrival[row, col]:
            continue
        for dr, dc in neighbors:
            nr = row + dr
            nc = col + dc
            if nr < 0 or nc < 0 or nr >= fuel_load.shape[0] or nc >= fuel_load.shape[1]:
                continue
            if burned[nr, nc]:
                continue
            ros = module._rate_of_spread(
                row,
                col,
                nr,
                nc,
                dr,
                dc,
                fuel_load,
                fuel_moisture,
                terrain,
                wind_dx,
                wind_dy,
            )
            if ros <= 0.0:
                continue
            dist = diag_dist if dr and dc else module.cell_size
            next_arrival = arrival + dist / (ros * 3600.0)
            if next_arrival <= duration_hr and next_arrival < time_of_arrival[nr, nc]:
                time_of_arrival[nr, nc] = next_arrival
                burned[nr, nc] = True
                heapq.heappush(heap, (next_arrival, nr, nc))

    return burned


def test_fire_spread_burns_ignition_cell():
    config = LandscapeConfig((60.0, 60.0), 20.0, (0.0, 0.0), 32610)
    module = FireModule(config)
    fuel = np.full(config.shape, 10000.0)
    moisture = np.full(config.shape, 0.1)
    terrain = _flat_terrain(config)
    vegetation = _empty_vegetation(config)
    burned, _ = module.spread_fire([(1, 1)], 1.0, 5.0, 90.0, fuel, moisture, terrain, vegetation)
    assert burned[1, 1]


def test_fire_spread_is_biased_downwind():
    config = LandscapeConfig((220.0, 220.0), 20.0, (0.0, 0.0), 32610)
    module = FireModule(config)
    fuel = np.full(config.shape, 12000.0)
    moisture = np.full(config.shape, 0.08)
    terrain = _flat_terrain(config)
    vegetation = _empty_vegetation(config)

    ignition = (config.shape[0] // 2, config.shape[1] // 2)
    burned, _ = module.spread_fire([ignition], 1.25, 14.0, 90.0, fuel, moisture, terrain, vegetation)
    burned_cols = np.where(burned)[1]

    assert burned[ignition]
    assert burned_cols.mean() > ignition[1]


def test_fire_spread_responds_to_slope_without_wind():
    config = LandscapeConfig((220.0, 220.0), 20.0, (0.0, 0.0), 32610)
    module = FireModule(config)
    fuel = np.full(config.shape, 12000.0)
    moisture = np.full(config.shape, 0.08)
    vegetation = _empty_vegetation(config)
    flat = _flat_terrain(config)
    elevation = np.tile(np.arange(config.shape[0], dtype=np.float32).reshape(-1, 1), (1, config.shape[1])) * 12.0
    upslope = TerrainLayers(
        elevation=elevation,
        slope=np.full(config.shape, 31.0, dtype=np.float32),
        aspect=np.full(config.shape, 180.0, dtype=np.float32),
        twi=np.zeros(config.shape),
        flow_accumulation=np.zeros(config.shape),
        curvature=np.zeros(config.shape),
    )

    ignition = (config.shape[0] // 2, config.shape[1] // 2)
    flat_burned, _ = module.spread_fire([ignition], 1.75, 0.0, 90.0, fuel, moisture, flat, vegetation)
    slope_burned, _ = module.spread_fire([ignition], 1.75, 0.0, 90.0, fuel, moisture, upslope, vegetation)

    flat_rows = np.where(flat_burned)[0]
    slope_rows = np.where(slope_burned)[0]

    assert slope_burned[ignition]
    assert slope_burned.sum() >= flat_burned.sum()
    assert slope_rows.mean() > flat_rows.mean() + 0.2


def test_fire_spread_prefers_shortest_arrival_paths():
    config = LandscapeConfig((100.0, 120.0), 20.0, (0.0, 0.0), 32610)
    module = FireModule(config)
    vegetation = _empty_vegetation(config)
    ignition = [(config.shape[0] // 2, 1)]

    witness = None
    rng = np.random.default_rng(17)
    for _ in range(300):
        fuel = rng.uniform(8500.0, 18000.0, size=config.shape)
        moisture = rng.uniform(0.03, 0.32, size=config.shape)
        elevation = rng.uniform(0.0, 80.0, size=config.shape)
        terrain = TerrainLayers(
            elevation=elevation,
            slope=np.zeros(config.shape),
            aspect=np.zeros(config.shape),
            twi=np.zeros(config.shape),
            flow_accumulation=np.zeros(config.shape),
            curvature=np.zeros(config.shape),
        )
        duration_hr = float(rng.choice(np.array([0.65, 0.8, 0.95, 1.1])))
        wind_dir_deg = float(rng.choice(np.array([0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0])))
        wind_speed_ms = float(rng.choice(np.array([8.0, 12.0, 16.0])))

        corrected, _ = module.spread_fire(
            ignition,
            duration_hr,
            wind_speed_ms,
            wind_dir_deg,
            fuel,
            moisture,
            terrain,
            vegetation,
        )
        flawed = _spread_fire_first_enqueue(
            module,
            ignition,
            duration_hr,
            wind_speed_ms,
            wind_dir_deg,
            fuel,
            moisture,
            terrain,
        )
        if corrected.sum() > flawed.sum():
            witness = (corrected, flawed)
            break

    assert witness is not None
    corrected, flawed = witness
    assert corrected.sum() > flawed.sum()


def test_synthetic_aspect_uses_initializer_convention_for_north_south_ramp():
    config = LandscapeConfig((60.0, 60.0), 20.0, (0.0, 0.0), 32610)
    elevation = np.array(
        [
            [0.0, 0.0, 0.0],
            [20.0, 20.0, 20.0],
            [40.0, 40.0, 40.0],
        ],
        dtype=np.float32,
    )

    grad_y, grad_x = np.gradient(elevation, config.cell_size_m)
    aspect = _aspect_from_gradient(grad_x, grad_y)

    assert np.allclose(aspect, 180.0)
