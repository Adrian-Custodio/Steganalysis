"""
FastAPI app: routes, CORS, and request orchestration.

This module is intentionally thin — it validates the upload, delegates to
the analysis modules for the actual math, and shapes the response. All the
interesting logic lives in app/analysis/.
"""

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
    """Run chi-square attack + RS analysis on an uploaded image.

    Rejects anything that isn't PNG/BMP (JPEG's lossy compression corrupts
    the raw LSB plane that both methods depend on — see README) and
    anything over the configured size limit.
    """
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
    # overall_verdict is derived from the *average* of the two scores,
    # not the worse of the two verdicts. Chi-square is known to be noisy
    # on smooth/gradient-heavy or naturally noisy images (see
    # chi_square.py's docstring, and README limitations) — letting a
    # single method's known false-positive tendency dictate the overall
    # result would make the tool cry wolf on plenty of legitimate clean
    # images. Averaging lets RS analysis (the more robust method)
    # counterbalance that, while both raw scores stay visible in the
    # response for anyone who wants to weigh them differently.
    overall_score = (chi_result.score + rs_result.score) / 2
    overall_verdict = score_to_verdict(overall_score)

    # Preview built from the first channel (R, or the sole channel for
    # grayscale-derived images) — enough to visually show the bit-plane
    # pattern the two methods are reasoning about.
    lsb_plane = extract_lsb_plane(channels[0])
    preview_b64 = lsb_plane_to_png_base64(lsb_plane)

    return AnalyzeResponse(
        filename=file.filename or "upload",
        chi_square=chi_square,
        rs_analysis=rs_analysis,
        overall_verdict=overall_verdict,
        bit_plane_preview=preview_b64,
    )
