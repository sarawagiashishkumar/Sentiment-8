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
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    import server as _srv

    extension = (file.filename or "").split(".")[-1].lower() if "." in (file.filename or "") else ""
    allowed = {"txt", "csv", "xls", "xlsx", "pdf", "jpg", "jpeg", "bmp", "png", "webp"}
    if extension not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    positions = await _srv._parse_positions_from_upload(file)
    if not positions:
        ocr_hint = "enabled" if _srv._is_tesseract_ready() else "not available"
        raise HTTPException(
            status_code=400,
            detail=(
                "No valid rows could be parsed from uploaded file. "
                "Use columns like Symbol/Name, Avg Price, Quantity. "
                f"OCR engine status: {ocr_hint}."
            ),
        )
    analysis = await _srv._analyze_portfolio_positions(positions)
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
