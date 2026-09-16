"""Pure layer-ranking math for depth pruning (no torch).

Block Influence (ShortGPT, arXiv:2403.03853): BI_i = 1 - E_t[cos(x_t^in, x_t^out)] over the
residual stream entering and leaving layer i. Angular distance (Gromov et al.,
arXiv:2403.17887): d_n(l) = E_t[arccos(cos(x_t^(l), x_t^(l+n)))/pi] for a block of n layers
starting at l. Low values mean the layers barely rotate the residual stream and are the
cheapest to remove.
"""

from __future__ import annotations

import math

import numpy as np


def cosine_rows(a: np.ndarray, b: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """Row-wise cosine similarity between two (tokens, hidden) arrays."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    num = (a * b).sum(axis=-1)
    # eps guards zero-norm rows only; adding it would bias identical vectors below cos = 1.
    den = np.maximum(np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1), eps)
    return num / den


def block_influence(layer_in: np.ndarray, layer_out: np.ndarray) -> float:
    """1 - mean cosine between a layer's input and output residual stream."""
    return float(1.0 - cosine_rows(layer_in, layer_out).mean())


def angular_distance(x_a: np.ndarray, x_b: np.ndarray) -> float:
    """Mean arccos(cos)/pi in [0, 1]; 0 = identical direction, 1 = opposite."""
    c = np.clip(cosine_rows(x_a, x_b), -1.0, 1.0)
    return float((np.arccos(c) / math.pi).mean())


def _eligible_range(n_layers: int, protect_first: int, protect_last: int) -> range:
    return range(protect_first, n_layers - protect_last)


def select_contiguous(
    block_distance: dict[int, float],
    n: int,
    n_layers: int,
    protect_first: int,
    protect_last: int,
) -> list[int]:
    """Block [l*, l*+n) with the smallest distance whose layers are all unprotected."""
    eligible = _eligible_range(n_layers, protect_first, protect_last)
    best: tuple[int, float] | None = None
    for start, distance in sorted(block_distance.items()):
        if start not in eligible or (start + n - 1) not in eligible:
            continue
        if best is None or distance < best[1]:
            best = (start, distance)
    if best is None:
        raise ValueError(
            f"no contiguous block of {n} layers fits between layer {protect_first} and "
            f"layer {n_layers - protect_last - 1}"
        )
    return list(range(best[0], best[0] + n))


def select_lowest_bi(
    bi: list[float], n: int, protect_first: int, protect_last: int
) -> list[int]:
    """The n unprotected layers with the smallest Block Influence, ascending by index."""
    eligible = list(_eligible_range(len(bi), protect_first, protect_last))
    if n > len(eligible):
        raise ValueError(f"cannot drop {n} of {len(eligible)} eligible layers")
    chosen = sorted(eligible, key=lambda i: (bi[i], i))[:n]
    return sorted(chosen)


def kept_layer_indices(n_layers: int, drop: list[int]) -> list[int]:
    dropped = set(drop)
    unknown = sorted(i for i in dropped if i < 0 or i >= n_layers)
    if unknown:
        raise ValueError(f"layer indices out of range for {n_layers} layers: {unknown}")
    return [i for i in range(n_layers) if i not in dropped]


def renumber_plan(n_layers: int, drop: list[int]) -> dict[int, int]:
    """Old layer index -> new contiguous index for every kept layer."""
    return {old: new for new, old in enumerate(kept_layer_indices(n_layers, drop))}
