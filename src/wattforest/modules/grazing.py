"""Grazing module scaffold."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np


class GrazingModule:
    def __init__(self):
        self.active_grazing: Dict[Tuple[int, int], float] = {}

    def activate(self, mask: np.ndarray, intensity: float) -> None:
        for row in range(mask.shape[0]):
            for col in range(mask.shape[1]):
                if mask[row, col]:
                    self.active_grazing[(row, col)] = intensity

    def deactivate(self, mask: np.ndarray) -> None:
        for row in range(mask.shape[0]):
            for col in range(mask.shape[1]):
                if mask[row, col]:
                    self.active_grazing.pop((row, col), None)

    def recruitment_modifier(self, row: int, col: int) -> float:
        intensity = self.active_grazing.get((row, col), 0.0)
        return max(0.05, 1.0 - 0.9 * intensity)
