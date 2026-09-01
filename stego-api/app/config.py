"""
Application settings for the Steganalysis Detection API.

Centralizing these here (rather than scattering literals through the route
handlers) makes it obvious what's configurable per-deploy — e.g. the allowed
CORS origin changes between local dev and the Vercel frontend's production URL.
"""

from __future__ import annotations

import os


class Settings:
    """Simple settings object. Values can be overridden via environment
    variables at deploy time (Render/Railway) without touching code."""

    # --- Upload limits -----------------------------------------------------
    # 5 MB, per spec. Images larger than this are rejected before decoding
    # to avoid wasting CPU/memory on oversized uploads.
    MAX_FILE_SIZE_BYTES: int = int(os.getenv("MAX_FILE_SIZE_BYTES", 5 * 1024 * 1024))

    # Formats we can meaningfully run LSB steganalysis on. JPEG is lossy and
    # its compression destroys/alters the raw LSB plane, so it's excluded
    # here; the upload route uses this list to decide whether to reject or
    # flag-and-degrade JPEG (see README for the chosen behavior).
    ALLOWED_CONTENT_TYPES: tuple[str, ...] = ("image/png", "image/bmp", "image/x-ms-bmp")
    ALLOWED_EXTENSIONS: tuple[str, ...] = (".png", ".bmp")

    # --- CORS ---------------------------------------------------------------
    # Comma-separated list of allowed origins, e.g.
    #   ALLOWED_ORIGINS="http://localhost:3000,https://my-frontend.vercel.app"
    # Defaults to permissive localhost dev origins only; production deploys
    # must set ALLOWED_ORIGINS explicitly to their Vercel domain.
    _default_origins = "http://localhost:3000,http://127.0.0.1:3000"
    ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
        if origin.strip()
    ]

    # --- Verdict thresholds ---------------------------------------------------
    # Heuristic, not forensic-grade — see README "Limitations" section.
    # score < SUSPICIOUS_THRESHOLD               -> "clean"
    # SUSPICIOUS_THRESHOLD <= score < STEGO_THRESHOLD -> "suspicious"
    # score >= STEGO_THRESHOLD                    -> "likely_stego"
    SUSPICIOUS_THRESHOLD: float = 0.3
    STEGO_THRESHOLD: float = 0.6

    # --- RS analysis group size ---------------------------------------------
    # Number of pixels per group when computing Regular/Singular groups.
    RS_GROUP_SIZE: int = 4


settings = Settings()
