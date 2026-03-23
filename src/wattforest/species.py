"""Species parameter definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List


@dataclass
class SpeciesParams:
    """Trait table for one species or plant functional type."""

    species_id: int
    name: str
    pft: str
    d_max_cm: float
    h_max_m: float
    age_max_yr: int
    g_max_cm_yr: float
    specific_leaf_area: float
    wood_density_kg_m3: float
    shade_tolerance: float
    light_compensation_frac: float
    light_saturation_frac: float
    gdd_min: float
    gdd_max: float
    drought_tolerance: float
    frost_tolerance: float
    background_mortality_yr: float
    stress_mortality_threshold: float
    stress_mortality_rate: float
    maturity_age_yr: int
    fecundity_seeds_yr: float
    seed_mass_g: float
    dispersal_mean_m: float
    dispersal_fat_tail_p: float
    leaf_litter_bulk_density: float
    flammability: float


_DEFAULT_SPECIES_PAYLOAD = [
    {
        "species_id": 0,
        "name": "Pioneer Conifer",
        "pft": "pioneer_conifer",
        "d_max_cm": 95.0,
        "h_max_m": 42.0,
        "age_max_yr": 220,
        "g_max_cm_yr": 1.05,
        "specific_leaf_area": 8.5,
        "wood_density_kg_m3": 430.0,
        "shade_tolerance": 1.4,
        "light_compensation_frac": 0.18,
        "light_saturation_frac": 0.85,
        "gdd_min": 700.0,
        "gdd_max": 2600.0,
        "drought_tolerance": 0.72,
        "frost_tolerance": 110.0,
        "background_mortality_yr": 0.012,
        "stress_mortality_threshold": 0.42,
        "stress_mortality_rate": 0.22,
        "maturity_age_yr": 12,
        "fecundity_seeds_yr": 2600.0,
        "seed_mass_g": 0.7,
        "dispersal_mean_m": 45.0,
        "dispersal_fat_tail_p": 2.1,
        "leaf_litter_bulk_density": 18.0,
        "flammability": 0.72,
    },
    {
        "species_id": 1,
        "name": "Shade-Tolerant Hardwood",
        "pft": "shade_tolerant_hardwood",
        "d_max_cm": 85.0,
        "h_max_m": 34.0,
        "age_max_yr": 280,
        "g_max_cm_yr": 0.58,
        "specific_leaf_area": 14.5,
        "wood_density_kg_m3": 610.0,
        "shade_tolerance": 4.7,
        "light_compensation_frac": 0.04,
        "light_saturation_frac": 0.52,
        "gdd_min": 900.0,
        "gdd_max": 2400.0,
        "drought_tolerance": 0.55,
        "frost_tolerance": 145.0,
        "background_mortality_yr": 0.009,
        "stress_mortality_threshold": 0.34,
        "stress_mortality_rate": 0.20,
        "maturity_age_yr": 24,
        "fecundity_seeds_yr": 900.0,
        "seed_mass_g": 1.2,
        "dispersal_mean_m": 28.0,
        "dispersal_fat_tail_p": 2.8,
        "leaf_litter_bulk_density": 27.0,
        "flammability": 0.32,
    },
    {
        "species_id": 2,
        "name": "Shade-Intolerant Hardwood",
        "pft": "shade_intolerant_hardwood",
        "d_max_cm": 78.0,
        "h_max_m": 31.0,
        "age_max_yr": 180,
        "g_max_cm_yr": 0.82,
        "specific_leaf_area": 13.0,
        "wood_density_kg_m3": 540.0,
        "shade_tolerance": 2.1,
        "light_compensation_frac": 0.12,
        "light_saturation_frac": 0.78,
        "gdd_min": 800.0,
        "gdd_max": 2800.0,
        "drought_tolerance": 0.50,
        "frost_tolerance": 130.0,
        "background_mortality_yr": 0.013,
        "stress_mortality_threshold": 0.39,
        "stress_mortality_rate": 0.24,
        "maturity_age_yr": 14,
        "fecundity_seeds_yr": 2100.0,
        "seed_mass_g": 0.9,
        "dispersal_mean_m": 38.0,
        "dispersal_fat_tail_p": 2.2,
        "leaf_litter_bulk_density": 22.0,
        "flammability": 0.46,
    },
    {
        "species_id": 3,
        "name": "Pioneer Hardwood",
        "pft": "pioneer_hardwood",
        "d_max_cm": 62.0,
        "h_max_m": 26.0,
        "age_max_yr": 120,
        "g_max_cm_yr": 1.15,
        "specific_leaf_area": 16.0,
        "wood_density_kg_m3": 470.0,
        "shade_tolerance": 1.1,
        "light_compensation_frac": 0.20,
        "light_saturation_frac": 0.88,
        "gdd_min": 700.0,
        "gdd_max": 3000.0,
        "drought_tolerance": 0.45,
        "frost_tolerance": 120.0,
        "background_mortality_yr": 0.022,
        "stress_mortality_threshold": 0.45,
        "stress_mortality_rate": 0.30,
        "maturity_age_yr": 8,
        "fecundity_seeds_yr": 3200.0,
        "seed_mass_g": 0.5,
        "dispersal_mean_m": 55.0,
        "dispersal_fat_tail_p": 1.9,
        "leaf_litter_bulk_density": 16.0,
        "flammability": 0.50,
    },
    {
        "species_id": 4,
        "name": "Subcanopy Specialist",
        "pft": "subcanopy_specialist",
        "d_max_cm": 38.0,
        "h_max_m": 18.0,
        "age_max_yr": 160,
        "g_max_cm_yr": 0.45,
        "specific_leaf_area": 18.0,
        "wood_density_kg_m3": 590.0,
        "shade_tolerance": 5.0,
        "light_compensation_frac": 0.03,
        "light_saturation_frac": 0.45,
        "gdd_min": 850.0,
        "gdd_max": 2200.0,
        "drought_tolerance": 0.48,
        "frost_tolerance": 150.0,
        "background_mortality_yr": 0.014,
        "stress_mortality_threshold": 0.32,
        "stress_mortality_rate": 0.18,
        "maturity_age_yr": 18,
        "fecundity_seeds_yr": 700.0,
        "seed_mass_g": 1.5,
        "dispersal_mean_m": 18.0,
        "dispersal_fat_tail_p": 3.0,
        "leaf_litter_bulk_density": 24.0,
        "flammability": 0.24,
    },
]


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise FileNotFoundError("Could not locate project root from package path")


def default_species_asset_path() -> Path:
    # TODO: The default asset currently points at an eastern-US PFT file even
    # though the product framing and literature review are Pacific Northwest
    # leaning. Replace this with a regionally appropriate default or require an
    # explicit site/species asset at runtime.
    return _project_root() / "data" / "species" / "eastern_us_pfts.json"


def load_species_table(path: str | Path | None = None) -> List[SpeciesParams]:
    """Load a species/PFT table from JSON."""

    species_path = Path(path) if path is not None else default_species_asset_path()
    if species_path.exists():
        payload = json.loads(species_path.read_text())
    else:
        payload = _DEFAULT_SPECIES_PAYLOAD
    return [SpeciesParams(**record) for record in payload]


def write_species_table(path: str | Path, records: Iterable[SpeciesParams]) -> None:
    """Persist species parameters as JSON."""

    serialized = [asdict(record) for record in records]
    Path(path).write_text(json.dumps(serialized, indent=2) + "\n")


def default_species_table() -> List[SpeciesParams]:
    """Return the canonical 5-PFT parameter table."""

    return load_species_table()
