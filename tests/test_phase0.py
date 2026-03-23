import numpy as np

from wattforest import LandscapeConfig, WattForestEngine
from wattforest.metrics import PatternMetrics


def test_single_cell_closes_canopy_within_phase0_window():
    config = LandscapeConfig((20.0, 20.0), 20.0, (0.0, 0.0), 32610)
    engine = WattForestEngine.from_synthetic(config)

    engine.run(0, 120)

    biomass = np.array([record.total_biomass_kg for record in engine.history])
    assert engine.vegetation[0, 0].total_canopy_cover >= 0.75
    assert biomass[40] > biomass[10]
    assert biomass[-1] > biomass[40]
    assert biomass[-1] < biomass[80] * 2.3


def test_phase0_grid_forms_gaps_and_spatial_structure():
    config = LandscapeConfig((200.0, 200.0), 20.0, (0.0, 0.0), 32610)
    engine = WattForestEngine.from_synthetic(config)

    engine.run(0, 160)

    canopy_cover = engine.canopy_cover_grid()
    cell_area_ha = (config.cell_size_m**2) / 10000.0
    mid_gap_count = max(record.n_gaps for record in engine.history[10:30])
    early_gap_fraction = max(record.fraction_in_gaps for record in engine.history[10:60])
    max_late_moran = max(record.morans_i_height for record in engine.history[15:])
    initial_moran = engine.history[0].morans_i_height
    late_gap_fraction = float(np.mean([record.fraction_in_gaps for record in engine.history[-20:]]))
    late_canopy_sd = float(canopy_cover.std())
    final_gap_metrics = PatternMetrics.gap_size_distribution(canopy_cover, cell_area_ha=cell_area_ha)

    assert np.max(canopy_cover) > 0.85
    assert mid_gap_count >= 1
    assert engine.history[-1].n_gaps == final_gap_metrics["n_gaps"]
    assert max_late_moran > initial_moran
    assert early_gap_fraction > late_gap_fraction
    assert late_canopy_sd > 0.05
    assert np.min(canopy_cover) < np.max(canopy_cover)
