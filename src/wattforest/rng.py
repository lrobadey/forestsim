"""Deterministic random number streams."""

from __future__ import annotations

import hashlib
import json

import numpy as np


class DeterministicRNG:
    """Context-keyed pseudo-random generator."""

    def __init__(self, global_seed: int):
        self.global_seed = global_seed

    def _make_seed(self, *context: object) -> int:
        blob = json.dumps([self.global_seed, *context], sort_keys=True)
        return int(hashlib.sha256(blob.encode()).hexdigest()[:8], 16)

    def uniform(self, *context: object) -> float:
        rng = np.random.Generator(np.random.PCG64(self._make_seed(*context)))
        return float(rng.random())

    def normal(self, mean: float, std: float, *context: object) -> float:
        rng = np.random.Generator(np.random.PCG64(self._make_seed(*context)))
        return float(rng.normal(mean, std))

    def poisson(self, lam: float, *context: object) -> int:
        rng = np.random.Generator(np.random.PCG64(self._make_seed(*context)))
        return int(rng.poisson(lam))

    def cell_stream(self, process: str, year: int, row: int, col: int) -> np.random.Generator:
        return np.random.Generator(np.random.PCG64(self._make_seed(process, year, row, col)))
