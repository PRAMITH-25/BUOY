"""
Deterministic random seed manager for reproducible experiments.
"""
import random
import numpy as np

DEFAULT_RANDOM_SEED = 42

class ReproducibleRNG:
    def __init__(self, seed: int = DEFAULT_RANDOM_SEED):
        self._seed = seed
        self._py_rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)

    def reseed(self, seed: int):
        self._seed = seed
        self._py_rng.seed(seed)
        self._np_rng = np.random.default_rng(seed)

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def py(self) -> random.Random:
        return self._py_rng

    @property
    def np(self) -> np.random.Generator:
        return self._np_rng

global_rng = ReproducibleRNG()
