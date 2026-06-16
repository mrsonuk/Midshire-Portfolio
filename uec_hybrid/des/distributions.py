"""
Probability distributions for service-time sampling.

A spec is either a number (constant) or a dict, e.g.::

    {"dist": "lognormal", "mean": 65, "stdev": 20}   # parameterised by real-world mean/stdev
    {"dist": "exponential", "mean": 12}
    {"dist": "triangular", "low": 5, "mode": 10, "high": 30}
    {"dist": "uniform", "low": 5, "high": 15}
    {"dist": "normal", "mean": 30, "stdev": 10}
    {"dist": "constant", "value": 2}

All draws are clamped to be non-negative (durations cannot be negative).
"""
from __future__ import annotations

from typing import Any

import numpy as np


def sample(rng: np.random.Generator, spec: Any) -> float:
    if spec is None:
        return 0.0
    if isinstance(spec, (int, float)):
        return float(max(0.0, spec))

    dist = str(spec.get("dist", "constant")).lower()
    if dist == "constant":
        return float(max(0.0, spec.get("value", spec.get("mean", 0.0))))
    if dist == "exponential":
        return float(rng.exponential(spec.get("mean", 1.0)))
    if dist == "normal":
        return float(max(0.0, rng.normal(spec.get("mean", 0.0), spec.get("stdev", 0.0))))
    if dist == "uniform":
        return float(rng.uniform(spec.get("low", 0.0), spec.get("high", 1.0)))
    if dist == "triangular":
        return float(rng.triangular(spec["low"], spec["mode"], spec["high"]))
    if dist == "lognormal":
        mean = float(spec.get("mean", 1.0))
        stdev = float(spec.get("stdev", 0.0))
        if mean <= 0:
            return 0.0
        if stdev <= 0:
            return mean
        phi = np.sqrt(stdev ** 2 + mean ** 2)
        mu = np.log(mean ** 2 / phi)
        sigma = np.sqrt(np.log(phi ** 2 / mean ** 2))
        return float(rng.lognormal(mu, sigma))
    raise ValueError(f"Unknown distribution: {dist!r}")
