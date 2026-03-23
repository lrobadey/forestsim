"""Notebook-friendly timeline summaries."""

from __future__ import annotations

from typing import Any


def build_timeline(engine) -> dict[str, Any]:
    """Return a serializable summary of the engine history."""

    return {
        "years": [record.year for record in engine.history],
        "records": [
            {
                "year": record.year,
                "total_biomass_kg": record.total_biomass_kg,
                "mean_canopy_height_m": record.mean_canopy_height_m,
                "fraction_in_gaps": record.fraction_in_gaps,
                "n_gaps": record.n_gaps,
            }
            for record in engine.history
        ],
    }

