from __future__ import annotations
import numpy as np

def raw_unit_direction(coef: np.ndarray, scale: np.ndarray) -> np.ndarray:
    g = coef / scale
    norm = np.linalg.norm(g)
    if norm == 0:
        raise ValueError('degenerate probe direction (zero norm)')
    return g / norm

def probe_logit(h: np.ndarray, coef: np.ndarray, mean: np.ndarray, scale: np.ndarray, intercept: float) -> float:
    return float(np.dot(coef, (h - mean) / scale) + intercept)

def ablate_to_target(h: np.ndarray, d_unit: np.ndarray, target_proj: float) -> np.ndarray:
    return h - (np.dot(h, d_unit) - target_proj) * d_unit

def mean_projection(residuals: np.ndarray, d_unit: np.ndarray) -> float:
    return float(np.mean(residuals @ d_unit))

def random_unit_direction(dim: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    return v / np.linalg.norm(v)

def find_subsequence(haystack: list[int], needle: list[int]) -> tuple[int, int] | None:
    if not needle or len(needle) > len(haystack):
        return None
    first = needle[0]
    for i in range(len(haystack) - len(needle) + 1):
        if haystack[i] == first and haystack[i:i + len(needle)] == needle:
            return (i, i + len(needle))
    return None

def diff_of_means_direction(mean_offensive: np.ndarray, mean_benign: np.ndarray) -> np.ndarray:
    g = mean_offensive - mean_benign
    norm = np.linalg.norm(g)
    if norm == 0:
        raise ValueError('offensive and benign means coincide')
    return g / norm
