import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probes.intervention_ops import (
    ablate_to_target,
    diff_of_means_direction,
    find_subsequence,
    mean_projection,
    probe_logit,
    random_unit_direction,
    raw_unit_direction,
)


def test_ablation_sets_projection_to_target():
    h = np.array([3.0, 4.0, 0.0])
    d = np.array([1.0, 0.0, 0.0])
    out = ablate_to_target(h, d, target_proj=1.0)
    assert np.isclose(np.dot(out, d), 1.0)
    assert np.allclose(out[1:], h[1:])


def test_ablation_drives_probe_logit_to_benign_baseline():
    rng = np.random.default_rng(0)
    coef = rng.standard_normal(16)
    scale = np.abs(rng.standard_normal(16)) + 0.5
    mean = rng.standard_normal(16)
    d = raw_unit_direction(coef, scale)
    benign = rng.standard_normal((20, 16))
    target = mean_projection(benign, d)
    benign_logit = float(np.mean([probe_logit(b, coef, mean, scale, 0.0) for b in benign]))
    offensive = rng.standard_normal(16) + 5 * d
    ablated = ablate_to_target(offensive, d, target)
    assert np.isclose(probe_logit(ablated, coef, mean, scale, 0.0), benign_logit, atol=1e-06)


def test_random_direction_barely_moves_probe_logit():
    rng = np.random.default_rng(1)
    coef = rng.standard_normal(64)
    scale = np.abs(rng.standard_normal(64)) + 0.5
    mean = rng.standard_normal(64)
    d_probe = raw_unit_direction(coef, scale)
    h = rng.standard_normal(64) + 5 * d_probe
    before = probe_logit(h, coef, mean, scale, 0.0)
    r = random_unit_direction(64, seed=2)
    ablated_random = ablate_to_target(
        h, r, target_proj=mean_projection(rng.standard_normal((20, 64)), r)
    )
    after = probe_logit(ablated_random, coef, mean, scale, 0.0)
    probe_ablated = ablate_to_target(h, d_probe, target_proj=0.0)
    assert abs(after - before) < abs(probe_logit(probe_ablated, coef, mean, scale, 0.0) - before)


def test_random_unit_direction_is_unit_and_deterministic():
    a = random_unit_direction(128, seed=7)
    b = random_unit_direction(128, seed=7)
    assert np.isclose(np.linalg.norm(a), 1.0)
    assert np.allclose(a, b)


def test_diff_of_means_points_offensive_minus_benign():
    mu_off = np.array([2.0, 0.0, 0.0])
    mu_ben = np.array([0.0, 0.0, 0.0])
    d = diff_of_means_direction(mu_off, mu_ben)
    assert np.allclose(d, [1.0, 0.0, 0.0])
    assert np.isclose(np.linalg.norm(d), 1.0)


def test_diff_of_means_raises_when_means_coincide():
    import pytest

    with pytest.raises(ValueError):
        diff_of_means_direction(np.ones(3), np.ones(3))


def test_find_subsequence_locates_span():
    hay = [10, 11, 12, 13, 14, 15]
    assert find_subsequence(hay, [12, 13, 14]) == (2, 5)
    assert find_subsequence(hay, [10]) == (0, 1)


def test_find_subsequence_absent_or_empty():
    assert find_subsequence([1, 2, 3], [9, 9]) is None
    assert find_subsequence([1, 2, 3], []) is None
    assert find_subsequence([1, 2], [1, 2, 3]) is None
