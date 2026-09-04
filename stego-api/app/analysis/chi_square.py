"""
Chi-square attack for LSB steganography detection (Westfeld & Pfitzmann,
2000). Tests whether pixel "pairs of values" (2k, 2k+1) have been
equalized in frequency, a side effect of naive LSB embedding.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from app.analysis.utils import score_to_verdict

# Min expected frequency for a pair category to be included (rule of thumb: >= 5).
MIN_EXPECTED_FREQUENCY = 4.0

# p-value above which a block "triggers" (looks embedded).
P_VALUE_TRIGGER_THRESHOLD = 0.5

DEFAULT_BLOCK_SIZE = 2048


@dataclass
class BlockResult:
    """Chi-square test result for one block of pixels."""

    chi_square_stat: float
    p_value: float
    degrees_of_freedom: int
    triggered: bool


@dataclass
class ChiSquareResult:
    """Aggregated chi-square result for one channel or whole image."""

    score: float  # 0-1, fraction of blocks that triggered
    verdict: str
    explanation: str
    block_results: list[BlockResult] = field(default_factory=list, repr=False)
    mean_p_value: float = 0.0


def _chi_square_test_block(pixel_values: np.ndarray) -> BlockResult:
    """Run the pairs-of-values chi-square test on one block (1D uint8 array)."""
    counts, _ = np.histogram(pixel_values, bins=256, range=(0, 256))

    chi_square_stat = 0.0
    degrees_of_freedom = 0

    for k in range(128):
        h_even = counts[2 * k]
        h_odd = counts[2 * k + 1]
        expected = (h_even + h_odd) / 2.0

        if expected < MIN_EXPECTED_FREQUENCY:
            continue

        chi_square_stat += (h_even - expected) ** 2 / expected
        degrees_of_freedom += 1

    degrees_of_freedom = max(degrees_of_freedom - 1, 1)
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
    """Run the chi-square attack on a single-channel (H, W) array, block by block.
    Score = fraction of blocks whose p-value crosses the trigger threshold.
    """
    flat = channel.flatten()
    num_blocks = len(flat) // block_size

    if num_blocks == 0:
        # too small for one full block — use whatever pixels we have
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
    """Run the chi-square attack across all channels; combined score is the mean."""
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
