"""Application settings for the Steganalysis Detection API. Centralized here
so per-deploy config (CORS origin, limits) isn't scattered through routes."""

from __future__ import annotations

import os


class Settings:
    """Overridable via env vars at deploy time (Render/Railway)."""

    # Upload limit, per spec (5 MB default).
    MAX_FILE_SIZE_BYTES: int = int(os.getenv("MAX_FILE_SIZE_BYTES", 5 * 1024 * 1024))

    # JPEG excluded — lossy compression destroys the LSB plane this tool analyzes.
    ALLOWED_CONTENT_TYPES: tuple[str, ...] = ("image/png", "image/bmp", "image/x-ms-bmp")
    ALLOWED_EXTENSIONS: tuple[str, ...] = (".png", ".bmp")

    # Comma-separated allowed CORS origins; production must set this explicitly.
    _default_origins = "http://localhost:3000,http://127.0.0.1:3000"
    ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
        if origin.strip()
    ]

    # Heuristic verdict cutoffs (not forensic-grade — see README).
    SUSPICIOUS_THRESHOLD: float = 0.3
    STEGO_THRESHOLD: float = 0.6

    # Pixels per group for RS analysis.
    RS_GROUP_SIZE: int = 4


settings = Settings()
