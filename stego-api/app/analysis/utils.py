"""
Shared image-loading and bit-plane helpers used by both detection methods
(chi_square.py, rs_analysis.py) and by the API layer for building the
`bit_plane_preview` visualization.

Kept separate from the detection algorithms so those modules can stay focused
on the statistics, and so this I/O logic is tested/reused in one place.
"""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.config import settings


class ImageLoadError(ValueError):
    """Raised when uploaded bytes can't be decoded as a supported image."""


def load_image_from_bytes(data: bytes) -> Image.Image:
    """Decode raw file bytes into a Pillow Image.

    Raises ImageLoadError (rather than letting PIL's exception leak) so the
    API layer can catch one well-defined error type and turn it into a 400.
    """
    try:
        image = Image.open(io.BytesIO(data))
        image.load()  # force decode now, so truncated/corrupt files fail here
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageLoadError(f"Could not decode image: {exc}") from exc
    return image


def image_to_array(image: Image.Image) -> np.ndarray:
    """Convert a Pillow Image to a numpy array of shape (H, W, C).

    Normalizes to RGB so downstream code can always assume 3 channels,
    regardless of whether the source was RGB, RGBA, L (grayscale), or P
    (palette). Alpha (if present) is dropped — LSB steganography in alpha
    channels is out of scope for this tool.
    """
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    array = np.array(image)
    if array.ndim == 2:  # grayscale -> add a channel axis, then replicate to 3
        array = np.stack([array] * 3, axis=-1)
    return array


def split_channels(array: np.ndarray) -> list[np.ndarray]:
    """Split an (H, W, C) array into a list of (H, W) single-channel arrays."""
    return [array[:, :, c] for c in range(array.shape[-1])]


def extract_lsb_plane(channel: np.ndarray) -> np.ndarray:
    """Extract the least-significant-bit plane of a single-channel array.

    Returns an array of the same (H, W) shape with values in {0, 1} —
    each pixel's LSB. This is the plane LSB steganography writes payload
    bits into, and what the chi-square/RS methods analyze for statistical
    anomalies.
    """
    return (channel & 1).astype(np.uint8)


def lsb_plane_to_png_base64(plane: np.ndarray) -> str:
    """Render an LSB bit-plane (values in {0, 1}) as a black/white PNG,
    base64-encoded, for embedding directly in a JSON response.

    Scaling 0/1 -> 0/255 makes the bit pattern visible to the human eye
    (a raw 0/1 image would render as solid black).
    """
    visible = (plane * 255).astype(np.uint8)
    image = Image.fromarray(visible, mode="L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def score_to_verdict(score: float) -> str:
    """Map a 0-1 suspicion score to a verdict label using the shared
    heuristic thresholds in config.py, so chi-square and RS analysis (and
    the overall verdict) all classify consistently.
    """
    if score < settings.SUSPICIOUS_THRESHOLD:
        return "clean"
    if score < settings.STEGO_THRESHOLD:
        return "suspicious"
    return "likely_stego"


def validate_and_load(data: bytes, max_bytes: int) -> Image.Image:
    """Convenience wrapper: enforce the size limit, then decode.

    Size is checked before decoding since decoding is the more expensive
    step — no point spending CPU on a file we're going to reject anyway.
    """
    if len(data) > max_bytes:
        raise ImageLoadError(
            f"File too large: {len(data)} bytes exceeds the {max_bytes}-byte limit."
        )
    if len(data) == 0:
        raise ImageLoadError("Uploaded file is empty.")
    return load_image_from_bytes(data)
