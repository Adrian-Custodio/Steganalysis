"""FastAPI app: routes, CORS, and request orchestration. Validation and
response shaping only — the actual math lives in app/analysis/."""

from __future__ import annotations

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.analysis.chi_square import chi_square_attack_image
from app.analysis.rs_analysis import rs_analysis_image
from app.analysis.utils import (
    ImageLoadError,
    extract_lsb_plane,
    image_to_array,
    lsb_plane_to_png_base64,
    score_to_verdict,
    split_channels,
    validate_and_load,
)
from app.config import settings
from app.models import AnalyzeResponse, HealthResponse, MethodResult

app = FastAPI(
    title="Steganalysis Detection API",
    description=(
        "Accepts an uploaded PNG/BMP image and reports whether it likely "
        "contains LSB steganography, using a chi-square attack and RS "
        "(Regular-Singular) analysis. Heuristic/educational tool — see "
        "README for limitations, not a forensic-grade detector."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Basic health check for deploy monitoring (Render/Railway)."""
    return HealthResponse()


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(file: UploadFile = File(...)) -> AnalyzeResponse:
    """Run chi-square attack + RS analysis on an uploaded image. Rejects
    non-PNG/BMP files and anything over the configured size limit."""
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext or 'unknown'}'. Only "
                f"{', '.join(settings.ALLOWED_EXTENSIONS)} are supported — "
                "JPEG's lossy compression destroys the LSB data this tool "
                "analyzes."
            ),
        )

    data = await file.read()

    try:
        image = validate_and_load(data, settings.MAX_FILE_SIZE_BYTES)
    except ImageLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    array = image_to_array(image)
    channels = split_channels(array)

    chi_result = chi_square_attack_image(channels)
    rs_result = rs_analysis_image(channels)

    chi_square = MethodResult(
        score=round(chi_result.score, 4),
        verdict=chi_result.verdict,
        explanation=chi_result.explanation,
    )
    rs_analysis = MethodResult(
        score=round(rs_result.score, 4),
        verdict=rs_result.verdict,
        explanation=rs_result.explanation,
    )
    # Average the two scores rather than taking the worse verdict — chi-square
    # is noisy on smooth/natural images, so RS analysis counterbalances it.
    overall_score = (chi_result.score + rs_result.score) / 2
    overall_verdict = score_to_verdict(overall_score)

    # Preview from the first channel — enough to show the bit-plane pattern.
    lsb_plane = extract_lsb_plane(channels[0])
    preview_b64 = lsb_plane_to_png_base64(lsb_plane)

    return AnalyzeResponse(
        filename=file.filename or "upload",
        chi_square=chi_square,
        rs_analysis=rs_analysis,
        overall_verdict=overall_verdict,
        bit_plane_preview=preview_b64,
    )
