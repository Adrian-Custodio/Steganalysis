"""
RS (Regular-Singular) Analysis for LSB steganography detection (Fridrich,
Goljan & Du, 2001). More robust than chi-square, more compute-intensive.
Flips pixel groups under a mask and its negation, then scores the
image by how asymmetric the resulting Regular/Singular ratios are.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.analysis.utils import score_to_verdict

GROUP_SIZE = 4

# Scales raw asymmetry (clean images sit well under 0.5) to a 0-1 score.
# Empirically chosen against test fixtures, not analytically derived.
ASYMMETRY_CALIBRATION = 0.35


@dataclass
class RSResult:
    """Aggregated RS analysis result for one channel or whole image."""

    score: float  # 0-1, scaled RM/-M vs SM/-M asymmetry
    verdict: str
    explanation: str
    rm: float = 0.0
    sm: float = 0.0
    r_neg_m: float = 0.0
    s_neg_m: float = 0.0
    total_groups: int = 0


def _flip_f1(group: np.ndarray) -> np.ndarray:
    """F1: toggle the LSB of every value. Pairs (0,1),(2,3),...,(254,255)."""
    return (group ^ 1).astype(group.dtype)


def _flip_f_neg1(group: np.ndarray) -> np.ndarray:
    """F(-1): shifted LSB flip. Pairs (1,2),(3,4),...; 0 and 255 unchanged."""
    even = group % 2 == 0
    at_zero = group == 0
    at_max = group == 255
    return np.where(
        even,
        np.where(at_zero, group, group - 1),
        np.where(at_max, group, group + 1),
    ).astype(group.dtype)


def _discrimination(group: np.ndarray) -> int:
    """f(G) = sum of absolute differences between adjacent pixels."""
    diffs = np.abs(np.diff(group.astype(int)))
    return int(diffs.sum())


def _default_mask(group_size: int) -> np.ndarray:
    """Standard mask from Fridrich et al.: flip first/last pixel of a group."""
    mask = np.zeros(group_size, dtype=int)
    mask[0] = 1
    mask[-1] = 1
    return mask


def _apply_mask(group: np.ndarray, mask: np.ndarray, sign: int) -> np.ndarray:
    """Apply mask*sign to group: +1 -> F1, -1 -> F(-1), 0 -> unchanged."""
    effective = mask * sign
    flipped = group.copy()
    flipped = np.where(effective == 1, _flip_f1(group), flipped)
    flipped = np.where(effective == -1, _flip_f_neg1(group), flipped)
    return flipped


def _classify(group: np.ndarray, mask: np.ndarray, sign: int) -> str:
    """Classify a group as Regular, Singular, or Unusable."""
    f_before = _discrimination(group)
    f_after = _discrimination(_apply_mask(group, mask, sign))
    if f_after > f_before:
        return "R"
    if f_after < f_before:
        return "S"
    return "U"


def _make_groups(channel: np.ndarray, group_size: int) -> list[np.ndarray]:
    """Flatten and split into non-overlapping groups, dropping any remainder."""
    flat = channel.flatten()
    num_groups = len(flat) // group_size
    return [flat[i * group_size : (i + 1) * group_size] for i in range(num_groups)]


def rs_analysis_channel(channel: np.ndarray, group_size: int = GROUP_SIZE) -> RSResult:
    """Run RS analysis on a single-channel (H, W) array."""
    groups = _make_groups(channel, group_size)
    mask = _default_mask(group_size)

    if not groups:
        return RSResult(
            score=0.0,
            verdict=score_to_verdict(0.0),
            explanation="Image too small to analyze.",
        )

    rm = sm = r_neg_m = s_neg_m = 0
    for group in groups:
        c_pos = _classify(group, mask, sign=1)
        c_neg = _classify(group, mask, sign=-1)
        if c_pos == "R":
            rm += 1
        elif c_pos == "S":
            sm += 1
        if c_neg == "R":
            r_neg_m += 1
        elif c_neg == "S":
            s_neg_m += 1

    total = len(groups)
    rm_pct, sm_pct = rm / total, sm / total
    r_neg_pct, s_neg_pct = r_neg_m / total, s_neg_m / total

    asymmetry = abs(rm_pct - r_neg_pct) + abs(sm_pct - s_neg_pct)
    score = min(asymmetry / ASYMMETRY_CALIBRATION, 1.0)
    verdict = score_to_verdict(score)

    explanation = (
        f"RM={rm_pct:.1%}, R-M={r_neg_pct:.1%}, SM={sm_pct:.1%}, "
        f"S-M={s_neg_pct:.1%} across {total} groups "
        f"(asymmetry {asymmetry:.3f}); clean images keep RM~=R-M and SM~=S-M."
    )

    return RSResult(
        score=score,
        verdict=verdict,
        explanation=explanation,
        rm=rm_pct,
        sm=sm_pct,
        r_neg_m=r_neg_pct,
        s_neg_m=s_neg_pct,
        total_groups=total,
    )


def rs_analysis_image(channels: list[np.ndarray], group_size: int = GROUP_SIZE) -> RSResult:
    """Run RS analysis across all channels; combined score is the mean."""
    channel_results = [rs_analysis_channel(c, group_size) for c in channels]
    score = float(np.mean([r.score for r in channel_results]))
    verdict = score_to_verdict(score)

    per_channel_summary = ", ".join(
        f"ch{i}={r.score:.0%}" for i, r in enumerate(channel_results)
    )
    explanation = (
        f"RS analysis: {score:.0%} suspicion (avg across channels) based on "
        f"asymmetry between R/S group ratios under mask M vs. -M. "
        f"Per-channel: {per_channel_summary}."
    )

    return RSResult(
        score=score,
        verdict=verdict,
        explanation=explanation,
        total_groups=sum(r.total_groups for r in channel_results),
    )
