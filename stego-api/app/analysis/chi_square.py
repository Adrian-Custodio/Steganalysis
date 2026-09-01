"""
Chi-square attack for LSB steganography detection.

Based on Westfeld & Pfitzmann's "Attacks on Steganographic Systems" (2000).
This module implements the classic "pairs of values" (PoV) chi-square test.

--- The math, in plain-ish terms ---

Naive LSB embedding replaces each pixel's least-significant bit with a
payload bit. Over a large embedded region this has a specific side effect:
it pulls the frequencies of each "pair of values" (2k, 2k+1) — e.g. pixel
values 4 and 5, or 118 and 119 — toward each other.

Why: flipping a pixel's LSB moves its value between 2k and 2k+1 and nowhere
else (4 <-> 5, but never 4 <-> 6). If payload bits are ~50/50 ones and
zeros (true of most real payloads, and certainly of random/encrypted data),
then after embedding, roughly half of the original 2k-or-2k+1 pixels end up
as 2k and half as 2k+1 — regardless of how skewed the *original* histogram
was. So h(2k) and h(2k+1) get pulled toward their shared average.

A natural (non-stego) photo has no reason for h(2k) ~= h(2k+1); one value
in a pair is often meaningfully more common than the other (e.g. smooth
gradients favor certain values). So: if a channel's pair frequencies look
suspiciously *equal*, that's evidence of LSB embedding.

We test this statistically with a chi-square goodness-of-fit test:

    - Null hypothesis (H0): h(2k) and h(2k+1) are drawn from a distribution
      where both categories have the same expected frequency
      (i.e. "this histogram already looks embedded").
    - For each pair-category k, the expected frequency under H0 is the
      average of the pair:   expected_k = (h(2k) + h(2k+1)) / 2
    - The observed frequency we compare against is h(2k).
    - chi2 = sum_k  (observed_k - expected_k)^2 / expected_k
    - degrees of freedom = (number of valid categories) - 1
    - p-value = P(X >= chi2) under a chi2 distribution with that many
      degrees of freedom  (scipy.stats.chi2.sf, the survival function)

A HIGH p-value (close to 1) means the observed histogram is a good fit for
the "already-equalized" hypothesis -> evidence FOR embedding.
A LOW p-value means the pair frequencies are clearly unequal, as you'd
expect from an untouched natural image -> evidence AGAINST embedding.
(Note this is the opposite of the usual "low p-value = reject H0 = something
unusual is going on" intuition — here H0 *is* "stego is present", so a good
fit supports it. This trips people up, so it's called out explicitly.)

We run this test over sequential, non-overlapping blocks of pixels rather
than the whole channel at once, because embedding rarely fills 100% of an
image — running it block-by-block lets us see *how much* of the image
looks embedded, not just whether any of it does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from app.analysis.utils import score_to_verdict

# A category (pair) is only included in the test if its expected frequency
# meets this minimum. Chi-square goodness-of-fit is unreliable for very
# small expected counts (a standard rule of thumb is >= 5); pairs below
# this are just noise (e.g. in a small block or a rarely-used pixel value)
# and would otherwise distort the statistic.
MIN_EXPECTED_FREQUENCY = 4.0

# p-value above which a block is considered to "trigger" (look embedded).
# 0.5 is a common choice in chi-square-attack implementations: it's the
# point at which the equalized-histogram hypothesis becomes more plausible
# than not.
P_VALUE_TRIGGER_THRESHOLD = 0.5

DEFAULT_BLOCK_SIZE = 2048


@dataclass
class BlockResult:
    """Chi-square test result for one contiguous block of pixels."""

    chi_square_stat: float
    p_value: float
    degrees_of_freedom: int
    triggered: bool  # p_value > P_VALUE_TRIGGER_THRESHOLD


@dataclass
class ChiSquareResult:
    """Aggregated chi-square attack result for one channel or whole image."""

    score: float  # 0-1, fraction of blocks that "triggered"
    verdict: str
    explanation: str
    block_results: list[BlockResult] = field(default_factory=list, repr=False)
    mean_p_value: float = 0.0


def _chi_square_test_block(pixel_values: np.ndarray) -> BlockResult:
    """Run the pairs-of-values chi-square test on one block of pixel values
    (a 1D array of uint8 values from a single channel).
    """
    # Histogram over all 256 possible byte values.
    counts, _ = np.histogram(pixel_values, bins=256, range=(0, 256))

    chi_square_stat = 0.0
    degrees_of_freedom = 0

    # k indexes pairs (2k, 2k+1) for k in 0..127.
    for k in range(128):
        h_even = counts[2 * k]
        h_odd = counts[2 * k + 1]
        expected = (h_even + h_odd) / 2.0

        if expected < MIN_EXPECTED_FREQUENCY:
            continue  # skip unreliable categories, per MIN_EXPECTED_FREQUENCY

        chi_square_stat += (h_even - expected) ** 2 / expected
        degrees_of_freedom += 1

    degrees_of_freedom = max(degrees_of_freedom - 1, 1)

    # Survival function P(X >= chi_square_stat) for a chi2(df) distribution.
    p_value = float(stats.chi2.sf(chi_square_stat, degrees_of_freedom))

    return BlockResult(
        chi_square_stat=chi_square_stat,
        p_value=p_value,
        degrees_of_freedom=degrees_of_freedom,
        triggered=p_value > P_VALUE_TRIGGER_THRESHOLD,
    )


def chi_square_attack_channel(
    channel: np.ndarray, block_size: int = DEFAULT_BLOCK_SIZE
) -> ChiSquareResult:
    """Run the chi-square attack on a single-channel (H, W) numpy array.

    The channel is flattened in row-major order and split into
    non-overlapping blocks of `block_size` pixels. Each block gets its own
    chi-square test (see module docstring); the final score is the fraction
    of blocks whose p-value exceeds P_VALUE_TRIGGER_THRESHOLD, i.e. the
    proportion of the image that statistically "looks embedded".

    A trailing partial block smaller than block_size is dropped rather than
    tested, since a too-small sample makes the test unreliable (see
    MIN_EXPECTED_FREQUENCY).
    """
    flat = channel.flatten()
    num_blocks = len(flat) // block_size

    if num_blocks == 0:
        # Image too small for even one block at this block_size — treat as
        # a single block using whatever pixels we have, so tiny test
        # fixtures/thumbnails still produce a result instead of an error.
        blocks = [flat] if len(flat) > 0 else []
    else:
        blocks = [
            flat[i * block_size : (i + 1) * block_size] for i in range(num_blocks)
        ]

    block_results = [_chi_square_test_block(block) for block in blocks]

    if not block_results:
        return ChiSquareResult(
            score=0.0,
            verdict=score_to_verdict(0.0),
            explanation="Image too small to analyze.",
            block_results=[],
        )

    triggered_count = sum(1 for b in block_results if b.triggered)
    score = triggered_count / len(block_results)
    mean_p_value = float(np.mean([b.p_value for b in block_results]))

    verdict = score_to_verdict(score)
    explanation = (
        f"{triggered_count}/{len(block_results)} blocks "
        f"({score:.0%}) showed pair-of-values frequencies statistically "
        f"consistent with LSB embedding (mean p-value {mean_p_value:.2f})."
    )

    return ChiSquareResult(
        score=score,
        verdict=verdict,
        explanation=explanation,
        block_results=block_results,
        mean_p_value=mean_p_value,
    )


def chi_square_attack_image(
    channels: list[np.ndarray], block_size: int = DEFAULT_BLOCK_SIZE
) -> ChiSquareResult:
    """Run the chi-square attack across all color channels of an image and
    combine them into a single result.

    The combined score is the mean of the per-channel scores — a channel
    that's clean pulls the overall score down, one that's saturated with
    embedding pulls it up, which matches how naive RGB LSB embedding
    usually spreads payload roughly evenly across channels.
    """
    channel_results = [chi_square_attack_channel(c, block_size) for c in channels]
    score = float(np.mean([r.score for r in channel_results]))
    mean_p_value = float(np.mean([r.mean_p_value for r in channel_results]))
    verdict = score_to_verdict(score)

    per_channel_summary = ", ".join(
        f"ch{i}={r.score:.0%}" for i, r in enumerate(channel_results)
    )
    explanation = (
        f"Chi-square attack: {score:.0%} of blocks (avg across channels) "
        f"matched the equalized-histogram pattern typical of LSB embedding "
        f"(mean p-value {mean_p_value:.2f}). Per-channel: {per_channel_summary}."
    )

    return ChiSquareResult(
        score=score,
        verdict=verdict,
        explanation=explanation,
        block_results=[b for r in channel_results for b in r.block_results],
        mean_p_value=mean_p_value,
    )
