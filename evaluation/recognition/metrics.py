"""Verification metrics from genuine / impostor similarity scores (higher = more similar).

FAR(t) = fraction of impostor pairs with score >= t   (false accept rate)
FRR(t) = fraction of genuine pairs with score < t     (false reject rate)
TAR(t) = 1 - FRR(t)
"""
from __future__ import annotations

import numpy as np


def far_frr(genuine: np.ndarray, impostor: np.ndarray, thresholds: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    g = np.sort(genuine)
    i = np.sort(impostor)
    frr = np.searchsorted(g, thresholds, side="left") / len(g)
    far = 1.0 - np.searchsorted(i, thresholds, side="left") / len(i)
    return far, frr


def threshold_at_far(impostor: np.ndarray, target_far: float) -> float:
    """Smallest threshold whose FAR <= target_far (ties resolved conservatively)."""
    i = np.sort(impostor)[::-1]
    k = int(np.floor(target_far * len(i)))  # number of impostors allowed at or above threshold
    if k >= len(i):
        return float(i[-1])
    # accept at most k impostors: threshold just above the (k+1)-th highest impostor score
    return float(np.nextafter(i[k], np.inf))


def eer(genuine: np.ndarray, impostor: np.ndarray) -> tuple[float, float]:
    t = np.unique(np.concatenate([genuine, impostor]))
    far, frr = far_frr(genuine, impostor, t)
    idx = int(np.argmin(np.abs(far - frr)))
    return float((far[idx] + frr[idx]) / 2), float(t[idx])


def best_accuracy_threshold(genuine: np.ndarray, impostor: np.ndarray) -> tuple[float, float]:
    t = np.unique(np.concatenate([genuine, impostor]))
    far, frr = far_frr(genuine, impostor, t)
    n_g, n_i = len(genuine), len(impostor)
    acc = ((1 - frr) * n_g + (1 - far) * n_i) / (n_g + n_i)
    idx = int(np.argmax(acc))
    return float(acc[idx]), float(t[idx])
