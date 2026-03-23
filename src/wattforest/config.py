"""Simulation configuration primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass(frozen=True)
class LandscapeConfig:
    """Immutable landscape geometry."""

    extent_m: Tuple[float, float]
    cell_size_m: float
    origin_utm: Tuple[float, float]
    epsg: int

    @property
    def shape(self) -> Tuple[int, int]:
        return (
            int(np.ceil(self.extent_m[1] / self.cell_size_m)),
            int(np.ceil(self.extent_m[0] / self.cell_size_m)),
        )

    @property
    def n_cells(self) -> int:
        rows, cols = self.shape
        return rows * cols
