import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
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
    multibagger_score: int


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
    confluence_score: int


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _position_in_range(ltp: float | None, year_low: float | None, year_high: float | None) -> float | None:
    if ltp is None or year_low is None or year_high is None or year_high <= year_low:
        return None
    return clamp((ltp - year_low) / (year_high - year_low), 0.0, 1.0)


def compute_multibagger_score(stock: StockCoreNormalized) -> int:
    score = 0.0

    market_cap = stock.market_cap
    ltp = stock.ltp
    pe = stock.pe_ratio
    eps = stock.eps
    pos = _position_in_range(stock.ltp, stock.year_low, stock.year_high)

    if market_cap is not None:
        if 500 <= market_cap <= 1_000_000:
            score += 25
        elif market_cap < 500:
            score += 8
        else:
            score += 15

    if ltp is not None:
        if ltp >= 10:
            score += 12
        elif ltp >= 5:
            score += 6
        else:
            score += 2

    if pe is not None and pe > 0:
        if pe <= 25:
            score += 20
        elif pe <= 50:
            score += 14
        elif pe <= 80:
            score += 6
        else:
            score -= 8

    if stock.year_high and ltp and stock.year_high > 0:
        upside_pct = ((stock.year_high - ltp) / stock.year_high) * 100
        if upside_pct >= 20:
            score += 15
        elif upside_pct >= 8:
            score += 8
        else:
            score += 2

    if pos is not None:
        if 0.20 <= pos <= 0.75:
            score += 14
        elif pos < 0.20:
            score += 6
        else:
            score -= 6

    if eps is not None:
        if eps > 0:
            score += 10
        else:
            score -= 10

    if eps is not None and pe is not None and eps > 0 and pe <= 35:
        score += 8

    if stock.sector and stock.sector != "Unknown":
        score += 6

    return int(clamp(round(score), 0, 100))


def build_fno_signal(contract: FNOContract, stock_core: StockCoreNormalized, option_ltp: float) -> FNOSignalResponse:
    underlying_ltp = stock_core.ltp
    if underlying_ltp is None:
        raise HTTPException(status_code=502, detail="Underlying LTP unavailable")

    pos = _position_in_range(underlying_ltp, stock_core.year_low, stock_core.year_high)
    closer_to_high = pos is not None and pos >= 0.5
    closer_to_low = pos is not None and pos < 0.5

    if contract.option_type == "CE" and closer_to_high:
        direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif contract.option_type == "PE" and closer_to_low:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    entry_price = round(option_ltp, 2)
    stop_loss = round(entry_price * 0.6, 2)
    target1 = round(entry_price * 1.5, 2)
    target2 = round(entry_price * 2.0, 2)

    risk = max(entry_price - stop_loss, 0.01)
    risk_reward_target1 = round((target1 - entry_price) / risk, 2)
    risk_reward_target2 = round((target2 - entry_price) / risk, 2)

    confluence = 50
    if pos is not None:
        if contract.option_type == "CE":
            if pos >= 0.65:
                confluence += 25
            elif pos >= 0.5:
                confluence += 15
            elif pos < 0.3:
                confluence -= 15
            else:
                confluence -= 5
        else:
            if pos <= 0.35:
                confluence += 25
            elif pos <= 0.5:
                confluence += 15
            elif pos > 0.7:
                confluence -= 15
            else:
                confluence -= 5

    if direction == "NEUTRAL":
        confluence -= 10

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
        strategy="Index/Stock Directional Option (Simplified)",
        entry_price=entry_price,
        stop_loss=stop_loss,
        target1=target1,
        target2=target2,
        risk_reward_target1=risk_reward_target1,
        risk_reward_target2=risk_reward_target2,
        confluence_score=int(clamp(confluence, 0, 100)),
    )


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
async def get_multibagger_candidates():
    results = await asyncio.gather(*[get_stock_core(symbol) for symbol in MULTIBAGGER_UNIVERSE])
    candidates: list[MultibaggerCandidate] = []

    for row in results:
        stock = StockCoreNormalized(**row)
        if stock.ltp is None:
            continue
        score = compute_multibagger_score(stock)
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
                multibagger_score=score,
            )
        )

    candidates.sort(key=lambda item: item.multibagger_score, reverse=True)
    return candidates[:30]


@api_router.get("/fno/contracts", response_model=List[FNOContract])
async def get_fno_contracts():
    return [FNOContract(**item) for item in FNO_CONTRACTS]


@api_router.get("/fno/signal/{script}", response_model=FNOSignalResponse)
async def get_single_fno_signal(script: str):
    contract_dict = get_fno_contract(script)
    if not contract_dict:
        raise HTTPException(status_code=404, detail="Script not supported")

    contract = FNOContract(**contract_dict)
    stock_data = StockCoreNormalized(**(await get_stock_core(contract.underlying)))
    try:
        option_ltp = await get_option_ltp(contract.script)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return build_fno_signal(contract, stock_data, option_ltp)


@api_router.get("/fno/signals/index", response_model=List[FNOSignalResponse])
async def get_index_fno_signals():
    index_contracts = [
        FNOContract(**contract)
        for contract in FNO_CONTRACTS
        if contract["underlying"] in {"NIFTY", "BANKNIFTY"}
    ]

    signals: list[FNOSignalResponse] = []
    for contract in index_contracts:
        stock_data = StockCoreNormalized(**(await get_stock_core(contract.underlying)))
        try:
            option_ltp = await get_option_ltp(contract.script)
        except Exception:
            continue
        signals.append(build_fno_signal(contract, stock_data, option_ltp))
    return signals


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