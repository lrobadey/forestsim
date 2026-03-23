"""Hydrology and river-migration helpers."""

from __future__ import annotations

from typing import Dict

import numpy as np


class HydrologyModule:
    """Event-driven establishment rewrites for river migration."""

    def apply_river_shift(
        self,
        affected_mask: np.ndarray,
        scour_frac: float,
        moisture_bonus: float,
        recruitment_scalar: float,
        river_moisture_bonus: np.ndarray,
        river_recruitment_scalar: np.ndarray,
    ) -> Dict[str, float]:
        rows, cols = np.where(affected_mask)
        river_moisture_bonus[rows, cols] = float(moisture_bonus)
        river_recruitment_scalar[rows, cols] = float(recruitment_scalar)
        return {
            "cells_shifted": float(len(rows)),
            "scour_frac": float(scour_frac),
            "moisture_bonus": float(moisture_bonus),
            "recruitment_scalar": float(recruitment_scalar),
        }
