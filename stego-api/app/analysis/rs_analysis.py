"""
RS (Regular-Singular) Analysis for LSB steganography detection.

Based on Fridrich, Goljan & Du, "Reliable Detection of LSB Steganography in
Color and Grayscale Images" (2001). More robust than the chi-square attack
(handles noisier, more "natural" images better — see chi_square.py's
docstring for that method's weak spot), at the cost of more compute per
pixel (every group is flipped and re-scored, twice).

--- The math, in plain-ish terms ---

Split a channel into small, non-overlapping groups of `n` adjacent pixels
(n=4 here, e.g. 4 consecutive pixels in scan order). For each group, define
a "discrimination function" that measures how noisy/rough it is:

    f(G) = sum of |pixel[i+1] - pixel[i]|   for adjacent pixels in the group

Smooth groups have a low f(G); noisy ones have a high f(G).

Now define two "flipping" operations on pixel values:
    F1(x)   : toggles the LSB          -> pairs (0,1),(2,3),(4,5),...
    F(-1)(x): shifts LSB the other way -> pairs (1,2),(3,4),(5,6),...
(F1 is exactly the LSB-flip an embedder performs; F(-1) is a control that
flips pixels similarly but along the *other* set of pairs, used as a
contrast to F1 rather than to simulate embedding.)

A fixed "mask" pattern (here: flip the first and last pixel in each group
of 4, leave the middle two alone — the standard example from the original
paper) decides which pixels in a group get flipped, and with which
function. Applying the mask with F1 gives a flipped group G_M; applying the
*negated* mask (same positions, F(-1) instead of F1) gives G_{-M}.

Each group is classified by comparing its discrimination value before and
after flipping:
    Regular  (R): f(flipped) > f(original)  — flipping made it noisier
    Singular (S): f(flipped) < f(original)  — flipping made it smoother
    Unusable (U): f(flipped) == f(original)

Doing this across the whole channel gives four percentages: RM%, SM%
(using mask M) and R-M%, S-M% (using the negated mask).

Key insight from the paper: in an *unmodified* image, RM% ≈ R-M% and
SM% ≈ S-M% — flipping with M vs. -M has roughly symmetric effects, because
neither has anything to do with how the image's LSBs were generated.
LSB embedding overwrites LSBs with (close to) random bits, which breaks
that symmetry — RM/R-M and SM/S-M pull apart. So we use the *asymmetry*
between the M and -M statistics as the suspicion signal:

    asymmetry = |RM% - R-M%| + |SM% - S-M%|

A full quantitative RS analysis fits a quadratic to these curves at
several simulated flip rates to *estimate the embedded payload length*.
That's out of scope here (see README limitations) — this simplified
version uses the raw asymmetry, scaled by an empirically-chosen constant,
as a 0-1 suspicion score. Good enough to say "likely tampered", not
precise enough to say "how much".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.analysis.utils import score_to_verdict

GROUP_SIZE = 4

# Heuristic scale factor mapping raw asymmetry (0-2 in theory, but
# clean images sit well under 0.5 in practice) to a 0-1 score. Chosen by
# empirical testing against real clean/stego images (see tests/), not
# derived analytically — documented as heuristic per the spec.
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
    """F1: toggle the LSB of every value. Pairs (0,1),(2,3),...,(254,255).
    Always valid — no boundary cases, since toggling a bit never leaves
    the [0, 255] range.
    """
    return (group ^ 1).astype(group.dtype)


def _flip_f_neg1(group: np.ndarray) -> np.ndarray:
    """F(-1): shifted LSB flip. Pairs (1,2),(3,4),...,(253,254), with 0
    and 255 left unpaired (they'd pair with the out-of-range -1 and 256)
    and so are left unchanged.
    """
    even = group % 2 == 0
    at_zero = group == 0
    at_max = group == 255
    # even, nonzero -> x - 1 ; odd, not 255 -> x + 1 ; boundaries -> unchanged
    return np.where(
        even,
        np.where(at_zero, group, group - 1),
        np.where(at_max, group, group + 1),
    ).astype(group.dtype)


def _discrimination(group: np.ndarray) -> int:
    """f(G) = sum of absolute differences between adjacent pixels in the
    group. Low for smooth groups, high for noisy ones.
    """
    diffs = np.abs(np.diff(group.astype(int)))
    return int(diffs.sum())


def _default_mask(group_size: int) -> np.ndarray:
    """The standard example mask from Fridrich et al. for groups of 4:
    flip the first and last pixel, leave the middle ones untouched
    (i.e. [1, 0, 0, 1]). Generalized to other group sizes the same way.
    """
    mask = np.zeros(group_size, dtype=int)
    mask[0] = 1
    mask[-1] = 1
    return mask


def _apply_mask(group: np.ndarray, mask: np.ndarray, sign: int) -> np.ndarray:
    """Apply `mask` (values in {0, 1}) to `group`, scaled by `sign`
    (+1 or -1). Positions where mask*sign == 1 get F1; where it's -1 get
    F(-1); where it's 0, the pixel is left unchanged.
    """
    effective = mask * sign
    flipped = group.copy()
    flipped = np.where(effective == 1, _flip_f1(group), flipped)
    flipped = np.where(effective == -1, _flip_f_neg1(group), flipped)
    return flipped


def _classify(group: np.ndarray, mask: np.ndarray, sign: int) -> str:
    """Classify one group as Regular, Singular, or Unusable for a given
    mask/sign combination (see module docstring)."""
    f_before = _discrimination(group)
    f_after = _discrimination(_apply_mask(group, mask, sign))
    if f_after > f_before:
        return "R"
    if f_after < f_before:
        return "S"
    return "U"


def _make_groups(channel: np.ndarray, group_size: int) -> list[np.ndarray]:
    """Flatten a channel and split it into non-overlapping groups of
    `group_size` pixels, dropping any trailing partial group."""
    flat = channel.flatten()
    num_groups = len(flat) // group_size
    return [flat[i * group_size : (i + 1) * group_size] for i in range(num_groups)]


def rs_analysis_channel(channel: np.ndarray, group_size: int = GROUP_SIZE) -> RSResult:
    """Run RS analysis on a single-channel (H, W) numpy array.

    Classifies every group under both the mask M and its negation -M,
    then scores the image by how asymmetric the resulting R/S ratios are
    (see module docstring). More compute-intensive than the chi-square
    attack since every group requires two flip-and-rescore passes.
    """
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
    """Run RS analysis across all color channels of an image and combine
    into a single result (mean of per-channel scores — same rationale as
    chi_square_attack_image: naive RGB embedding spreads payload roughly
    evenly across channels).
    """
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
