"""Pattern metrics scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Sequence

import numpy as np
from scipy.ndimage import generic_filter, label


class PatternMetrics:
    _EIGHT_NEIGHBOR = np.ones((3, 3), dtype=np.uint8)

    @staticmethod
    def gap_size_distribution(
        canopy_cover: np.ndarray,
        gap_threshold: float = 0.3,
        cell_area_ha: float = 0.04,
    ) -> Dict[str, np.ndarray | float | int]:
        gap_mask = canopy_cover < gap_threshold
        labeled, n_gaps = label(gap_mask, structure=PatternMetrics._EIGHT_NEIGHBOR)
        gap_sizes = [np.sum(labeled == gap_id) * cell_area_ha for gap_id in range(1, n_gaps + 1)]
        return {
            "sizes_ha": np.array(gap_sizes),
            "n_gaps": n_gaps,
            "fraction_in_gaps": float(gap_mask.mean()),
        }

    @staticmethod
    def patch_size_distribution(categorical_map: np.ndarray) -> Dict[int, np.ndarray]:
        categories = np.unique(categorical_map)
        result: Dict[int, np.ndarray] = {}
        for category in categories:
            labeled, n_patches = label(categorical_map == category, structure=PatternMetrics._EIGHT_NEIGHBOR)
            result[int(category)] = np.array([np.sum(labeled == patch_id) for patch_id in range(1, n_patches + 1)])
        return result

    @staticmethod
    def quantile(values: Iterable[float], q: float, default: float = 0.0) -> float:
        array = np.asarray(list(values), dtype=float)
        if array.size == 0:
            return float(default)
        return float(np.quantile(array, q))

    @staticmethod
    def gap_size_quantiles(
        canopy_cover: np.ndarray,
        *,
        gap_threshold: float = 0.3,
        cell_area_ha: float = 0.04,
        quantiles: Sequence[float] = (0.5, 0.9),
    ) -> Dict[str, float]:
        distribution = PatternMetrics.gap_size_distribution(
            canopy_cover,
            gap_threshold=gap_threshold,
            cell_area_ha=cell_area_ha,
        )
        sizes = np.asarray(distribution["sizes_ha"], dtype=float)
        return {
            f"p{int(round(quantile * 100))}_ha": PatternMetrics.quantile(sizes, quantile)
            for quantile in quantiles
        } | {"fraction_in_gaps": float(distribution["fraction_in_gaps"])}

    @staticmethod
    def patch_size_quantiles(
        categorical_map: np.ndarray,
        *,
        quantiles: Sequence[float] = (0.5, 0.9),
        background_value: int | None = None,
    ) -> Dict[str, float]:
        sizes: list[float] = []
        for category, category_sizes in PatternMetrics.patch_size_distribution(categorical_map).items():
            if background_value is not None and category == background_value:
                continue
            sizes.extend(float(size) for size in np.asarray(category_sizes, dtype=float))
        return {
            f"p{int(round(quantile * 100))}_cells": PatternMetrics.quantile(sizes, quantile)
            for quantile in quantiles
        }

    @staticmethod
    def morans_i(values: np.ndarray) -> float:
        values = values.astype(float)
        n = values.size
        mean = float(np.nanmean(values))
        deviations = values - mean
        denominator = float(np.nansum(deviations**2))
        if denominator == 0.0:
            return 0.0

        def neighbor_deviation_sum(window: np.ndarray) -> float:
            neighbors = np.delete(window, 4)
            return float(np.nansum(neighbors))

        lagged = generic_filter(deviations, neighbor_deviation_sum, size=3, mode="constant", cval=np.nan)
        numerator = float(np.nansum(deviations * lagged))

        rows, cols = values.shape
        horizontal_edges = rows * max(cols - 1, 0)
        vertical_edges = max(rows - 1, 0) * cols
        diagonal_edges = 2 * max(rows - 1, 0) * max(cols - 1, 0)
        w_sum = float(2 * (horizontal_edges + vertical_edges + diagonal_edges))
        if w_sum == 0.0:
            return 0.0
        return float((n / w_sum) * (numerator / denominator))

    @staticmethod
    def age_class_distribution(
        vegetation_grid: np.ndarray,
        bin_width_yr: int = 20,
    ) -> Dict[str, np.ndarray | float]:
        if bin_width_yr <= 0:
            raise ValueError("bin_width_yr must be positive")

        ages: list[int] = []
        for row in range(vegetation_grid.shape[0]):
            for col in range(vegetation_grid.shape[1]):
                cell = vegetation_grid[row, col]
                if not cell.cohorts:
                    continue
                dominant = max(cell.cohorts, key=lambda cohort: cohort.canopy_height_m)
                ages.append(int(dominant.age))

        if not ages:
            edges = np.array([0, bin_width_yr], dtype=int)
            return {"counts": np.array([0], dtype=int), "bin_edges": edges, "mean_age": 0.0}

        ages_array = np.asarray(ages, dtype=int)
        max_age = int(ages_array.max())
        upper_edge = ((max_age // bin_width_yr) + 1) * bin_width_yr
        edges = np.arange(0, upper_edge + bin_width_yr, bin_width_yr, dtype=int)
        hist, bin_edges = np.histogram(ages_array, bins=edges)
        return {
            "counts": hist.astype(int),
            "bin_edges": bin_edges.astype(int),
            "mean_age": float(ages_array.mean()),
        }


@dataclass
class YearRecord:
    year: int
    total_biomass_kg: float
    mean_canopy_height_m: float
    fraction_in_gaps: float
    n_gaps: int
    species_basal_area: Dict[int, float]
    morans_i_height: float
    morans_i_age: float
    area_burned_ha: float
    area_harvested_ha: float
    area_blown_down_ha: float
    n_species_present: int
