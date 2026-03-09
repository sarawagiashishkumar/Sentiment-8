import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

from data.fno_contracts import FNO_CONTRACTS, get_fno_contract
from data.symbols import MULTIBAGGER_UNIVERSE
from services.market_data import get_option_ltp, get_stock_core

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI()
api_router = APIRouter(prefix="/api")


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class StockCoreNormalized(BaseModel):
    symbol: str
    company_name: str
    ltp: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    year_high: float | None = None
    year_low: float | None = None
    volume: int = 0
    market_cap: float | None = None
    pe_ratio: float | None = None
    book_value: float | None = None
    eps: float | None = None
    sector: str = "Unknown"


class MultibaggerCandidate(BaseModel):
    symbol: str
    company_name: str
    sector: str
    ltp: float | None = None
    market_cap_cr: float | None = None
    pe_ratio: float | None = None
    year_high: float | None = None
    year_low: float | None = None
    upside_to_52w_high_pct: float | None = None
    pb_ratio_est: float | None = None
    peg_ratio_est: float | None = None
    tier_pass_count: int
    is_potential_multibagger: bool
    multibagger_score: int
    analysis_refreshed_at: str


class FNOContract(BaseModel):
    script: str
    underlying: str
    expiry: str
    strike: float
    option_type: Literal["CE", "PE"]
    exchange: str
    lot_size: int


class FNOSignalResponse(BaseModel):
    script: str
    underlying: str
    expiry: str
    strike: float
    option_type: Literal["CE", "PE"]
    exchange: str
    lot_size: int
    underlying_ltp: float
    option_ltp: float
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    strategy: str
    entry_price: float
    stop_loss: float
    target1: float
    target2: float
    risk_reward_target1: float
    risk_reward_target2: float
    trigger_factors: List[str]
    confluence_score: int
    signal_quality: Literal["HIGH", "MEDIUM", "LOW"]
    is_potential_trade: bool
    analysis_refreshed_at: str


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _position_in_range(ltp: float | None, year_low: float | None, year_high: float | None) -> float | None:
    if ltp is None or year_low is None or year_high is None or year_high <= year_low:
        return None
    return clamp((ltp - year_low) / (year_high - year_low), 0.0, 1.0)


def compute_multibagger_analysis(stock: StockCoreNormalized) -> dict:
    ltp = stock.ltp
    market_cap = stock.market_cap
    pe = stock.pe_ratio
    book_value = stock.book_value
    eps = stock.eps
    year_high = stock.year_high
    year_low = stock.year_low

    pb_ratio_est = _safe_ratio(ltp, book_value)
    upside_to_52w_high_pct = (
        ((year_high - ltp) / ltp) * 100
        if year_high is not None and ltp is not None and ltp > 0
        else None
    )

    growth_proxy_pct = (
        ((year_high - year_low) / year_low) * 100
        if year_high is not None and year_low is not None and year_low > 0 and year_high > year_low
        else None
    )
    peg_ratio_est = _safe_ratio(pe, growth_proxy_pct) if growth_proxy_pct is not None else None

    tier_1_market_cap = market_cap is not None and 500 < market_cap < 1_000_000
    tier_1_price_zone = (
        ltp is not None
        and year_low is not None
        and year_high is not None
        and ltp <= 1.15 * year_low
        and year_high >= 1.70 * ltp
        and ltp >= 10
        and pb_ratio_est is not None
        and pb_ratio_est < 5
        and peg_ratio_est is not None
        and peg_ratio_est < 1.5
    )

    # Tier proxies built from available reliable live fields.
    tier_2_revenue_profit_proxy = (
        eps is not None
        and eps > 0
        and pe is not None
        and pe < 45
        and upside_to_52w_high_pct is not None
        and upside_to_52w_high_pct >= 12
    )
    tier_3_profitability_proxy = (
        pe is not None
        and 5 <= pe <= 40
        and pb_ratio_est is not None
        and pb_ratio_est < 4.5
    )
    tier_4_balance_sheet_proxy = (
        market_cap is not None
        and market_cap > 1_000
        and stock.volume > 100_000
        and ltp is not None
        and stock.prev_close is not None
    )
    tier_5_governance_proxy = stock.sector != "Unknown" and market_cap is not None and market_cap > 2_000
    tier_6_forensic_proxy = eps is not None and eps > 0 and pe is not None and 6 <= pe <= 45
    tier_7_cwip_capex_proxy = (
        year_high is not None and year_low is not None and year_low > 0 and year_high >= 1.20 * year_low
    )

    tier_flags = [
        tier_1_market_cap,
        tier_1_price_zone,
        tier_2_revenue_profit_proxy,
        tier_3_profitability_proxy,
        tier_4_balance_sheet_proxy,
        tier_5_governance_proxy,
        tier_6_forensic_proxy,
        tier_7_cwip_capex_proxy,
    ]
    tier_pass_count = sum(1 for status in tier_flags if status)

    mandatory_pass = tier_1_market_cap and tier_1_price_zone

    score = 0.0
    score += 9 * tier_pass_count
    if mandatory_pass:
        score += 15
    else:
        score -= 6

    if upside_to_52w_high_pct is not None:
        score += clamp(upside_to_52w_high_pct / 8, 0, 12)

    if peg_ratio_est is not None:
        if peg_ratio_est < 1.5:
            score += 8
        elif peg_ratio_est < 2.5:
            score += 4

    if pb_ratio_est is not None:
        if pb_ratio_est < 3:
            score += 6
        elif pb_ratio_est < 5:
            score += 3

    if pe is not None and pe > 55:
        score -= 10
    elif pe is not None and pe < 10:
        score -= 4

    final_score = int(clamp(round(score), 0, 100))
    is_potential_multibagger = (mandatory_pass and tier_pass_count >= 5) or (
        tier_pass_count >= 6 and final_score >= 68
    )

    return {
        "multibagger_score": final_score,
        "upside_to_52w_high_pct": round(upside_to_52w_high_pct, 2) if upside_to_52w_high_pct is not None else None,
        "pb_ratio_est": round(pb_ratio_est, 2) if pb_ratio_est is not None else None,
        "peg_ratio_est": round(peg_ratio_est, 2) if peg_ratio_est is not None else None,
        "tier_pass_count": tier_pass_count,
        "is_potential_multibagger": is_potential_multibagger,
    }


def _get_signal_quality(confluence_score: int) -> Literal["HIGH", "MEDIUM", "LOW"]:
    if confluence_score >= 78:
        return "HIGH"
    if confluence_score >= 65:
        return "MEDIUM"
    return "LOW"


def build_fno_signal(
    contract: FNOContract,
    stock_core: StockCoreNormalized,
    option_ltp: float,
    refreshed_at: str,
) -> FNOSignalResponse:
    underlying_ltp = stock_core.ltp
    if underlying_ltp is None:
        raise HTTPException(status_code=502, detail="Underlying LTP unavailable")

    pos = _position_in_range(underlying_ltp, stock_core.year_low, stock_core.year_high)
    day_change_pct = (
        ((underlying_ltp - stock_core.prev_close) / stock_core.prev_close) * 100
        if stock_core.prev_close is not None and stock_core.prev_close > 0
        else 0.0
    )
    intraday_change_pct = (
        ((underlying_ltp - stock_core.open) / stock_core.open) * 100
        if stock_core.open is not None and stock_core.open > 0
        else 0.0
    )

    trend_points = 0.0
    trigger_factors: list[str] = []

    if day_change_pct >= 0.35:
        trend_points += 16
        trigger_factors.append(f"DayChange={day_change_pct:.2f}%")
    elif day_change_pct <= -0.35:
        trend_points -= 16
        trigger_factors.append(f"DayChange={day_change_pct:.2f}%")

    if intraday_change_pct >= 0.20:
        trend_points += 14
        trigger_factors.append(f"IntraDay={intraday_change_pct:.2f}%")
    elif intraday_change_pct <= -0.20:
        trend_points -= 14
        trigger_factors.append(f"IntraDay={intraday_change_pct:.2f}%")

    if pos is not None:
        if pos >= 0.62:
            trend_points += 12
            trigger_factors.append("RangePos=Upper")
        elif pos <= 0.38:
            trend_points -= 12
            trigger_factors.append("RangePos=Lower")

    if stock_core.high is not None and underlying_ltp >= stock_core.high * 0.995:
        trend_points += 8
        trigger_factors.append("NearDayHigh")
    if stock_core.low is not None and underlying_ltp <= stock_core.low * 1.005:
        trend_points -= 8
        trigger_factors.append("NearDayLow")

    bias_score = (0.65 * day_change_pct) + (0.35 * intraday_change_pct)
    if pos is not None:
        bias_score += (pos - 0.5) * 1.2

    if bias_score >= 0.15:
        underlying_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
        trigger_factors.append(f"BiasScore={bias_score:.2f}")
    elif bias_score <= -0.15:
        underlying_bias = "BEARISH"
        trigger_factors.append(f"BiasScore={bias_score:.2f}")
    else:
        underlying_bias = "NEUTRAL"
        trigger_factors.append(f"BiasScore={bias_score:.2f}")

    if contract.option_type == "CE" and underlying_bias == "BULLISH":
        direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif contract.option_type == "PE" and underlying_bias == "BEARISH":
        direction = "BEARISH"
    elif underlying_bias == "NEUTRAL":
        direction = "NEUTRAL"
    else:
        direction = "NEUTRAL"

    entry_price = round(option_ltp, 2)
    stop_loss = round(entry_price * 0.6, 2)
    target1 = round(entry_price * 1.5, 2)
    target2 = round(entry_price * 2.0, 2)

    risk = max(entry_price - stop_loss, 0.01)
    risk_reward_target1 = round((target1 - entry_price) / risk, 2)
    risk_reward_target2 = round((target2 - entry_price) / risk, 2)

    confluence = 52 + abs(bias_score) * 22

    if direction == "NEUTRAL":
        confluence -= 20
    else:
        confluence += 12

    if risk_reward_target2 >= 2:
        confluence += 8
    if option_ltp < 1:
        confluence -= 8
    if stock_core.volume <= 0:
        confluence -= 4

    confluence_score = int(clamp(round(confluence), 0, 100))
    signal_quality = _get_signal_quality(confluence_score)
    is_potential_trade = direction != "NEUTRAL" and confluence_score >= 72 and risk_reward_target2 >= 2

    if is_potential_trade:
        trigger_factors.append("PotentialTrade=YES")

    return FNOSignalResponse(
        script=contract.script,
        underlying=contract.underlying,
        expiry=contract.expiry,
        strike=contract.strike,
        option_type=contract.option_type,
        exchange=contract.exchange,
        lot_size=contract.lot_size,
        underlying_ltp=round(underlying_ltp, 2),
        option_ltp=round(option_ltp, 2),
        direction=direction,
        strategy=(
            "Index Directional Option (High Conviction)"
            if is_potential_trade
            else "Index/Stock Directional Option (Simplified)"
        ),
        entry_price=entry_price,
        stop_loss=stop_loss,
        target1=target1,
        target2=target2,
        risk_reward_target1=risk_reward_target1,
        risk_reward_target2=risk_reward_target2,
        trigger_factors=trigger_factors,
        confluence_score=confluence_score,
        signal_quality=signal_quality,
        is_potential_trade=is_potential_trade,
        analysis_refreshed_at=refreshed_at,
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _build_fno_signal_for_contract(contract: FNOContract, refreshed_at: str) -> FNOSignalResponse:
    stock_data = StockCoreNormalized(**(await get_stock_core(contract.underlying)))
    option_ltp = await get_option_ltp(contract.script)
    return build_fno_signal(contract, stock_data, option_ltp, refreshed_at)


@api_router.get("/")
async def root():
    return {"message": "AI Stock Research API"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    doc = status_obj.model_dump()
    doc["timestamp"] = doc["timestamp"].isoformat()
    _ = await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check.get("timestamp"), str):
            check["timestamp"] = datetime.fromisoformat(check["timestamp"])
    return status_checks


@api_router.get("/multibagger/candidates", response_model=List[MultibaggerCandidate])
async def get_multibagger_candidates(
    refresh_nonce: str | None = Query(default=None),
):
    _ = refresh_nonce
    refreshed_at = _utc_now_iso()
    results = await asyncio.gather(*[get_stock_core(symbol) for symbol in MULTIBAGGER_UNIVERSE])
    candidates: list[MultibaggerCandidate] = []

    for row in results:
        stock = StockCoreNormalized(**row)
        if stock.ltp is None:
            continue
        analysis = compute_multibagger_analysis(stock)
        candidates.append(
            MultibaggerCandidate(
                symbol=stock.symbol,
                company_name=stock.company_name,
                sector=stock.sector,
                ltp=stock.ltp,
                market_cap_cr=stock.market_cap,
                pe_ratio=stock.pe_ratio,
                year_high=stock.year_high,
                year_low=stock.year_low,
                upside_to_52w_high_pct=analysis["upside_to_52w_high_pct"],
                pb_ratio_est=analysis["pb_ratio_est"],
                peg_ratio_est=analysis["peg_ratio_est"],
                tier_pass_count=analysis["tier_pass_count"],
                is_potential_multibagger=analysis["is_potential_multibagger"],
                multibagger_score=analysis["multibagger_score"],
                analysis_refreshed_at=refreshed_at,
            )
        )

    candidates.sort(
        key=lambda item: (item.is_potential_multibagger, item.multibagger_score),
        reverse=True,
    )
    return candidates[:30]


@api_router.get("/fno/contracts", response_model=List[FNOContract])
async def get_fno_contracts():
    return [FNOContract(**item) for item in FNO_CONTRACTS]


@api_router.get("/fno/signal/{script}", response_model=FNOSignalResponse)
async def get_single_fno_signal(
    script: str,
    refresh_nonce: str | None = Query(default=None),
):
    _ = refresh_nonce
    contract_dict = get_fno_contract(script)
    if not contract_dict:
        raise HTTPException(status_code=404, detail="Script not supported")

    contract = FNOContract(**contract_dict)
    refreshed_at = _utc_now_iso()
    try:
        return await _build_fno_signal_for_contract(contract, refreshed_at)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@api_router.get("/fno/signals/index", response_model=List[FNOSignalResponse])
async def get_index_fno_signals(
    refresh_nonce: str | None = Query(default=None),
):
    _ = refresh_nonce
    index_contracts = [
        FNOContract(**contract)
        for contract in FNO_CONTRACTS
        if contract["underlying"] in {"NIFTY", "BANKNIFTY"}
    ]

    refreshed_at = _utc_now_iso()
    signals: list[FNOSignalResponse] = []
    for contract in index_contracts:
        try:
            signal = await _build_fno_signal_for_contract(contract, refreshed_at)
            signals.append(signal)
        except Exception:
            continue
    signals.sort(key=lambda item: (item.is_potential_trade, item.confluence_score), reverse=True)
    return signals


@api_router.get("/fno/signals/potential", response_model=List[FNOSignalResponse])
async def get_potential_index_signals(
    refresh_nonce: str | None = Query(default=None),
):
    _ = refresh_nonce
    signals = await get_index_fno_signals(refresh_nonce=None)
    potential = [signal for signal in signals if signal.is_potential_trade]
    if potential:
        return potential
    return signals[:2]


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()