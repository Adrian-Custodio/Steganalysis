"""
Test suite for the steganalysis backend.

Run with:  pytest  (from the stego-api/ directory, with requirements-dev.txt
installed)

Fixture images are generated once per test session (see `fixtures_dir`
below) rather than committed as binary files, so the repo stays diffable
and the fixtures are always in sync with the current embedder.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.analysis.chi_square import chi_square_attack_channel, chi_square_attack_image
from app.analysis.rs_analysis import rs_analysis_channel, rs_analysis_image
from app.analysis.utils import (
    extract_lsb_plane,
    image_to_array,
    load_image_from_bytes,
    lsb_plane_to_png_base64,
    score_to_verdict,
    split_channels,
)
from app.config import settings
from app.main import app
from tests.generate_test_images import embed_lsb, extract_lsb_payload, generate_fixtures


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory) -> Path:
    out_dir = tmp_path_factory.mktemp("fixtures")
    generate_fixtures(out_dir)
    return out_dir


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# --------------------------------------------------------------------------
# utils.py
# --------------------------------------------------------------------------


def test_load_image_from_bytes_roundtrip():
    img = Image.new("RGB", (16, 16), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    loaded = load_image_from_bytes(buf.getvalue())
    array = image_to_array(loaded)

    assert array.shape == (16, 16, 3)
    assert (array == [10, 20, 30]).all()


def test_extract_lsb_plane_values_are_binary():
    channel = np.array([[0, 1, 2, 3], [254, 255, 100, 101]], dtype=np.uint8)
    plane = extract_lsb_plane(channel)
    assert set(np.unique(plane)).issubset({0, 1})
    assert (plane == (channel % 2)).all()


def test_lsb_plane_to_png_base64_is_decodable():
    plane = np.array([[0, 1], [1, 0]], dtype=np.uint8)
    b64 = lsb_plane_to_png_base64(plane)
    import base64

    decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert decoded.size == (2, 2)
    assert decoded.mode == "L"


def test_score_to_verdict_thresholds():
    assert score_to_verdict(0.0) == "clean"
    assert score_to_verdict(settings.SUSPICIOUS_THRESHOLD - 0.01) == "clean"
    assert score_to_verdict(settings.SUSPICIOUS_THRESHOLD) == "suspicious"
    assert score_to_verdict(settings.STEGO_THRESHOLD - 0.01) == "suspicious"
    assert score_to_verdict(settings.STEGO_THRESHOLD) == "likely_stego"
    assert score_to_verdict(1.0) == "likely_stego"


# --------------------------------------------------------------------------
# LSB embedder (tests/generate_test_images.py)
# --------------------------------------------------------------------------


def test_embed_and_extract_lsb_roundtrip():
    rng = np.random.default_rng(0)
    image = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    payload = b"hello steganalysis, this is a test payload!"

    stego = embed_lsb(image, payload)
    recovered = extract_lsb_payload(stego)

    assert recovered == payload
    # Embedding should only ever touch LSBs — every value should differ
    # from the original by at most 1.
    assert np.abs(stego.astype(int) - image.astype(int)).max() <= 1


def test_embed_lsb_raises_when_payload_too_large():
    image = np.zeros((4, 4, 3), dtype=np.uint8)  # tiny image, tiny capacity
    with pytest.raises(ValueError):
        embed_lsb(image, b"x" * 1024)


# --------------------------------------------------------------------------
# chi_square.py — synthetic, controlled cases
# --------------------------------------------------------------------------


def test_chi_square_flags_artificially_equalized_histogram():
    """A channel constructed so every pair (2k, 2k+1) has near-identical
    frequency should score high (this is exactly what LSB embedding does
    to a histogram)."""
    rng = np.random.default_rng(1)
    # For each of 128 pair-buckets, assign an equal number of pixels to
    # 2k and 2k+1.
    values = []
    for k in range(128):
        count = 20
        values += [2 * k] * count
        values += [2 * k + 1] * count
    channel = np.array(values, dtype=np.uint8).reshape(-1, 1)

    result = chi_square_attack_channel(channel, block_size=len(values))
    assert result.score > 0.5
    assert result.verdict in ("suspicious", "likely_stego")


def test_chi_square_does_not_flag_skewed_histogram():
    """A channel with a strongly skewed histogram (each pair heavily
    favors one value) should score low."""
    rng = np.random.default_rng(2)
    values = []
    for k in range(128):
        values += [2 * k] * 50  # even value dominates
        values += [2 * k + 1] * 2  # odd value rare
    channel = np.array(values, dtype=np.uint8).reshape(-1, 1)

    result = chi_square_attack_channel(channel, block_size=len(values))
    assert result.score < 0.5


def test_chi_square_attack_image_averages_channels():
    rng = np.random.default_rng(3)
    channels = [rng.integers(0, 256, size=(32, 32), dtype=np.uint8) for _ in range(3)]
    result = chi_square_attack_image(channels, block_size=256)
    assert 0.0 <= result.score <= 1.0
    assert result.verdict in ("clean", "suspicious", "likely_stego")


# --------------------------------------------------------------------------
# rs_analysis.py — synthetic, controlled cases
# --------------------------------------------------------------------------


def test_rs_analysis_scores_full_embed_higher_than_clean():
    rng = np.random.default_rng(4)
    base = np.array(
        Image.fromarray(
            rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8), mode="RGB"
        ).resize((256, 256), Image.BICUBIC)
    )

    clean_channel = base[:, :, 0]
    stego_channel = clean_channel.copy().flatten()
    bits = rng.integers(0, 2, size=stego_channel.size, dtype=np.uint8)
    stego_channel = ((stego_channel & 0xFE) | bits).reshape(clean_channel.shape)

    clean_result = rs_analysis_channel(clean_channel)
    stego_result = rs_analysis_channel(stego_channel)

    assert stego_result.score > clean_result.score


def test_rs_analysis_image_averages_channels():
    rng = np.random.default_rng(5)
    channels = [rng.integers(0, 256, size=(32, 32), dtype=np.uint8) for _ in range(3)]
    result = rs_analysis_image(channels)
    assert 0.0 <= result.score <= 1.0
    assert result.total_groups > 0


# --------------------------------------------------------------------------
# End-to-end against generated fixtures
# --------------------------------------------------------------------------


def test_fixtures_clean_scores_lower_than_heavily_embedded(fixtures_dir):
    clean_path = fixtures_dir / "photo_like_clean.png"
    stego_path = fixtures_dir / "photo_like_stego_50kb.png"

    clean_array = image_to_array(load_image_from_bytes(clean_path.read_bytes()))
    stego_array = image_to_array(load_image_from_bytes(stego_path.read_bytes()))

    clean_chi = chi_square_attack_image(split_channels(clean_array))
    stego_chi = chi_square_attack_image(split_channels(stego_array))
    clean_rs = rs_analysis_image(split_channels(clean_array))
    stego_rs = rs_analysis_image(split_channels(stego_array))

    # RS analysis is the more reliable signal per the README; assert on it
    # directly. Chi-square is checked too but see chi_square.py's docstring
    # re: its weaker discrimination on noisy/photo-like content.
    assert stego_rs.score > clean_rs.score
    assert stego_chi.score >= clean_chi.score


# --------------------------------------------------------------------------
# API routes (main.py)
# --------------------------------------------------------------------------


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_happy_path(client, fixtures_dir):
    image_bytes = (fixtures_dir / "shapes_stego_10kb.png").read_bytes()

    response = client.post(
        "/analyze",
        files={"file": ("shapes_stego_10kb.png", image_bytes, "image/png")},
    )

    assert response.status_code == 200
    body = response.json()

    for key in ("filename", "chi_square", "rs_analysis", "overall_verdict", "bit_plane_preview"):
        assert key in body

    for method_key in ("chi_square", "rs_analysis"):
        method = body[method_key]
        assert 0.0 <= method["score"] <= 1.0
        assert method["verdict"] in ("clean", "suspicious", "likely_stego")
        assert isinstance(method["explanation"], str) and method["explanation"]

    assert body["overall_verdict"] in ("clean", "suspicious", "likely_stego")

    # bit_plane_preview should be valid base64-encoded PNG bytes.
    import base64

    decoded = Image.open(io.BytesIO(base64.b64decode(body["bit_plane_preview"])))
    assert decoded.mode == "L"


def test_analyze_rejects_jpeg(client):
    img = Image.new("RGB", (16, 16))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    response = client.post(
        "/analyze", files={"file": ("photo.jpg", buf.getvalue(), "image/jpeg")}
    )
    assert response.status_code == 400
    assert "unsupported" in response.json()["detail"].lower()


def test_analyze_rejects_oversized_file(client):
    oversized = b"\x00" * (settings.MAX_FILE_SIZE_BYTES + 1)
    response = client.post(
        "/analyze", files={"file": ("big.png", oversized, "image/png")}
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()


def test_analyze_rejects_corrupt_png(client):
    response = client.post(
        "/analyze", files={"file": ("bad.png", b"not a real png", "image/png")}
    )
    assert response.status_code == 400
