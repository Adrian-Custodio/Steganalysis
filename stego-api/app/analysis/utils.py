"""Shared image-loading and bit-plane helpers used by the detection
algorithms and the API layer's bit_plane_preview visualization."""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.config import settings


class ImageLoadError(ValueError):
    """Raised when uploaded bytes can't be decoded as a supported image."""


def load_image_from_bytes(data: bytes) -> Image.Image:
    """Decode raw bytes into a Pillow Image, raising ImageLoadError on failure."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()  # force decode now so corrupt files fail here
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageLoadError(f"Could not decode image: {exc}") from exc
    return image


def image_to_array(image: Image.Image) -> np.ndarray:
    """Convert to an (H, W, C) numpy array, normalized to RGB (alpha dropped)."""
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    array = np.array(image)
    if array.ndim == 2:  # grayscale -> replicate to 3 channels
        array = np.stack([array] * 3, axis=-1)
    return array


def split_channels(array: np.ndarray) -> list[np.ndarray]:
    """Split an (H, W, C) array into a list of (H, W) single-channel arrays."""
    return [array[:, :, c] for c in range(array.shape[-1])]


def extract_lsb_plane(channel: np.ndarray) -> np.ndarray:
    """Extract the least-significant-bit plane (values in {0, 1})."""
    return (channel & 1).astype(np.uint8)


def lsb_plane_to_png_base64(plane: np.ndarray) -> str:
    """Render an LSB bit-plane as a base64 black/white PNG (0/1 -> 0/255)."""
    visible = (plane * 255).astype(np.uint8)
    image = Image.fromarray(visible, mode="L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def score_to_verdict(score: float) -> str:
    """Map a 0-1 suspicion score to a verdict label via config.py thresholds."""
    if score < settings.SUSPICIOUS_THRESHOLD:
        return "clean"
    if score < settings.STEGO_THRESHOLD:
        return "suspicious"
    return "likely_stego"


def validate_and_load(data: bytes, max_bytes: int) -> Image.Image:
    """Enforce the size limit, then decode."""
    if len(data) > max_bytes:
        raise ImageLoadError(
            f"File too large: {len(data)} bytes exceeds the {max_bytes}-byte limit."
        )
    if len(data) == 0:
        raise ImageLoadError("Uploaded file is empty.")
    return load_image_from_bytes(data)
