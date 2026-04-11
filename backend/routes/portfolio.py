"""
Portfolio analysis route handlers.

Endpoints: /portfolio/analyze, /portfolio/analyze-upload
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from deps import get_current_user
from models import PortfolioAnalyzeRequest, PortfolioAnalyzeResponse

logger = logging.getLogger(__name__)

portfolio_router = APIRouter()


@portfolio_router.post("/portfolio/analyze", response_model=PortfolioAnalyzeResponse)
async def analyze_portfolio_manual(
    payload: PortfolioAnalyzeRequest,
    current_user: dict = Depends(get_current_user),
):
    import server as _srv

    normalized = [item.model_dump() for item in payload.positions]
    analysis = await _srv._analyze_portfolio_positions(normalized)
    cost = round(0.2 * analysis.parsed_positions_count, 2)
    updated_user, charged = await _srv._consume_credits(current_user, cost)
    return PortfolioAnalyzeResponse(
        cost_charged=charged,
        credits_remaining=round(float(updated_user.get("credits", 0)), 2),
        parsed_positions_count=analysis.parsed_positions_count,
        stocks=analysis.stocks,
        failed_symbols=analysis.failed_symbols,
        portfolio_risk_metrics=analysis.portfolio_risk_metrics,
        enhanced_analytics=analysis.enhanced_analytics,
    )


@portfolio_router.post("/portfolio/analyze-upload", response_model=PortfolioAnalyzeResponse)
async def analyze_portfolio_upload(
    file: UploadFile = File(None),
    files: list[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    """Analyze uploaded portfolio file(s). Supports single or multi-file upload."""
    import server as _srv

    # Collect all files — support both single 'file' and multi 'files' params
    upload_files = []
    if files:
        upload_files.extend([f for f in files if f and f.filename])
    if file and file.filename and file not in upload_files:
        upload_files.append(file)

    if not upload_files:
        raise HTTPException(status_code=400, detail="No file uploaded")

    allowed = {"txt", "csv", "xls", "xlsx", "pdf", "jpg", "jpeg", "bmp", "png", "webp"}
    all_positions = []

    for uf in upload_files:
        extension = (uf.filename or "").split(".")[-1].lower() if "." in (uf.filename or "") else ""
        if extension not in allowed:
            logger.warning("Skipping unsupported file: %s", uf.filename)
            continue
        try:
            parsed = await _srv._parse_positions_from_upload(uf)
            if parsed:
                all_positions.extend(parsed)
        except Exception as exc:
            logger.warning("Failed to parse file %s: %s", uf.filename, exc)

    if not all_positions:
        ocr_hint = "enabled" if _srv._is_tesseract_ready() else "not available"
        raise HTTPException(
            status_code=400,
            detail=(
                f"No valid rows could be parsed from {len(upload_files)} uploaded file(s). "
                "Use columns like Symbol/Name, Avg Price, Quantity. "
                f"OCR engine status: {ocr_hint}."
            ),
        )

    analysis = await _srv._analyze_portfolio_positions(all_positions)
    cost = round(0.2 * analysis.parsed_positions_count, 2)
    updated_user, charged = await _srv._consume_credits(current_user, cost)
    return PortfolioAnalyzeResponse(
        cost_charged=charged,
        credits_remaining=round(float(updated_user.get("credits", 0)), 2),
        parsed_positions_count=analysis.parsed_positions_count,
        stocks=analysis.stocks,
        failed_symbols=analysis.failed_symbols,
        portfolio_risk_metrics=analysis.portfolio_risk_metrics,
        enhanced_analytics=analysis.enhanced_analytics,
    )
