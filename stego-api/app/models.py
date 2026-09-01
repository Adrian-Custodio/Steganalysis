"""
Pydantic response schemas for the Steganalysis Detection API.

Keeping these separate from route logic gives FastAPI's auto-generated
OpenAPI docs clean, reusable schema definitions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["clean", "suspicious", "likely_stego"]


class MethodResult(BaseModel):
    """Result of a single detection method (chi-square or RS analysis)."""

    score: float = Field(..., ge=0.0, le=1.0, description="Normalized suspicion score, 0-1.")
    verdict: Verdict = Field(..., description="Heuristic classification derived from `score`.")
    explanation: str = Field(..., description="Short human-readable summary of the result.")


class AnalyzeResponse(BaseModel):
    """Response body for `POST /analyze`."""

    filename: str
    chi_square: MethodResult
    rs_analysis: MethodResult
    overall_verdict: Verdict
    bit_plane_preview: str = Field(
        ..., description="Base64-encoded PNG of the extracted LSB plane, for visualization."
    )


class HealthResponse(BaseModel):
    """Response body for `GET /health`."""

    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    """Shape of error bodies returned for rejected uploads (bad format, too large, etc.)."""

    detail: str
