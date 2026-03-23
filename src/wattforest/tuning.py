"""Calibration parameter helpers."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Mapping, Sequence

import numpy as np

from .species import SpeciesParams

_SPECIES_IDENTITY_FIELDS = {"species_id", "name", "pft"}
_SPECIES_FIELDS = {field.name: field for field in fields(SpeciesParams)}


@dataclass(frozen=True)
class CalibrationGlobals:
    recruitment_base_scalar: float = 1.0
    recruitment_disturbance_scalar: float = 1.0
    mortality_stress_scalar: float = 1.0
    fire_spread_scalar: float = 1.0
    windthrow_damage_scalar: float = 1.0

    def to_dict(self) -> dict[str, float]:
        return {
            "recruitment_base_scalar": float(self.recruitment_base_scalar),
            "recruitment_disturbance_scalar": float(self.recruitment_disturbance_scalar),
            "mortality_stress_scalar": float(self.mortality_stress_scalar),
            "fire_spread_scalar": float(self.fire_spread_scalar),
            "windthrow_damage_scalar": float(self.windthrow_damage_scalar),
        }


def tunable_species_fields() -> list[str]:
    return sorted(name for name in _SPECIES_FIELDS if name not in _SPECIES_IDENTITY_FIELDS)


def _species_field_cast(field_name: str, value: float) -> int | float:
    field = _SPECIES_FIELDS[field_name]
    if field_name in _SPECIES_IDENTITY_FIELDS:
        raise ValueError(f"Field {field_name} is not tunable")
    current_type = field.type
    if current_type is int:
        return int(round(value))
    return float(value)


def validate_parameter_path(path: str, species_table: Sequence[SpeciesParams]) -> None:
    parts = path.split(".")
    if len(parts) == 2 and parts[0] == "globals":
        field_name = parts[1]
        if not hasattr(CalibrationGlobals(), field_name):
            raise ValueError(f"Unknown global calibration field {field_name!r} in parameter path {path!r}")
        return
    if len(parts) != 3:
        raise ValueError(f"Parameter path {path!r} must be 'species.<pft>.<field>' or 'globals.<field>'")

    root, target, field_name = parts
    if root == "species":
        if field_name not in _SPECIES_FIELDS:
            raise ValueError(f"Unknown species field {field_name!r} in parameter path {path!r}")
        if field_name in _SPECIES_IDENTITY_FIELDS:
            raise ValueError(f"Species field {field_name!r} is not tunable in parameter path {path!r}")
        valid_pfts = {species.pft for species in species_table}
        if target not in valid_pfts:
            raise ValueError(f"Unknown species/PFT {target!r} in parameter path {path!r}")
        return

    if root == "globals":
        raise ValueError(f"Global parameter path {path!r} must use the form 'globals.<field>'")

    raise ValueError(f"Unsupported parameter root {root!r} in parameter path {path!r}")


def apply_parameter_overrides(
    species_table: Sequence[SpeciesParams],
    calibration_globals: CalibrationGlobals,
    overrides: Mapping[str, float],
) -> tuple[list[SpeciesParams], CalibrationGlobals]:
    updated_species = [replace(species) for species in species_table]
    species_by_pft = {species.pft: species for species in updated_species}
    globals_payload = calibration_globals.to_dict()

    for path, value in overrides.items():
        parts = path.split(".")
        if len(parts) == 2 and parts[0] == "globals":
            field_name = parts[1]
            if field_name not in globals_payload:
                raise ValueError(f"Unknown global calibration field {field_name!r} in parameter path {path!r}")
            globals_payload[field_name] = float(value)
            continue

        if len(parts) != 3 or parts[0] != "species":
            raise ValueError(
                f"Parameter path {path!r} must be 'species.<pft>.<field>' or 'globals.<field>'"
            )

        _, pft, field_name = parts
        if pft not in species_by_pft:
            raise ValueError(f"Unknown species/PFT {pft!r} in parameter path {path!r}")
        if field_name not in _SPECIES_FIELDS or field_name in _SPECIES_IDENTITY_FIELDS:
            raise ValueError(f"Unknown or non-tunable species field {field_name!r} in parameter path {path!r}")
        setattr(species_by_pft[pft], field_name, _species_field_cast(field_name, float(value)))

    return updated_species, CalibrationGlobals(**globals_payload)


def sample_parameter_value(
    rng: np.random.Generator,
    minimum: float,
    maximum: float,
    scale: str,
) -> float:
    if maximum < minimum:
        raise ValueError(f"Invalid parameter range: max {maximum} is below min {minimum}")
    if scale == "linear":
        return float(rng.uniform(minimum, maximum))
    if scale == "log":
        if minimum <= 0.0 or maximum <= 0.0:
            raise ValueError("Log-scaled parameter ranges must be strictly positive")
        return float(np.exp(rng.uniform(np.log(minimum), np.log(maximum))))
    raise ValueError(f"Unsupported parameter scale {scale!r}")
