"""Phase 3 and Phase 4 validation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .engine import WattForestEngine
from .metrics import PatternMetrics
from .species import SpeciesParams

DEFAULT_AGE_BINS = [0, 20, 40, 80, 120, 999]


@dataclass(frozen=True)
class SitePatternSummary:
    total_biomass_kg: float
    total_biomass_kg_ha: float
    gap_fraction: float
    mean_canopy_height_m: float
    morans_i_height: float
    pft_biomass_kg: dict[str, float]
    pft_biomass_fraction: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "total_biomass_kg": self.total_biomass_kg,
            "total_biomass_kg_ha": self.total_biomass_kg_ha,
            "gap_fraction": self.gap_fraction,
            "mean_canopy_height_m": self.mean_canopy_height_m,
            "morans_i_height": self.morans_i_height,
            "pft_biomass_kg": dict(self.pft_biomass_kg),
            "pft_biomass_fraction": dict(self.pft_biomass_fraction),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SitePatternSummary":
        required = {
            "total_biomass_kg",
            "total_biomass_kg_ha",
            "gap_fraction",
            "mean_canopy_height_m",
            "morans_i_height",
            "pft_biomass_kg",
            "pft_biomass_fraction",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"Site pattern payload is missing required keys: {missing}")

        return cls(
            total_biomass_kg=float(payload["total_biomass_kg"]),
            total_biomass_kg_ha=float(payload["total_biomass_kg_ha"]),
            gap_fraction=float(payload["gap_fraction"]),
            mean_canopy_height_m=float(payload["mean_canopy_height_m"]),
            morans_i_height=float(payload["morans_i_height"]),
            pft_biomass_kg={str(key): float(value) for key, value in dict(payload["pft_biomass_kg"]).items()},
            pft_biomass_fraction={str(key): float(value) for key, value in dict(payload["pft_biomass_fraction"]).items()},
        )


@dataclass(frozen=True)
class Phase4PatternSnapshot:
    total_biomass_kg_ha: float = 0.0
    mean_canopy_height_m: float = 0.0
    gap_fraction: float = 0.0
    mean_gap_size_ha: float = 0.0
    gap_size_p50_ha: float = 0.0
    gap_size_p90_ha: float = 0.0
    dominant_pft_patch_p50_cells: float = 0.0
    dominant_pft_patch_p90_cells: float = 0.0
    morans_i_height: float = 0.0
    species_richness: float = 0.0
    biomass_trajectory_shape: list[float] = field(default_factory=list)
    pft_biomass_fraction: dict[str, float] = field(default_factory=dict)
    age_distribution: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "total_biomass_kg_ha": self.total_biomass_kg_ha,
            "mean_canopy_height_m": self.mean_canopy_height_m,
            "gap_fraction": self.gap_fraction,
            "mean_gap_size_ha": self.mean_gap_size_ha,
            "gap_size_p50_ha": self.gap_size_p50_ha,
            "gap_size_p90_ha": self.gap_size_p90_ha,
            "dominant_pft_patch_p50_cells": self.dominant_pft_patch_p50_cells,
            "dominant_pft_patch_p90_cells": self.dominant_pft_patch_p90_cells,
            "morans_i_height": self.morans_i_height,
            "species_richness": self.species_richness,
            "biomass_trajectory_shape": list(self.biomass_trajectory_shape),
            "pft_biomass_fraction": dict(self.pft_biomass_fraction),
            "age_distribution": list(self.age_distribution),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "Phase4PatternSnapshot":
        required = {
            "total_biomass_kg_ha",
            "mean_canopy_height_m",
            "gap_fraction",
            "gap_size_p50_ha",
            "gap_size_p90_ha",
            "dominant_pft_patch_p50_cells",
            "dominant_pft_patch_p90_cells",
            "morans_i_height",
            "pft_biomass_fraction",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"Phase 4 snapshot payload is missing required keys: {missing}")

        return cls(
            total_biomass_kg_ha=float(payload["total_biomass_kg_ha"]),
            mean_canopy_height_m=float(payload["mean_canopy_height_m"]),
            gap_fraction=float(payload["gap_fraction"]),
            mean_gap_size_ha=float(payload.get("mean_gap_size_ha", 0.0)),
            gap_size_p50_ha=float(payload["gap_size_p50_ha"]),
            gap_size_p90_ha=float(payload["gap_size_p90_ha"]),
            dominant_pft_patch_p50_cells=float(payload["dominant_pft_patch_p50_cells"]),
            dominant_pft_patch_p90_cells=float(payload["dominant_pft_patch_p90_cells"]),
            morans_i_height=float(payload["morans_i_height"]),
            species_richness=float(payload.get("species_richness", 0.0)),
            biomass_trajectory_shape=[float(value) for value in list(payload.get("biomass_trajectory_shape", []))],
            pft_biomass_fraction={
                str(key): float(value) for key, value in dict(payload["pft_biomass_fraction"]).items()
            },
            age_distribution=[float(value) for value in list(payload.get("age_distribution", []))],
        )


def _species_lookup(species_table: Sequence[SpeciesParams]) -> dict[int, str]:
    return {species.species_id: species.pft for species in species_table}


def summarize_engine(engine: WattForestEngine, *, gap_threshold: float = 0.3) -> SitePatternSummary:
    species_lookup = _species_lookup(engine.species_table)
    canopy = engine.canopy_cover_grid()
    height = engine.dominant_height_grid()
    cell_area_ha = (engine.config.cell_size_m**2) / 10000.0

    # TODO: `total_biomass_kg_ha` should be an area-weighted landscape mean.
    # The current implementation sums per-cell kg/ha values, which inflates the
    # reported landscape density and contaminates validation/calibration scores.
    total_biomass_kg_ha = float(sum(cell.total_biomass_kg_ha for cell in engine.vegetation.ravel()))
    total_biomass_kg = total_biomass_kg_ha * cell_area_ha

    pft_biomass_kg = _pft_biomass_kg(engine, species_lookup)
    pft_total_kg = max(sum(pft_biomass_kg.values()), 1e-9)
    pft_biomass_fraction = {pft: biomass / pft_total_kg for pft, biomass in pft_biomass_kg.items()}

    gap_metrics = PatternMetrics.gap_size_distribution(canopy, gap_threshold=gap_threshold, cell_area_ha=cell_area_ha)
    return SitePatternSummary(
        total_biomass_kg=total_biomass_kg,
        total_biomass_kg_ha=total_biomass_kg_ha,
        gap_fraction=float(gap_metrics["fraction_in_gaps"]),
        mean_canopy_height_m=float(np.mean(height)),
        morans_i_height=float(PatternMetrics.morans_i(height)),
        pft_biomass_kg=pft_biomass_kg,
        pft_biomass_fraction=pft_biomass_fraction,
    )


def compare_site_patterns(
    observed: SitePatternSummary,
    simulated: SitePatternSummary,
) -> dict[str, float]:
    def relative_error(observed_value: float, simulated_value: float) -> float:
        return abs(simulated_value - observed_value) / max(abs(observed_value), 1e-6)

    comparison = {
        "total_biomass_kg_rel_error": relative_error(observed.total_biomass_kg, simulated.total_biomass_kg),
        "total_biomass_kg_ha_rel_error": relative_error(observed.total_biomass_kg_ha, simulated.total_biomass_kg_ha),
        "gap_fraction_abs_error": abs(simulated.gap_fraction - observed.gap_fraction),
        "mean_canopy_height_m_rel_error": relative_error(observed.mean_canopy_height_m, simulated.mean_canopy_height_m),
        "morans_i_height_abs_error": abs(simulated.morans_i_height - observed.morans_i_height),
    }

    for pft, observed_fraction in observed.pft_biomass_fraction.items():
        simulated_fraction = simulated.pft_biomass_fraction.get(pft, 0.0)
        comparison[f"pft_fraction_abs_error::{pft}"] = abs(simulated_fraction - observed_fraction)

    comparison["mean_pft_fraction_abs_error"] = float(
        np.mean([value for key, value in comparison.items() if key.startswith("pft_fraction_abs_error::")] or [0.0])
    )
    comparison["phase3_validation_score"] = float(
        np.mean(
            [
                comparison["total_biomass_kg_ha_rel_error"],
                comparison["gap_fraction_abs_error"],
                comparison["mean_canopy_height_m_rel_error"],
                comparison["morans_i_height_abs_error"],
                comparison["mean_pft_fraction_abs_error"],
            ]
        )
    )
    return comparison


def summarize_phase4_engine(
    engine: WattForestEngine,
    *,
    gap_threshold: float = 0.3,
    age_bins: Sequence[int] | None = None,
) -> Phase4PatternSnapshot:
    species_lookup = _species_lookup(engine.species_table)
    canopy = engine.canopy_cover_grid()
    height = engine.dominant_height_grid()
    cell_area_ha = (engine.config.cell_size_m**2) / 10000.0
    gap_quantiles = PatternMetrics.gap_size_quantiles(
        canopy,
        gap_threshold=gap_threshold,
        cell_area_ha=cell_area_ha,
    )
    gap_distribution = PatternMetrics.gap_size_distribution(
        canopy,
        gap_threshold=gap_threshold,
        cell_area_ha=cell_area_ha,
    )
    dominant_pft = _dominant_pft_grid(engine, species_lookup)
    patch_quantiles = PatternMetrics.patch_size_quantiles(dominant_pft, background_value=-1)

    # TODO: Fix this to mirror the corrected landscape-density calculation in
    # `summarize_engine(...)` and add a regression test that compares against
    # `total_biomass_kg / total_area_ha`.
    total_biomass_kg_ha = float(sum(cell.total_biomass_kg_ha for cell in engine.vegetation.ravel()))
    pft_biomass_kg = _pft_biomass_kg(engine, species_lookup)
    pft_total = max(sum(pft_biomass_kg.values()), 1e-9)
    pft_biomass_fraction = {
        pft: biomass / pft_total for pft, biomass in sorted(pft_biomass_kg.items(), key=lambda item: item[0])
    }

    return Phase4PatternSnapshot(
        total_biomass_kg_ha=total_biomass_kg_ha,
        mean_canopy_height_m=float(np.mean(height)),
        gap_fraction=float(gap_quantiles["fraction_in_gaps"]),
        mean_gap_size_ha=float(np.mean(np.asarray(gap_distribution["sizes_ha"], dtype=float)))
        if int(gap_distribution["n_gaps"]) > 0
        else 0.0,
        gap_size_p50_ha=float(gap_quantiles["p50_ha"]),
        gap_size_p90_ha=float(gap_quantiles["p90_ha"]),
        dominant_pft_patch_p50_cells=float(patch_quantiles["p50_cells"]),
        dominant_pft_patch_p90_cells=float(patch_quantiles["p90_cells"]),
        morans_i_height=float(PatternMetrics.morans_i(height)),
        species_richness=float(sum(1 for value in pft_biomass_fraction.values() if value > 0.0)),
        biomass_trajectory_shape=_biomass_trajectory_shape(engine),
        pft_biomass_fraction=pft_biomass_fraction,
        age_distribution=_biomass_weighted_age_distribution(engine, age_bins or DEFAULT_AGE_BINS),
    )


def load_site_pattern_summary(path: str | Path) -> SitePatternSummary:
    payload = json.loads(Path(path).read_text())
    return SitePatternSummary.from_dict(payload)


def write_site_pattern_summary(path: str | Path, summary: SitePatternSummary) -> None:
    Path(path).write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n")


def load_phase4_pattern_snapshot(path: str | Path) -> Phase4PatternSnapshot:
    payload = json.loads(Path(path).read_text())
    return Phase4PatternSnapshot.from_dict(payload)


def write_phase4_pattern_snapshot(path: str | Path, snapshot: Phase4PatternSnapshot) -> None:
    Path(path).write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n")


def _pft_biomass_kg(engine: WattForestEngine, species_lookup: Mapping[int, str]) -> dict[str, float]:
    cell_area_ha = (engine.config.cell_size_m**2) / 10000.0
    pfts = sorted(set(species_lookup.values()))
    pft_biomass_kg = {pft: 0.0 for pft in pfts}
    for cell in engine.vegetation.ravel():
        for cohort in cell.cohorts:
            pft_biomass_kg[species_lookup[cohort.species_id]] += float(cohort.biomass_kg_ha * cell_area_ha)
    return pft_biomass_kg


def _dominant_pft_grid(engine: WattForestEngine, species_lookup: Mapping[int, str]) -> np.ndarray:
    pft_order = {pft: idx for idx, pft in enumerate(sorted(set(species_lookup.values())))}
    dominant = np.full(engine.config.shape, -1, dtype=np.int16)
    for row in range(engine.config.shape[0]):
        for col in range(engine.config.shape[1]):
            cell = engine.vegetation[row, col]
            if not cell.cohorts:
                continue
            biomass_by_pft: dict[str, float] = {}
            for cohort in cell.cohorts:
                pft = species_lookup[cohort.species_id]
                biomass_by_pft[pft] = biomass_by_pft.get(pft, 0.0) + float(cohort.biomass_kg_ha)
            if biomass_by_pft:
                dominant_pft = max(sorted(biomass_by_pft), key=lambda pft: biomass_by_pft[pft])
                dominant[row, col] = pft_order[dominant_pft]
    return dominant


def _biomass_weighted_age_distribution(engine: WattForestEngine, age_bins: Sequence[int]) -> list[float]:
    if len(age_bins) < 2:
        raise ValueError("Phase 4 age_bins must contain at least two edges")
    if sorted(age_bins) != list(age_bins):
        raise ValueError("Phase 4 age_bins must be monotonically increasing")

    biomass = np.zeros(len(age_bins) - 1, dtype=float)
    for cell in engine.vegetation.ravel():
        for cohort in cell.cohorts:
            bin_index = min(
                len(age_bins) - 2,
                int(np.searchsorted(np.asarray(age_bins[1:], dtype=float), cohort.age, side="right")),
            )
            biomass[bin_index] += float(max(0.0, cohort.biomass_kg_ha))
    total = float(biomass.sum())
    if total <= 0.0:
        return [0.0 for _ in biomass]
    return [float(value / total) for value in biomass]


def _biomass_trajectory_shape(engine: WattForestEngine) -> list[float]:
    if engine.history:
        series = np.asarray([record.total_biomass_kg for record in engine.history], dtype=float)
    else:
        cell_area_ha = (engine.config.cell_size_m**2) / 10000.0
        series = np.asarray([sum(cell.total_biomass_kg_ha for cell in engine.vegetation.ravel()) * cell_area_ha], dtype=float)
    if series.size == 0:
        return []
    if series.size == 1:
        return [1.0]
    normalized = series / max(float(np.max(series)), 1e-6)
    sample_positions = np.linspace(0, normalized.size - 1, num=min(8, normalized.size))
    sampled = np.interp(sample_positions, np.arange(normalized.size, dtype=float), normalized)
    return [float(value) for value in sampled]
