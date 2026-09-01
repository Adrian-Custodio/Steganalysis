"""
Generates clean + LSB-embedded test fixtures into tests/fixtures/.

Run directly:  python -m tests.generate_test_images

Rather than downloading sample images (network dependency, licensing
ambiguity, non-reproducible), this generates a small set of synthetic
"clean" base images procedurally — varied enough (smooth gradients, sharp
geometric edges, photo-like smoothed noise) to exercise both detection
methods meaningfully, and identical on every machine/run.

The `embed_lsb` function here is a genuine, from-scratch LSB embedder —
not a mock. It's intentionally simple (sequential embedding, no
encryption/spreading) since it exists to *demonstrate* the naive LSB
embedding this tool detects, not to be a robust stego scheme. It's also
reusable as the "try it yourself" payload generator mentioned in the
project README/frontend.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

FIXTURES_DIR = Path(__file__).parent / "fixtures"
IMAGE_SIZE = (512, 512)  # (width, height) — big enough for 50KB payload capacity
PAYLOAD_SIZES_BYTES = (1024, 10 * 1024, 50 * 1024)  # 1KB, 10KB, 50KB
HEADER_BYTES = 4  # 32-bit big-endian payload length, written before the payload


def _bytes_to_bits(data: bytes) -> np.ndarray:
    """Unpack bytes into a 1D array of individual bits (MSB first per byte)."""
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    return np.packbits(bits).tobytes()


def embed_lsb(image_array: np.ndarray, payload: bytes) -> np.ndarray:
    """Embed `payload` into the LSBs of `image_array` (H, W, C uint8).

    Writes a 4-byte big-endian length header followed by the payload,
    sequentially into the LSB of each channel value in row-major order.
    Raises ValueError if the image doesn't have enough capacity.
    """
    header = len(payload).to_bytes(HEADER_BYTES, byteorder="big")
    bits = _bytes_to_bits(header + payload)

    flat = image_array.flatten()
    if len(bits) > flat.size:
        capacity_bytes = flat.size // 8 - HEADER_BYTES
        raise ValueError(
            f"Payload too large: needs {len(payload)} bytes, "
            f"image capacity is ~{capacity_bytes} bytes."
        )

    stego_flat = flat.copy()
    stego_flat[: len(bits)] = (stego_flat[: len(bits)] & 0xFE) | bits
    return stego_flat.reshape(image_array.shape)


def extract_lsb_payload(image_array: np.ndarray) -> bytes:
    """Inverse of embed_lsb: read the length header, then that many bytes
    of payload back out of the LSBs. Included so the embedder is testably
    round-trippable, and reusable by a future "decode" demo endpoint.
    """
    flat = image_array.flatten()
    header_bits = flat[: HEADER_BYTES * 8] & 1
    length = int.from_bytes(_bits_to_bytes(header_bits), byteorder="big")

    total_bits = (HEADER_BYTES + length) * 8
    payload_bits = flat[HEADER_BYTES * 8 : total_bits] & 1
    return _bits_to_bytes(payload_bits)


def _make_gradient_image(seed: int = 1) -> np.ndarray:
    """Smooth diagonal RGB gradient — represents low-noise, highly
    correlated image content (e.g. sky, studio backdrop).

    A *mathematically exact* linear ramp is a pathological case for the
    chi-square attack: linspace-to-uint8 rounding makes every value
    0-255 occur (almost) equally often, which trivially satisfies the
    "pair frequencies are equal" test the attack looks for — a false
    positive that has nothing to do with steganography. A small amount
    of dithering noise breaks that artificial exact-uniformity, the way
    real-world smooth gradients (which are never mathematically perfect
    ramps) do.
    """
    rng = np.random.default_rng(seed)
    w, h = IMAGE_SIZE
    x = np.linspace(0, 255, w, dtype=np.float32)
    y = np.linspace(0, 255, h, dtype=np.float32)
    xv, yv = np.meshgrid(x, y)
    r = xv
    g = yv
    b = (xv + yv) / 2
    ramp = np.stack([r, g, b], axis=-1)
    dither = rng.normal(loc=0.0, scale=1.5, size=ramp.shape)
    return np.clip(ramp + dither, 0, 255).astype(np.uint8)


def _make_shapes_image() -> np.ndarray:
    """Flat-colored geometric shapes on a solid background — represents
    sharp-edged, low-entropy graphic content (e.g. a logo or UI screenshot)."""
    w, h = IMAGE_SIZE
    arr = np.full((h, w, 3), fill_value=(30, 30, 40), dtype=np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]

    circle_mask = (xx - w * 0.3) ** 2 + (yy - h * 0.35) ** 2 < (min(w, h) * 0.2) ** 2
    arr[circle_mask] = (220, 80, 80)

    rect_mask = (xx > w * 0.55) & (xx < w * 0.85) & (yy > h * 0.5) & (yy < h * 0.8)
    arr[rect_mask] = (80, 180, 220)

    return arr


def _make_photo_like_image(seed: int = 0) -> np.ndarray:
    """Smoothed random noise with a coarse low-frequency base — a rough
    stand-in for photographic texture (fine sensor-noise-like detail on
    top of smooth large-scale structure).

    Noise amplitude is kept modest and spatially correlated (blurred
    before adding), similar to real camera sensor noise, rather than raw
    independent per-pixel noise — iid noise at high amplitude pushes
    pair frequencies toward equal almost by construction, which (like the
    exact-linear gradient above) is a synthetic-data artifact that trips
    the chi-square attack for reasons unrelated to steganography. This
    was tuned by comparing against a real downloaded photo, where the
    chi-square attack landed around 0.5 (borderline) on the clean image
    rather than near-certain "likely_stego".
    """
    rng = np.random.default_rng(seed)
    w, h = IMAGE_SIZE

    # Low-frequency base: generate at a small size, then upsample so
    # neighboring pixels are correlated (like real photo structure).
    small = rng.integers(0, 256, size=(h // 32, w // 32, 3), dtype=np.uint8)
    base = np.array(
        Image.fromarray(small, mode="RGB").resize((w, h), Image.BICUBIC)
    ).astype(np.float32)

    # Modest, spatially-correlated noise on top, like sensor noise: a
    # small-amplitude noise field upsampled from a coarser resolution
    # (blurring it slightly) rather than pure per-pixel iid noise.
    noise_small = rng.normal(loc=0.0, scale=3.0, size=(h // 4, w // 4, 3))
    noise = np.array(
        Image.fromarray(
            np.clip(noise_small + 128, 0, 255).astype(np.uint8), mode="RGB"
        ).resize((w, h), Image.BILINEAR)
    ).astype(np.float32) - 128.0

    combined = np.clip(base + noise, 0, 255).astype(np.uint8)
    return combined


def generate_clean_images() -> dict[str, np.ndarray]:
    """Return {name: array} for the base clean images."""
    return {
        "gradient": _make_gradient_image(),
        "shapes": _make_shapes_image(),
        "photo_like": _make_photo_like_image(),
    }


def generate_fixtures(output_dir: Path = FIXTURES_DIR) -> list[Path]:
    """Generate clean + stego fixtures and save them as PNGs.

    Returns the list of file paths written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for name, clean_array in generate_clean_images().items():
        clean_path = output_dir / f"{name}_clean.png"
        Image.fromarray(clean_array, mode="RGB").save(clean_path)
        written.append(clean_path)

        for payload_bytes in PAYLOAD_SIZES_BYTES:
            payload = os.urandom(payload_bytes)
            stego_array = embed_lsb(clean_array, payload)
            size_label = f"{payload_bytes // 1024}kb"
            stego_path = output_dir / f"{name}_stego_{size_label}.png"
            Image.fromarray(stego_array, mode="RGB").save(stego_path)
            written.append(stego_path)

    return written


def main() -> None:
    paths = generate_fixtures()
    print(f"Wrote {len(paths)} fixture images to {FIXTURES_DIR}/:")
    for p in paths:
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
