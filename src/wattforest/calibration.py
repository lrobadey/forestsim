"""Phase 4 calibration and validation workflow."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - lightweight fallback for constrained test envs
    class _FallbackDataFrame(list):
        @property
        def empty(self) -> bool:
            return len(self) == 0

    class _FallbackPandasModule:
        @staticmethod
        def DataFrame(rows):
            return _FallbackDataFrame(rows)

    pd = _FallbackPandasModule()

from .species import SpeciesParams
from .tuning import (
    CalibrationGlobals,
    apply_parameter_overrides,
    sample_parameter_value,
    tunable_species_fields,
    validate_parameter_path,
)
from .validation import DEFAULT_AGE_BINS, Phase4PatternSnapshot, summarize_phase4_engine

_SCALAR_METRICS = {
    "mean_gap_fraction",
    "mean_gap_size",
    "mean_gap_size_ha",
    "species_richness",
    "biomass_trajectory_length",
    "total_biomass_kg_ha",
    "mean_canopy_height_m",
    "gap_fraction",
    "gap_size_p50_ha",
    "gap_size_p90_ha",
    "dominant_pft_patch_p50_cells",
    "dominant_pft_patch_p90_cells",
    "morans_i_height",
}
_VECTOR_METRICS = {"pft_biomass_fraction", "age_distribution", "biomass_trajectory_shape"}
_ALLOWED_METRICS = _SCALAR_METRICS | _VECTOR_METRICS


@dataclass(frozen=True)
class ParameterRange:
    minimum: float
    maximum: float
    scale: str = "linear"

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ParameterRange":
        return cls(
            minimum=float(payload["min"]),
            maximum=float(payload["max"]),
            scale=str(payload.get("scale", "linear")),
        )

    def to_dict(self) -> dict[str, object]:
        return {"min": self.minimum, "max": self.maximum, "scale": self.scale}

    def quantile(self, quantile: float) -> float:
        if self.scale == "log":
            if self.minimum <= 0.0 or self.maximum <= 0.0:
                raise ValueError("Log-scaled parameter ranges must be strictly positive")
            return float(np.exp(np.log(self.minimum) + quantile * (np.log(self.maximum) - np.log(self.minimum))))
        return float(self.minimum + quantile * (self.maximum - self.minimum))


@dataclass(frozen=True)
class MetricTarget:
    metric: str
    family: str
    observed: float | dict[str, float] | list[float]
    tolerance: float
    weight: float

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "MetricTarget":
        metric = str(payload["metric"])
        if metric not in _ALLOWED_METRICS:
            raise ValueError(f"Unsupported Phase 4 metric target {metric!r}")
        observed = payload["observed"]
        if metric == "pft_biomass_fraction":
            observed = {str(key): float(value) for key, value in dict(observed).items()}
        elif metric == "age_distribution":
            observed = [float(value) for value in list(observed)]
        else:
            observed = float(observed)
        return cls(
            metric=metric,
            family=str(payload.get("family", metric)),
            observed=observed,
            tolerance=float(payload["tolerance"]),
            weight=float(payload.get("weight", 1.0)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "family": self.family,
            "observed": self.observed,
            "tolerance": self.tolerance,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class CalibrationSpec:
    parameter_space: dict[str, ParameterRange]
    metric_targets: list[MetricTarget]
    gap_threshold: float = 0.3
    age_bins: list[int] = None  # type: ignore[assignment]
    min_pattern_families: int = 3

    def __post_init__(self) -> None:
        if self.age_bins is None:
            object.__setattr__(self, "age_bins", list(DEFAULT_AGE_BINS))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object], species_table: Sequence[SpeciesParams]) -> "CalibrationSpec":
        raw_parameter_space = payload.get("parameter_space", payload.get("param_ranges"))
        if raw_parameter_space is None:
            raise ValueError("Calibration spec requires parameter_space or param_ranges")
        parameter_space = {
            str(path): ParameterRange.from_dict(dict(spec))
            if isinstance(spec, Mapping)
            else ParameterRange(minimum=float(spec[0]), maximum=float(spec[1]))
            for path, spec in dict(raw_parameter_space).items()
        }
        for path in parameter_space:
            validate_parameter_path(path, species_table)
        if "metric_targets" in payload:
            metric_targets = [MetricTarget.from_dict(dict(entry)) for entry in list(payload["metric_targets"])]
        elif "target_patterns" in payload:
            metric_targets = _metric_targets_from_target_patterns(
                dict(payload["target_patterns"]),
                default_tolerance=float(payload.get("tolerance", 0.1)),
            )
        else:
            raise ValueError("Calibration spec requires metric_targets or target_patterns")
        age_bins = [int(value) for value in list(payload.get("age_bins", DEFAULT_AGE_BINS))]
        if len(age_bins) < 2:
            raise ValueError("Phase 4 age_bins must contain at least two edges")
        return cls(
            parameter_space=parameter_space,
            metric_targets=metric_targets,
            gap_threshold=float(payload.get("gap_threshold", 0.3)),
            age_bins=age_bins,
            min_pattern_families=int(payload.get("min_pattern_families", len(metric_targets))),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "parameter_space": {path: spec.to_dict() for path, spec in sorted(self.parameter_space.items())},
            "metric_targets": [target.to_dict() for target in self.metric_targets],
            "gap_threshold": self.gap_threshold,
            "age_bins": list(self.age_bins),
            "min_pattern_families": self.min_pattern_families,
        }

    @property
    def parameter_names(self) -> list[str]:
        return sorted(self.parameter_space)


def _metric_targets_from_target_patterns(
    target_patterns: Mapping[str, object],
    *,
    default_tolerance: float,
) -> list[MetricTarget]:
    metric_targets: list[MetricTarget] = []
    for metric_name, raw_target in sorted(target_patterns.items()):
        if metric_name not in _ALLOWED_METRICS:
            raise ValueError(f"Unsupported target pattern {metric_name!r}")
        if isinstance(raw_target, Mapping):
            payload = dict(raw_target)
            observed = payload["value"]
            tolerance = float(payload.get("tolerance", default_tolerance))
            weight = float(payload.get("weight", 1.0))
        else:
            observed = raw_target
            tolerance = default_tolerance
            weight = 1.0
        metric_targets.append(
            MetricTarget(
                metric=metric_name,
                family=metric_name,
                observed=observed,  # type: ignore[arg-type]
                tolerance=tolerance,
                weight=weight,
            )
        )
    return metric_targets


@dataclass(frozen=True)
class CalibrationSampleRecord:
    sample_index: int
    parameters: dict[str, float]
    simulated: Phase4PatternSnapshot
    metric_errors: dict[str, float]
    metric_passes: dict[str, bool]
    family_passes: dict[str, bool]
    total_distance: float
    accepted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_index": self.sample_index,
            "parameters": dict(self.parameters),
            "simulated": self.simulated.to_dict(),
            "metric_errors": dict(self.metric_errors),
            "metric_passes": dict(self.metric_passes),
            "family_passes": dict(self.family_passes),
            "total_distance": self.total_distance,
            "accepted": self.accepted,
        }

    def to_flat_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "sample_index": self.sample_index,
            "total_distance": self.total_distance,
            "accepted": self.accepted,
            "passing_family_count": int(sum(self.family_passes.values())),
        }
        for key, value in sorted(self.parameters.items()):
            payload[f"param::{key}"] = value
        for key, value in sorted(self.metric_errors.items()):
            payload[f"error::{key}"] = value
        for key, value in sorted(self.metric_passes.items()):
            payload[f"pass::{key}"] = value
        for key, value in sorted(self.family_passes.items()):
            payload[f"family::{key}"] = value
        for key, value in _flatten_snapshot_metrics(self.simulated).items():
            payload[f"metric::{key}"] = value
        return payload


class PatternOrientedCalibration:
    """Spec-faithful rejection-ABC calibration surface."""

    def __init__(
        self,
        engine_factory: Callable[[dict[str, float]], Any],
        target_patterns: Mapping[str, object],
        param_ranges: Mapping[str, object],
    ):
        self.engine_factory = engine_factory
        self.targets = dict(target_patterns)
        self.ranges = {
            str(name): ParameterRange.from_dict(dict(spec))
            if isinstance(spec, Mapping)
            else ParameterRange(minimum=float(spec[0]), maximum=float(spec[1]))
            for name, spec in dict(param_ranges).items()
        }

    def run_abc(
        self,
        n_samples: int = 1000,
        tolerance: float = 0.1,
    ) -> pd.DataFrame:
        rng = np.random.default_rng(0)
        accepted: list[dict[str, float]] = []
        for _ in range(n_samples):
            params = {
                name: sample_parameter_value(rng, spec.minimum, spec.maximum, spec.scale)
                for name, spec in sorted(self.ranges.items())
            }
            engine = self.engine_factory(params)
            engine.run(start_year=0, end_year=200)
            metrics = self._compute_metrics(engine)
            if _patterns_within_tolerance(self.targets, metrics, tolerance):
                accepted.append({name: float(value) for name, value in params.items()} | {"_accepted": True})
        return pd.DataFrame(accepted)

    def _compute_metrics(self, engine: Any) -> dict[str, float | list[float] | dict[str, float]]:
        snapshot = summarize_phase4_engine(engine)
        mean_gap_fraction = (
            float(np.mean([record.fraction_in_gaps for record in engine.history]))
            if getattr(engine, "history", None)
            else snapshot.gap_fraction
        )
        return {
            "mean_gap_fraction": mean_gap_fraction,
            "mean_gap_size": snapshot.mean_gap_size_ha,
            "mean_gap_size_ha": snapshot.mean_gap_size_ha,
            "morans_i_height": snapshot.morans_i_height,
            "species_richness": snapshot.species_richness,
            "biomass_trajectory_shape": list(snapshot.biomass_trajectory_shape),
            "gap_fraction": snapshot.gap_fraction,
            "pft_biomass_fraction": dict(snapshot.pft_biomass_fraction),
            "age_distribution": list(snapshot.age_distribution),
            "total_biomass_kg_ha": snapshot.total_biomass_kg_ha,
            "mean_canopy_height_m": snapshot.mean_canopy_height_m,
        }


@dataclass(frozen=True)
class Phase4CalibrationRun:
    site_id: str
    manifest_path: Path
    calibration_spec_path: Path
    start_year: int
    end_year: int
    calibration_spec: CalibrationSpec
    sampled_runs: list[CalibrationSampleRecord]
    accepted_runs: list[CalibrationSampleRecord]
    best_run: CalibrationSampleRecord
    neutral_baseline: CalibrationSampleRecord
    oat_sensitivity: list[dict[str, object]]
    sobol_indices: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "site_id": self.site_id,
            "manifest_path": str(self.manifest_path),
            "calibration_spec_path": str(self.calibration_spec_path),
            "start_year": self.start_year,
            "end_year": self.end_year,
            "n_sampled_runs": len(self.sampled_runs),
            "n_accepted_runs": len(self.accepted_runs),
            "best_run": self.best_run.to_dict(),
            "neutral_baseline": self.neutral_baseline.to_dict(),
            "oat_sensitivity_count": len(self.oat_sensitivity),
            "sobol_indices_count": len(self.sobol_indices),
        }


def load_calibration_spec(path: str | Path, species_table: Sequence[SpeciesParams]) -> CalibrationSpec:
    payload = json.loads(Path(path).read_text())
    return CalibrationSpec.from_dict(payload, species_table)


def _snapshot_metric_map(snapshot: Phase4PatternSnapshot) -> dict[str, float | list[float] | dict[str, float]]:
    return {
        "mean_gap_fraction": snapshot.gap_fraction,
        "mean_gap_size": snapshot.mean_gap_size_ha,
        "mean_gap_size_ha": snapshot.mean_gap_size_ha,
        "total_biomass_kg_ha": snapshot.total_biomass_kg_ha,
        "mean_canopy_height_m": snapshot.mean_canopy_height_m,
        "gap_fraction": snapshot.gap_fraction,
        "gap_size_p50_ha": snapshot.gap_size_p50_ha,
        "gap_size_p90_ha": snapshot.gap_size_p90_ha,
        "dominant_pft_patch_p50_cells": snapshot.dominant_pft_patch_p50_cells,
        "dominant_pft_patch_p90_cells": snapshot.dominant_pft_patch_p90_cells,
        "morans_i_height": snapshot.morans_i_height,
        "species_richness": snapshot.species_richness,
        "biomass_trajectory_shape": list(snapshot.biomass_trajectory_shape),
        "pft_biomass_fraction": dict(snapshot.pft_biomass_fraction),
        "age_distribution": list(snapshot.age_distribution),
    }


def _patterns_within_tolerance(
    target_patterns: Mapping[str, object],
    simulated_metrics: Mapping[str, object],
    tolerance: float,
) -> bool:
    for metric_name, raw_target in target_patterns.items():
        if metric_name not in simulated_metrics:
            return False
        observed = raw_target["value"] if isinstance(raw_target, Mapping) and "value" in raw_target else raw_target
        metric_tolerance = (
            float(raw_target.get("tolerance", tolerance))
            if isinstance(raw_target, Mapping)
            else float(tolerance)
        )
        error = _metric_error_against_value(metric_name, observed, simulated_metrics[metric_name])
        if error > metric_tolerance:
            return False
    return True


def run_phase4_calibration(
    manifest_path: str | Path,
    *,
    calibration_spec_path: str | Path | None = None,
    end_year: int | None = None,
    n_samples: int = 250,
    seed: int = 0,
    sobol_base_n: int = 128,
    engine_builder: Callable[..., Any] | None = None,
) -> Phase4CalibrationRun:
    from .initializer import LandscapeInitializer, _load_manifest, _resolve_manifest_path

    manifest, base_dir = _load_manifest(manifest_path)
    resolved_manifest_path = Path(manifest_path).resolve()
    start_year = int(manifest["start_year"])
    resolved_end_year = _resolve_phase4_end_year(manifest, end_year=end_year)
    if resolved_end_year < start_year:
        raise ValueError(
            f"Phase 4 calibration end_year {resolved_end_year} is earlier than manifest start_year {start_year}"
        )

    calibration_spec_file = calibration_spec_path
    calibration_block = manifest.get("calibration")
    if calibration_spec_file is None and isinstance(calibration_block, Mapping):
        calibration_spec_file = calibration_block.get("spec_path")
    if calibration_spec_file is None:
        raise ValueError("Phase 4 calibration requires --calibration-spec or calibration.spec_path in the manifest")
    resolved_spec_path = _resolve_manifest_path(base_dir, calibration_spec_file)

    build_engine = engine_builder or LandscapeInitializer.from_site_manifest
    prototype_engine = build_engine(resolved_manifest_path)
    calibration_spec = load_calibration_spec(resolved_spec_path, prototype_engine.species_table)
    rng = np.random.default_rng(seed)

    sampled_runs = [
        _evaluate_parameter_set(
            sample_index=index,
            parameter_values=_sample_parameter_set(rng, calibration_spec),
            manifest_path=resolved_manifest_path,
            start_year=start_year,
            end_year=resolved_end_year,
            calibration_spec=calibration_spec,
            base_species_table=prototype_engine.species_table,
            base_globals=prototype_engine.calibration_globals,
            engine_builder=build_engine,
        )
        for index in range(n_samples)
    ]
    accepted_runs = sorted([record for record in sampled_runs if record.accepted], key=lambda record: record.total_distance)
    best_run = accepted_runs[0] if accepted_runs else min(sampled_runs, key=lambda record: record.total_distance)

    neutral_baseline = _evaluate_neutral_baseline(
        manifest_path=resolved_manifest_path,
        start_year=start_year,
        end_year=resolved_end_year,
        calibration_spec=calibration_spec,
        base_species_table=prototype_engine.species_table,
        base_globals=prototype_engine.calibration_globals,
        anchor_parameters=best_run.parameters,
        engine_builder=build_engine,
    )
    oat_sensitivity = _run_oat_sensitivity(
        manifest_path=resolved_manifest_path,
        start_year=start_year,
        end_year=resolved_end_year,
        calibration_spec=calibration_spec,
        base_species_table=prototype_engine.species_table,
        base_globals=prototype_engine.calibration_globals,
        anchor_parameters=best_run.parameters,
        engine_builder=build_engine,
    )
    sobol_indices = _run_sobol_sensitivity(
        manifest_path=resolved_manifest_path,
        start_year=start_year,
        end_year=resolved_end_year,
        calibration_spec=calibration_spec,
        base_species_table=prototype_engine.species_table,
        base_globals=prototype_engine.calibration_globals,
        seed=seed,
        base_n=sobol_base_n,
        engine_builder=build_engine,
    )

    return Phase4CalibrationRun(
        site_id=str(manifest["site_id"]),
        manifest_path=resolved_manifest_path,
        calibration_spec_path=resolved_spec_path,
        start_year=start_year,
        end_year=resolved_end_year,
        calibration_spec=calibration_spec,
        sampled_runs=sampled_runs,
        accepted_runs=accepted_runs,
        best_run=best_run,
        neutral_baseline=neutral_baseline,
        oat_sensitivity=oat_sensitivity,
        sobol_indices=sobol_indices,
    )


def write_phase4_outputs(output_dir: str | Path, result: Phase4CalibrationRun) -> Path:
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "calibration_spec_resolved.json").write_text(
        json.dumps(result.calibration_spec.to_dict(), indent=2, sort_keys=True) + "\n"
    )
    _write_csv(directory / "runs.csv", [record.to_flat_dict() for record in result.sampled_runs])
    _write_csv(directory / "accepted_runs.csv", [record.to_flat_dict() for record in result.accepted_runs])
    (directory / "best_run.json").write_text(json.dumps(result.best_run.to_dict(), indent=2, sort_keys=True) + "\n")
    (directory / "neutral_baseline.json").write_text(
        json.dumps(
            {
                "mode": "neutral",
                "sample": result.neutral_baseline.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    _write_csv(directory / "oat_sensitivity.csv", result.oat_sensitivity)
    _write_csv(directory / "sobol_indices.csv", result.sobol_indices)
    (directory / "run_metadata.json").write_text(
        json.dumps(
            {
                "site_id": result.site_id,
                "manifest_path": str(result.manifest_path),
                "calibration_spec_path": str(result.calibration_spec_path),
                "start_year": result.start_year,
                "end_year": result.end_year,
                "n_samples": len(result.sampled_runs),
                "n_accepted_runs": len(result.accepted_runs),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return directory


def _resolve_phase4_end_year(manifest: Mapping[str, object], *, end_year: int | None) -> int:
    if end_year is not None:
        return int(end_year)
    calibration = manifest.get("calibration")
    if isinstance(calibration, Mapping) and "end_year" in calibration:
        return int(calibration["end_year"])
    validation = manifest.get("validation")
    if isinstance(validation, Mapping) and "baseline_end_year" in validation:
        return int(validation["baseline_end_year"])
    raise ValueError("Phase 4 calibration requires end_year, calibration.end_year, or validation.baseline_end_year")


def _sample_parameter_set(rng: np.random.Generator, calibration_spec: CalibrationSpec) -> dict[str, float]:
    return {
        name: sample_parameter_value(rng, spec.minimum, spec.maximum, spec.scale)
        for name, spec in sorted(calibration_spec.parameter_space.items())
    }


def _evaluate_parameter_set(
    *,
    sample_index: int,
    parameter_values: Mapping[str, float],
    manifest_path: Path,
    start_year: int,
    end_year: int,
    calibration_spec: CalibrationSpec,
    base_species_table: Sequence[SpeciesParams],
    base_globals: CalibrationGlobals,
    engine_builder: Callable[..., Any],
) -> CalibrationSampleRecord:
    species_table, calibration_globals = apply_parameter_overrides(base_species_table, base_globals, parameter_values)
    engine = engine_builder(
        manifest_path,
        species_table=species_table,
        calibration_globals=calibration_globals,
    )
    engine.run(start_year, end_year)
    simulated = summarize_phase4_engine(
        engine,
        gap_threshold=calibration_spec.gap_threshold,
        age_bins=calibration_spec.age_bins,
    )
    metric_errors, metric_passes, family_passes, total_distance, accepted = _score_snapshot(calibration_spec, simulated)
    return CalibrationSampleRecord(
        sample_index=sample_index,
        parameters={str(key): float(value) for key, value in sorted(parameter_values.items())},
        simulated=simulated,
        metric_errors=metric_errors,
        metric_passes=metric_passes,
        family_passes=family_passes,
        total_distance=float(total_distance),
        accepted=accepted,
    )


def _score_snapshot(
    calibration_spec: CalibrationSpec,
    simulated: Phase4PatternSnapshot,
) -> tuple[dict[str, float], dict[str, bool], dict[str, bool], float, bool]:
    metric_errors: dict[str, float] = {}
    metric_passes: dict[str, bool] = {}
    family_metric_passes: dict[str, list[bool]] = {}
    total_distance = 0.0
    simulated_metrics = _snapshot_metric_map(simulated)

    for target in calibration_spec.metric_targets:
        error = _metric_error_against_value(target.metric, target.observed, simulated_metrics.get(target.metric))
        passed = error <= target.tolerance
        metric_errors[target.metric] = error
        metric_passes[target.metric] = passed
        family_metric_passes.setdefault(target.family, []).append(passed)
        total_distance += target.weight * error

    family_passes = {family: all(values) for family, values in family_metric_passes.items()}
    accepted = bool(metric_passes) and all(metric_passes.values())
    return metric_errors, metric_passes, family_passes, float(total_distance), accepted


def _metric_error_against_value(
    metric_name: str,
    observed: float | dict[str, float] | list[float],
    simulated_value: object,
) -> float:
    if metric_name in _SCALAR_METRICS:
        observed_value = float(observed)
        return abs(float(simulated_value) - observed_value) / max(abs(observed_value), 1e-6)

    if metric_name == "pft_biomass_fraction":
        observed_mapping = {str(key): float(value) for key, value in dict(observed).items()}
        simulated_mapping = {str(key): float(value) for key, value in dict(simulated_value or {}).items()}
        keys = sorted(set(observed_mapping) | set(simulated_mapping))
        return float(sum(abs(simulated_mapping.get(key, 0.0) - observed_mapping.get(key, 0.0)) for key in keys))

    if metric_name in {"age_distribution", "biomass_trajectory_shape"}:
        observed_values = [float(value) for value in list(observed)]
        simulated_values = [float(value) for value in list(simulated_value or [])]
        if metric_name == "biomass_trajectory_shape" and observed_values and simulated_values:
            if len(observed_values) != len(simulated_values):
                simulated_values = np.interp(
                    np.linspace(0, len(simulated_values) - 1, num=len(observed_values)),
                    np.arange(len(simulated_values), dtype=float),
                    np.asarray(simulated_values, dtype=float),
                ).tolist()
        elif len(observed_values) != len(simulated_values):
            raise ValueError(f"Calibration target {metric_name} length must match simulated vector length")
        return float(np.mean([abs(a - b) for a, b in zip(simulated_values, observed_values)]))

    raise ValueError(f"Unsupported metric {metric_name!r}")


def _flatten_snapshot_metrics(snapshot: Phase4PatternSnapshot) -> dict[str, object]:
    payload: dict[str, object] = {
        "total_biomass_kg_ha": snapshot.total_biomass_kg_ha,
        "mean_canopy_height_m": snapshot.mean_canopy_height_m,
        "gap_fraction": snapshot.gap_fraction,
        "mean_gap_size_ha": snapshot.mean_gap_size_ha,
        "gap_size_p50_ha": snapshot.gap_size_p50_ha,
        "gap_size_p90_ha": snapshot.gap_size_p90_ha,
        "dominant_pft_patch_p50_cells": snapshot.dominant_pft_patch_p50_cells,
        "dominant_pft_patch_p90_cells": snapshot.dominant_pft_patch_p90_cells,
        "morans_i_height": snapshot.morans_i_height,
        "species_richness": snapshot.species_richness,
    }
    for index, value in enumerate(snapshot.biomass_trajectory_shape):
        payload[f"biomass_trajectory_shape::{index}"] = value
    for key, value in sorted(snapshot.pft_biomass_fraction.items()):
        payload[f"pft_biomass_fraction::{key}"] = value
    for index, value in enumerate(snapshot.age_distribution):
        payload[f"age_distribution::{index}"] = value
    return payload


def _neutralize_species_table(species_table: Sequence[SpeciesParams]) -> list[SpeciesParams]:
    species_copy = [SpeciesParams(**species.__dict__) for species in species_table]
    for field_name in tunable_species_fields():
        mean_value = float(np.mean([float(getattr(species, field_name)) for species in species_copy]))
        for species in species_copy:
            if isinstance(getattr(species, field_name), int):
                setattr(species, field_name, int(round(mean_value)))
            else:
                setattr(species, field_name, mean_value)
    return species_copy


def _evaluate_neutral_baseline(
    *,
    manifest_path: Path,
    start_year: int,
    end_year: int,
    calibration_spec: CalibrationSpec,
    base_species_table: Sequence[SpeciesParams],
    base_globals: CalibrationGlobals,
    anchor_parameters: Mapping[str, float],
    engine_builder: Callable[..., Any],
) -> CalibrationSampleRecord:
    anchored_species, anchored_globals = apply_parameter_overrides(base_species_table, base_globals, anchor_parameters)
    neutral_species = _neutralize_species_table(anchored_species)
    engine = engine_builder(
        manifest_path,
        species_table=neutral_species,
        calibration_globals=anchored_globals,
    )
    engine.run(start_year, end_year)
    simulated = summarize_phase4_engine(
        engine,
        gap_threshold=calibration_spec.gap_threshold,
        age_bins=calibration_spec.age_bins,
    )
    metric_errors, metric_passes, family_passes, total_distance, accepted = _score_snapshot(calibration_spec, simulated)
    return CalibrationSampleRecord(
        sample_index=-1,
        parameters={str(key): float(value) for key, value in sorted(anchor_parameters.items())},
        simulated=simulated,
        metric_errors=metric_errors,
        metric_passes=metric_passes,
        family_passes=family_passes,
        total_distance=float(total_distance),
        accepted=accepted,
    )


def _run_oat_sensitivity(
    *,
    manifest_path: Path,
    start_year: int,
    end_year: int,
    calibration_spec: CalibrationSpec,
    base_species_table: Sequence[SpeciesParams],
    base_globals: CalibrationGlobals,
    anchor_parameters: Mapping[str, float],
    engine_builder: Callable[..., Any],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for parameter_name in calibration_spec.parameter_names:
        spec = calibration_spec.parameter_space[parameter_name]
        for quantile in (0.25, 0.75):
            updated_parameters = dict(anchor_parameters)
            updated_parameters[parameter_name] = spec.quantile(quantile)
            record = _evaluate_parameter_set(
                sample_index=-1,
                parameter_values=updated_parameters,
                manifest_path=manifest_path,
                start_year=start_year,
                end_year=end_year,
                calibration_spec=calibration_spec,
                base_species_table=base_species_table,
                base_globals=base_globals,
                engine_builder=engine_builder,
            )
            rows.append(
                {
                    "parameter": parameter_name,
                    "quantile": quantile,
                    "value": updated_parameters[parameter_name],
                    "total_distance": record.total_distance,
                    "accepted": record.accepted,
                    "passing_family_count": int(sum(record.family_passes.values())),
                }
            )
    return rows


def _run_sobol_sensitivity(
    *,
    manifest_path: Path,
    start_year: int,
    end_year: int,
    calibration_spec: CalibrationSpec,
    base_species_table: Sequence[SpeciesParams],
    base_globals: CalibrationGlobals,
    seed: int,
    base_n: int,
    engine_builder: Callable[..., Any],
) -> list[dict[str, object]]:
    parameter_names = calibration_spec.parameter_names
    if not parameter_names:
        return []

    rng = np.random.default_rng(seed + 1009)
    a_unit = rng.uniform(0.0, 1.0, size=(base_n, len(parameter_names)))
    b_unit = rng.uniform(0.0, 1.0, size=(base_n, len(parameter_names)))
    a = _scale_unit_samples(a_unit, calibration_spec, parameter_names)
    b = _scale_unit_samples(b_unit, calibration_spec, parameter_names)
    y_a = _evaluate_distance_matrix(
        a,
        parameter_names,
        manifest_path=manifest_path,
        start_year=start_year,
        end_year=end_year,
        calibration_spec=calibration_spec,
        base_species_table=base_species_table,
        base_globals=base_globals,
        engine_builder=engine_builder,
    )
    y_b = _evaluate_distance_matrix(
        b,
        parameter_names,
        manifest_path=manifest_path,
        start_year=start_year,
        end_year=end_year,
        calibration_spec=calibration_spec,
        base_species_table=base_species_table,
        base_globals=base_globals,
        engine_builder=engine_builder,
    )
    variance = float(np.var(np.concatenate([y_a, y_b]), ddof=1))
    if variance <= 1e-12:
        return [{"parameter": name, "first_order": 0.0, "total_order": 0.0} for name in parameter_names]

    rows: list[dict[str, object]] = []
    for index, parameter_name in enumerate(parameter_names):
        c = b.copy()
        c[:, index] = a[:, index]
        y_c = _evaluate_distance_matrix(
            c,
            parameter_names,
            manifest_path=manifest_path,
            start_year=start_year,
            end_year=end_year,
            calibration_spec=calibration_spec,
            base_species_table=base_species_table,
            base_globals=base_globals,
            engine_builder=engine_builder,
        )
        first_order = float(np.mean(y_b * (y_c - y_a)) / variance)
        total_order = float(0.5 * np.mean((y_a - y_c) ** 2) / variance)
        rows.append({"parameter": parameter_name, "first_order": first_order, "total_order": total_order})
    return rows


def _scale_unit_samples(
    matrix: np.ndarray,
    calibration_spec: CalibrationSpec,
    parameter_names: Sequence[str],
) -> np.ndarray:
    scaled = np.zeros_like(matrix, dtype=float)
    for index, parameter_name in enumerate(parameter_names):
        spec = calibration_spec.parameter_space[parameter_name]
        scaled[:, index] = [spec.quantile(float(value)) for value in matrix[:, index]]
    return scaled


def _evaluate_distance_matrix(
    matrix: np.ndarray,
    parameter_names: Sequence[str],
    *,
    manifest_path: Path,
    start_year: int,
    end_year: int,
    calibration_spec: CalibrationSpec,
    base_species_table: Sequence[SpeciesParams],
    base_globals: CalibrationGlobals,
    engine_builder: Callable[..., Any],
) -> np.ndarray:
    distances = np.zeros(matrix.shape[0], dtype=float)
    for row_index in range(matrix.shape[0]):
        parameter_values = {
            parameter_name: float(matrix[row_index, column_index])
            for column_index, parameter_name in enumerate(parameter_names)
        }
        record = _evaluate_parameter_set(
            sample_index=row_index,
            parameter_values=parameter_values,
            manifest_path=manifest_path,
            start_year=start_year,
            end_year=end_year,
            calibration_spec=calibration_spec,
            base_species_table=base_species_table,
            base_globals=base_globals,
            engine_builder=engine_builder,
        )
        distances[row_index] = record.total_distance
    return distances


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        if not fieldnames:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
