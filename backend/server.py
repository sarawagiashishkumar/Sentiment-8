import asyncio
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Literal

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from starlette.middleware.cors import CORSMiddleware

from data.fno_contracts import FNO_CONTRACTS, get_fno_contract
from data.symbols import MULTIBAGGER_UNIVERSE
from services.market_data import get_stock_core, market_data_client

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

OWNER_BOOTSTRAP_USERNAME = os.environ.get("OWNER_BOOTSTRAP_USERNAME", "@shish123")
LEGACY_OWNER_ALIAS = os.environ.get("LEGACY_OWNER_ALIAS", "owner123")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9@._-]{6,}$")
SCRIPT_PATTERN = re.compile(r"^([A-Z]+)(\d{1,2})([A-Z]{3})(\d+)(CE|PE)$")
SESSION_STORE: Dict[str, dict] = {}
IST = timezone(timedelta(hours=5, minutes=30))

MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

LOT_SIZE_MAP = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "RELIANCE": 250,
    "BDL": 1350,
    "SBIN": 750,
    "TCS": 175,
}

NIFTY_WEIGHT_PROXY = [
    ("HDFCBANK", 13.0),
    ("RELIANCE", 9.6),
    ("ICICIBANK", 8.4),
    ("INFY", 6.0),
    ("TCS", 4.4),
    ("BHARTIARTL", 4.1),
    ("ITC", 3.8),
    ("LT", 3.5),
    ("AXISBANK", 3.1),
    ("KOTAKBANK", 2.8),
]

BANKNIFTY_WEIGHT_PROXY = [
    ("HDFCBANK", 29.0),
    ("ICICIBANK", 23.0),
    ("KOTAKBANK", 13.0),
    ("AXISBANK", 11.0),
    ("SBIN", 10.0),
    ("INDUSINDBK", 4.0),
    ("BANDHANBNK", 2.0),
    ("FEDERALBNK", 2.0),
    ("AUBANK", 2.0),
    ("PNB", 1.5),
    ("CANBK", 1.5),
    ("BANKBARODA", 1.0),
]


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class AccessRequest(BaseModel):
    username: str | None = None
    password: str | None = None


class AccessResponse(BaseModel):
    token: str
    role: Literal["owner", "sub_admin", "user"]
    credits: int
    user_key: str
    username: str
    admin_exempt: bool


class MeResponse(BaseModel):
    role: Literal["owner", "sub_admin", "user"]
    credits: int
    user_key: str
    username: str
    admin_exempt: bool


class AdminUserView(BaseModel):
    user_key: str
    username: str
    role: Literal["owner", "sub_admin", "user"]
    credits: int
    created_at: str
    created_by: str
    quota_limit: int
    quota_used: int
    credential_label: str


class AdminCreateUserRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    role: Literal["sub_admin", "user"] = "user"
    initial_credits: int = 0
    quota_limit: int = 10


class AdminSetCreditsRequest(BaseModel):
    credits: int


class AdminSetQuotaRequest(BaseModel):
    quota_limit: int


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
    current_rsi_level: float | None = None
    gtt_buy_price: float | None = None
    targeted_upside_price: dict
    targeted_upside_profit_pct: dict
    analysis_refreshed_at: str


class FNOContract(BaseModel):
    script: str
    underlying: str
    expiry: str
    expiry_time_ist: str = "15:30"
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
    minutes_to_expiry: int
    expiry_risk: Literal["LOW", "MEDIUM", "HIGH"]
    analysis_refreshed_at: str


class NonDirectionalStrategy(BaseModel):
    strike: float
    strategy: str
    ce_script: str
    pe_script: str
    combined_entry: float
    rationale: str
    confidence_score: int


class IndexAnalysisReport(BaseModel):
    report_type: Literal["with_consolidated", "without_consolidated"]
    breadth_score: float
    momentum_score: float
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    top_contributors: List[str]
    summary: str


class IndexProjectionPane(BaseModel):
    index_name: Literal["NIFTY", "BANKNIFTY"]
    spot: float
    strike_range_min: float
    strike_range_max: float
    assured_signals: List[FNOSignalResponse]
    non_directional_strategies: List[NonDirectionalStrategy]
    with_consolidated_report: IndexAnalysisReport
    without_consolidated_report: IndexAnalysisReport


class MultibaggerGenerateResponse(BaseModel):
    cost_charged: int
    credits_remaining: int
    analysis_refreshed_at: str
    candidates: List[MultibaggerCandidate]
    potential_count: int


class FNOGenerateRequest(BaseModel):
    custom_script: str | None = None


class FNOGenerateResponse(BaseModel):
    cost_charged: int
    credits_remaining: int
    analysis_refreshed_at: str
    signals: List[FNOSignalResponse]
    potential_signals: List[FNOSignalResponse]
    top_trades: List[FNOSignalResponse]
    custom_signal: FNOSignalResponse | None = None
    nifty_projection: IndexProjectionPane
    banknifty_projection: IndexProjectionPane
    stock_signals: List[FNOSignalResponse]


class CustomPositionCreateRequest(BaseModel):
    script: str
    buy_price: float


class CustomPositionResponse(BaseModel):
    id: str
    script: str
    underlying: str
    expiry_date: str
    expiry_time_ist: str
    lot_size: int
    buy_price: float
    created_at: str
    last_update: str
    status: Literal["OPEN", "CLOSED", "EXPIRED"]
    alert: str | None = None
    latest_option_ltp: float | None = None
    target1: float | None = None
    target2: float | None = None
    minutes_to_expiry: int
    revised_exit_plan: str


class CustomPositionCreateResponse(BaseModel):
    cost_charged: int
    credits_remaining: int
    position: CustomPositionResponse


class ScriptSearchResult(BaseModel):
    query: str
    suggestions: List[str]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _position_in_range(ltp: float | None, year_low: float | None, year_high: float | None) -> float | None:
    if ltp is None or year_low is None or year_high is None or year_high <= year_low:
        return None
    return clamp((ltp - year_low) / (year_high - year_low), 0.0, 1.0)


def get_minutes_to_expiry(contract: FNOContract | dict) -> int:
    expiry_date_str = contract["expiry"] if isinstance(contract, dict) else contract.expiry
    expiry_time_str = (
        contract.get("expiry_time_ist", "15:30")
        if isinstance(contract, dict)
        else contract.expiry_time_ist
    )
    expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    hh, mm = map(int, expiry_time_str.split(":"))
    expiry_dt = datetime.combine(expiry_date, time(hh, mm, tzinfo=IST))
    now = datetime.now(IST)
    return int((expiry_dt - now).total_seconds() / 60)


def _expiry_risk_bucket(minutes_to_expiry: int) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if minutes_to_expiry < 180:
        return "HIGH"
    if minutes_to_expiry < 1440:
        return "MEDIUM"
    return "LOW"


def _validate_expiry_guard(minutes_to_expiry: int) -> None:
    if minutes_to_expiry <= 0:
        raise HTTPException(status_code=400, detail="Contract expired. No projections available.")
    if minutes_to_expiry <= 15:
        raise HTTPException(status_code=400, detail="Too close to expiry for safe projections.")


def _validate_username(username: str) -> str:
    value = username.strip()
    if not USERNAME_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail="Username must be at least 6 chars and can use letters, numbers, @ . _ -",
        )
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise HTTPException(status_code=400, detail="Username must include at least one letter and one number")
    return value


async def _ensure_owner_exists() -> dict:
    owner_doc = await db.app_users.find_one_and_update(
        {"username": OWNER_BOOTSTRAP_USERNAME},
        {
            "$setOnInsert": {
                "user_key": str(uuid.uuid4()),
                "username": OWNER_BOOTSTRAP_USERNAME,
                "role": "owner",
                "credits": 0,
                "created_at": _utc_now_iso(),
                "created_by": "SYSTEM",
                "quota_limit": 10_000,
                "quota_used": 0,
            }
        },
        upsert=True,
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return owner_doc


async def _get_user_by_key(user_key: str) -> dict | None:
    return await db.app_users.find_one({"user_key": user_key}, {"_id": 0})


async def _get_user_by_username(username: str) -> dict | None:
    return await db.app_users.find_one({"username": username}, {"_id": 0})


async def _get_user_by_ref(user_ref: str) -> dict | None:
    candidate = await db.app_users.find_one({"user_key": user_ref}, {"_id": 0})
    if candidate:
        return candidate
    return await db.app_users.find_one({"username": user_ref}, {"_id": 0})


def _is_owner(user: dict) -> bool:
    return user.get("role") == "owner"


def _is_admin(user: dict) -> bool:
    return user.get("role") in {"owner", "sub_admin"}


def _is_credit_exempt(user: dict) -> bool:
    return user.get("role") in {"owner", "sub_admin"}


async def _consume_credits(user: dict, cost: int) -> tuple[dict, int]:
    if _is_credit_exempt(user):
        latest = await _get_user_by_key(user["user_key"])
        return latest or user, 0

    updated = await db.app_users.find_one_and_update(
        {"user_key": user["user_key"], "credits": {"$gte": cost}},
        {"$inc": {"credits": -cost}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        latest = await _get_user_by_key(user["user_key"])
        current = int(latest.get("credits", 0)) if latest else 0
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. Required {cost}, available {current}",
        )
    return updated, cost


def _map_user_view(user: dict) -> AdminUserView:
    role_raw = str(user.get("role", "user"))
    if role_raw == "admin":
        role_raw = "owner"
    role: Literal["owner", "sub_admin", "user"] = role_raw if role_raw in {"owner", "sub_admin", "user"} else "user"
    username = user.get("username") or f"legacy-{str(user.get('user_key', 'user'))[:6]}"

    return AdminUserView(
        user_key=user.get("user_key", str(uuid.uuid4())),
        username=username,
        role=role,
        credits=int(user.get("credits", 0)),
        created_at=user.get("created_at", ""),
        created_by=user.get("created_by", "SYSTEM"),
        quota_limit=int(user.get("quota_limit", 0)),
        quota_used=int(user.get("quota_used", 0)),
        credential_label=f"{username} as {role}",
    )


async def get_current_user(authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.replace("Bearer ", "", 1).strip()
    session = SESSION_STORE.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    user = await _get_user_by_key(session["user_key"])
    if not user:
        SESSION_STORE.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired")
    return user


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


async def get_owner_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not _is_owner(current_user):
        raise HTTPException(status_code=403, detail="Owner only")
    return current_user


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

    tier_2_revenue_profit_proxy = (
        eps is not None
        and eps > 0
        and pe is not None
        and pe < 45
        and upside_to_52w_high_pct is not None
        and upside_to_52w_high_pct >= 12
    )
    tier_3_profitability_proxy = (
        pe is not None and 5 <= pe <= 40 and pb_ratio_est is not None and pb_ratio_est < 4.5
    )
    tier_4_balance_sheet_proxy = market_cap is not None and market_cap > 1_000 and stock.volume > 100_000
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
    tier_pass_count = sum(1 for state in tier_flags if state)

    mandatory_pass = tier_1_market_cap and tier_1_price_zone
    score = 9 * tier_pass_count + (15 if mandatory_pass else -6)
    if upside_to_52w_high_pct is not None:
        score += clamp(upside_to_52w_high_pct / 8, 0, 12)
    if peg_ratio_est is not None:
        score += 8 if peg_ratio_est < 1.5 else (4 if peg_ratio_est < 2.5 else 0)
    if pb_ratio_est is not None:
        score += 6 if pb_ratio_est < 3 else (3 if pb_ratio_est < 5 else 0)
    if pe is not None and pe > 55:
        score -= 10
    elif pe is not None and pe < 10:
        score -= 4

    final_score = int(clamp(round(score), 0, 100))
    is_potential_multibagger = (mandatory_pass and tier_pass_count >= 5) or (
        tier_pass_count >= 6 and final_score >= 68
    )

    position = _position_in_range(ltp, year_low, year_high)
    current_rsi_level = round(30 + (position if position is not None else 0.5) * 40, 2) if ltp is not None else None
    gtt_buy_price = None
    if ltp is not None:
        base_buy = ltp * 0.965
        if year_low is not None and year_low > 0:
            base_buy = max(base_buy, year_low * 1.03)
        gtt_buy_price = round(base_buy, 2)

    duration_base = {
        "1W": 0.012,
        "1M": 0.045,
        "3M": 0.11,
        "6M": 0.19,
        "9M": 0.27,
        "1Y": 0.34,
    }
    momentum_adj = (final_score - 55) / 300
    targeted_upside_price = {}
    targeted_upside_profit_pct = {}
    for key, base in duration_base.items():
        if ltp is None:
            targeted_upside_price[key] = None
            targeted_upside_profit_pct[key] = None
            continue

        growth = base + momentum_adj
        if upside_to_52w_high_pct is not None and upside_to_52w_high_pct > 0:
            growth = min(growth, (upside_to_52w_high_pct / 100) * 1.25)
        growth = max(growth, 0.005)
        target_price = round(ltp * (1 + growth), 2)
        roi_pct = round(((target_price - ltp) / ltp) * 100, 2)

        targeted_upside_price[key] = target_price
        targeted_upside_profit_pct[key] = roi_pct

    return {
        "multibagger_score": final_score,
        "upside_to_52w_high_pct": round(upside_to_52w_high_pct, 2) if upside_to_52w_high_pct is not None else None,
        "pb_ratio_est": round(pb_ratio_est, 2) if pb_ratio_est is not None else None,
        "peg_ratio_est": round(peg_ratio_est, 2) if peg_ratio_est is not None else None,
        "tier_pass_count": tier_pass_count,
        "is_potential_multibagger": is_potential_multibagger,
        "current_rsi_level": current_rsi_level,
        "gtt_buy_price": gtt_buy_price,
        "targeted_upside_price": targeted_upside_price,
        "targeted_upside_profit_pct": targeted_upside_profit_pct,
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
    minutes_to_expiry: int,
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

    trigger_factors: list[str] = []
    if day_change_pct >= 0.35:
        trigger_factors.append(f"DayChange={day_change_pct:.2f}%")
    elif day_change_pct <= -0.35:
        trigger_factors.append(f"DayChange={day_change_pct:.2f}%")

    if intraday_change_pct >= 0.20:
        trigger_factors.append(f"IntraDay={intraday_change_pct:.2f}%")
    elif intraday_change_pct <= -0.20:
        trigger_factors.append(f"IntraDay={intraday_change_pct:.2f}%")

    bias_score = (0.65 * day_change_pct) + (0.35 * intraday_change_pct)
    if pos is not None:
        bias_score += (pos - 0.5) * 1.2
    trigger_factors.append(f"BiasScore={bias_score:.2f}")

    if bias_score >= 0.15:
        underlying_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif bias_score <= -0.15:
        underlying_bias = "BEARISH"
    else:
        underlying_bias = "NEUTRAL"

    if contract.option_type == "CE" and underlying_bias == "BULLISH":
        direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif contract.option_type == "PE" and underlying_bias == "BEARISH":
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    entry_price = round(option_ltp, 2)
    stop_loss = round(entry_price * 0.75, 2)
    target1 = round(entry_price * 1.12, 2)
    target2 = round(entry_price * 1.5, 2)

    if minutes_to_expiry < 60 and entry_price > 0:
        required_gain = (target1 - entry_price) / entry_price
        if required_gain > 0.12:
            raise HTTPException(
                status_code=400,
                detail="Insufficient time to expiry for this upside. No projections shown.",
            )

    risk = max(entry_price - stop_loss, 0.01)
    risk_reward_target1 = round((target1 - entry_price) / risk, 2)
    risk_reward_target2 = round((target2 - entry_price) / risk, 2)

    confluence = 52 + abs(bias_score) * 22
    confluence += 12 if direction != "NEUTRAL" else -18
    if risk_reward_target2 >= 2:
        confluence += 8
    if option_ltp < 1:
        confluence -= 8
    if minutes_to_expiry < 60:
        confluence -= 30
        trigger_factors.append("ExpiryWindow=<60m")
    elif minutes_to_expiry < 180:
        confluence -= 15
        trigger_factors.append("ExpiryWindow=<180m")

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
            "Assured Directional Projection"
            if is_potential_trade
            else "Directional Projection (Low Confidence)"
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
        minutes_to_expiry=minutes_to_expiry,
        expiry_risk=_expiry_risk_bucket(minutes_to_expiry),
        analysis_refreshed_at=refreshed_at,
    )


async def _get_nearest_expiry(underlying: str) -> str:
    instrument_id = ""
    if underlying == "NIFTY":
        instrument_id = "9"
    elif underlying == "BANKNIFTY":
        instrument_id = "23"
    else:
        meta = await asyncio.to_thread(market_data_client.resolve_symbol_meta, underlying)
        if meta:
            instrument_id = str(meta.get("id", ""))

    if not instrument_id:
        return "2026-03-10"

    expiries = await asyncio.to_thread(market_data_client.get_option_expiries, instrument_id)
    if not expiries:
        return "2026-03-10"

    now_ist = datetime.now(IST)
    for expiry in expiries:
        expiry_dt = datetime.combine(expiry.date(), time(15, 30, tzinfo=IST))
        if expiry_dt > now_ist:
            return expiry.strftime("%Y-%m-%d")
    return expiries[-1].strftime("%Y-%m-%d")


def _format_script(underlying: str, expiry: str, strike: float, option_type: str) -> str:
    date_obj = datetime.strptime(expiry, "%Y-%m-%d")
    return f"{underlying}{date_obj.strftime('%d%b').upper()}{int(strike)}{option_type}"


async def _build_contract(underlying: str, strike: float, option_type: Literal["CE", "PE"]) -> FNOContract:
    expiry = await _get_nearest_expiry(underlying)
    script = _format_script(underlying, expiry, strike, option_type)
    lot_size = LOT_SIZE_MAP.get(underlying, 1)
    return FNOContract(
        script=script,
        underlying=underlying,
        expiry=expiry,
        expiry_time_ist="15:30",
        strike=float(strike),
        option_type=option_type,
        exchange="NFO",
        lot_size=lot_size,
    )


async def _resolve_contract_from_input(raw_script: str) -> FNOContract:
    script = raw_script.strip().upper()
    contract_dict = get_fno_contract(script)
    if contract_dict:
        return FNOContract(**contract_dict)

    parsed = SCRIPT_PATTERN.fullmatch(script)
    if parsed:
        underlying, day_txt, mon_txt, strike_txt, option_type = parsed.groups()
        month = MONTH_MAP.get(mon_txt)
        if not month:
            raise HTTPException(status_code=404, detail="Script not supported")

        day = int(day_txt)
        now_ist = datetime.now(IST)
        year = now_ist.year
        try:
            candidate = datetime(year, month, day, 15, 30, tzinfo=IST)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Script not supported") from exc
        if candidate <= now_ist:
            candidate = datetime(year + 1, month, day, 15, 30, tzinfo=IST)

        return FNOContract(
            script=script,
            underlying=underlying,
            expiry=candidate.strftime("%Y-%m-%d"),
            expiry_time_ist="15:30",
            strike=float(strike_txt),
            option_type=option_type,
            exchange="NFO",
            lot_size=LOT_SIZE_MAP.get(underlying, 1),
        )

    if script in {"NIFTY", "BANKNIFTY", "RELIANCE", "BDL", "SBIN", "TCS"}:
        stock = StockCoreNormalized(**(await get_stock_core(script)))
        if stock.ltp is None:
            raise HTTPException(status_code=404, detail="Script not supported")
        step = 50 if script == "NIFTY" else (100 if script == "BANKNIFTY" else (20 if stock.ltp > 300 else 10))
        strike = round(stock.ltp / step) * step
        return await _build_contract(script, strike, "CE")

    raise HTTPException(status_code=404, detail="Script not supported")


async def _build_signal_for_contract(contract: FNOContract, refreshed_at: str) -> FNOSignalResponse:
    minutes_to_expiry = get_minutes_to_expiry(contract)
    _validate_expiry_guard(minutes_to_expiry)
    stock_data = StockCoreNormalized(**(await get_stock_core(contract.underlying)))
    try:
        option_ltp = await asyncio.to_thread(
            market_data_client.fetch_option_ltp_for_contract,
            contract.model_dump(),
        )
    except ValueError:
        if stock_data.ltp is None:
            raise
        if contract.underlying == "NIFTY":
            step = 50
        elif contract.underlying == "BANKNIFTY":
            step = 100
        else:
            step = 20 if stock_data.ltp > 300 else 10

        fallback_contract = contract.model_copy(
            update={"strike": float(round(stock_data.ltp / step) * step)}
        )
        try:
            option_ltp = await asyncio.to_thread(
                market_data_client.fetch_option_ltp_for_contract,
                fallback_contract.model_dump(),
            )
        except Exception:
            intrinsic = (
                max(stock_data.ltp - contract.strike, 0)
                if contract.option_type == "CE"
                else max(contract.strike - stock_data.ltp, 0)
            )
            time_value = max(stock_data.ltp * 0.002, 5)
            option_ltp = round(intrinsic + time_value, 2)
    return build_fno_signal(contract, stock_data, option_ltp, refreshed_at, minutes_to_expiry)


async def _safe_signal(contract: FNOContract, refreshed_at: str, sem: asyncio.Semaphore) -> FNOSignalResponse | None:
    async with sem:
        try:
            return await _build_signal_for_contract(contract, refreshed_at)
        except Exception:
            return None


async def _build_report(index_name: Literal["NIFTY", "BANKNIFTY"], weighted: bool) -> IndexAnalysisReport:
    weight_source = NIFTY_WEIGHT_PROXY if index_name == "NIFTY" else BANKNIFTY_WEIGHT_PROXY
    symbols = [symbol for symbol, _ in weight_source]
    rows = await asyncio.gather(*[get_stock_core(symbol) for symbol in symbols])

    contributions: list[tuple[str, float]] = []
    bullish_count = 0
    total_weight = 0.0
    total_momentum = 0.0
    for idx, row in enumerate(rows):
        stock = StockCoreNormalized(**row)
        day_change = 0.0
        if stock.ltp is not None and stock.prev_close is not None and stock.prev_close > 0:
            day_change = ((stock.ltp - stock.prev_close) / stock.prev_close) * 100

        if day_change > 0:
            bullish_count += 1

        weight = weight_source[idx][1] if weighted else 1.0
        total_weight += weight
        total_momentum += day_change * weight
        contributions.append((stock.symbol, day_change * weight))

    breadth_score = round((bullish_count / max(len(rows), 1)) * 100, 2)
    weighted_change = total_momentum / max(total_weight, 1)
    momentum_score = round(clamp(50 + (weighted_change * 8), 0, 100), 2)

    if momentum_score >= 58:
        bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "BULLISH"
    elif momentum_score <= 42:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    top_contributors = [f"{sym}:{round(val, 2)}" for sym, val in sorted(contributions, key=lambda x: abs(x[1]), reverse=True)[:3]]
    mode_text = "weighted constituent" if weighted else "equal constituent"

    return IndexAnalysisReport(
        report_type="with_consolidated" if weighted else "without_consolidated",
        breadth_score=breadth_score,
        momentum_score=momentum_score,
        bias=bias,
        top_contributors=top_contributors,
        summary=(
            f"{index_name} {mode_text} analysis: breadth {breadth_score} and momentum {momentum_score} suggests {bias.lower()} bias."
        ),
    )


async def _build_index_projection(index_name: Literal["NIFTY", "BANKNIFTY"], refreshed_at: str) -> IndexProjectionPane:
    stock = StockCoreNormalized(**(await get_stock_core(index_name)))
    if stock.ltp is None:
        raise HTTPException(status_code=502, detail=f"{index_name} spot unavailable")

    step = 50 if index_name == "NIFTY" else 100
    atm = round(stock.ltp / step) * step
    strike_range_min = atm - 500
    strike_range_max = atm + 500

    strikes = list(range(int(strike_range_min), int(strike_range_max) + step, step))
    contracts: list[FNOContract] = []
    for strike in strikes:
        contracts.append(await _build_contract(index_name, strike, "CE"))
        contracts.append(await _build_contract(index_name, strike, "PE"))

    sem = asyncio.Semaphore(12)
    tasks = [_safe_signal(contract, refreshed_at, sem) for contract in contracts]
    rows = [item for item in await asyncio.gather(*tasks) if item is not None]

    potential = [item for item in rows if item.is_potential_trade]
    by_strike: dict[float, list[FNOSignalResponse]] = defaultdict(list)
    for row in potential:
        by_strike[row.strike].append(row)

    paired_scripts = set()
    non_directional: list[NonDirectionalStrategy] = []
    for strike, entries in by_strike.items():
        ce = next((item for item in entries if item.option_type == "CE"), None)
        pe = next((item for item in entries if item.option_type == "PE"), None)
        if ce and pe:
            paired_scripts.add(ce.script)
            paired_scripts.add(pe.script)
            non_directional.append(
                NonDirectionalStrategy(
                    strike=strike,
                    strategy="Long Straddle (Non-Directional Strategy)",
                    ce_script=ce.script,
                    pe_script=pe.script,
                    combined_entry=round(ce.entry_price + pe.entry_price, 2),
                    rationale=(
                        "Both CE and PE at same strike passed profitability checks. "
                        "Classified as volatility strategy, not assured directional signal."
                    ),
                    confidence_score=int(round((ce.confluence_score + pe.confluence_score) / 2)),
                )
            )

    assured_signals = [
        item
        for item in potential
        if item.script not in paired_scripts and strike_range_min <= item.strike <= strike_range_max
    ]
    assured_signals.sort(key=lambda row: row.confluence_score, reverse=True)

    with_report, without_report = await asyncio.gather(
        _build_report(index_name, weighted=True),
        _build_report(index_name, weighted=False),
    )

    return IndexProjectionPane(
        index_name=index_name,
        spot=round(stock.ltp, 2),
        strike_range_min=float(strike_range_min),
        strike_range_max=float(strike_range_max),
        assured_signals=assured_signals,
        non_directional_strategies=non_directional,
        with_consolidated_report=with_report,
        without_consolidated_report=without_report,
    )


async def _build_stock_fno_signals(refreshed_at: str) -> list[FNOSignalResponse]:
    symbols = ["RELIANCE", "BDL", "SBIN", "TCS"]
    results: list[FNOSignalResponse] = []

    for symbol in symbols:
        core = StockCoreNormalized(**(await get_stock_core(symbol)))
        if core.ltp is None:
            continue

        step = 20 if core.ltp > 400 else 10
        strike = round(core.ltp / step) * step
        ce_contract = await _build_contract(symbol, strike, "CE")
        pe_contract = await _build_contract(symbol, strike, "PE")

        ce_signal = await _safe_signal(ce_contract, refreshed_at, asyncio.Semaphore(1))
        pe_signal = await _safe_signal(pe_contract, refreshed_at, asyncio.Semaphore(1))
        chosen = sorted([item for item in [ce_signal, pe_signal] if item], key=lambda row: row.confluence_score, reverse=True)
        if chosen:
            results.append(chosen[0])

    results.sort(key=lambda row: (row.is_potential_trade, row.confluence_score), reverse=True)
    return results


async def _build_multibagger_candidates(refreshed_at: str) -> list[MultibaggerCandidate]:
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
                current_rsi_level=analysis["current_rsi_level"],
                gtt_buy_price=analysis["gtt_buy_price"],
                targeted_upside_price=analysis["targeted_upside_price"],
                targeted_upside_profit_pct=analysis["targeted_upside_profit_pct"],
                analysis_refreshed_at=refreshed_at,
            )
        )

    candidates.sort(
        key=lambda row: (row.is_potential_multibagger, row.multibagger_score),
        reverse=True,
    )
    return candidates[:30]


def _position_to_response(position: dict) -> CustomPositionResponse:
    return CustomPositionResponse(
        id=position["id"],
        script=position["script"],
        underlying=position["underlying"],
        expiry_date=position["expiry_date"],
        expiry_time_ist=position.get("expiry_time_ist", "15:30"),
        lot_size=int(position.get("lot_size", 1)),
        buy_price=float(position["buy_price"]),
        created_at=position["created_at"],
        last_update=position["last_update"],
        status=position["status"],
        alert=position.get("alert"),
        latest_option_ltp=position.get("latest_option_ltp"),
        target1=position.get("target1"),
        target2=position.get("target2"),
        minutes_to_expiry=int(position.get("minutes_to_expiry", 0)),
        revised_exit_plan=position.get("revised_exit_plan", ""),
    )


async def _refresh_open_position(position: dict) -> dict:
    contract_dict = {
        "script": position["script"],
        "underlying": position["underlying"],
        "expiry": position["expiry_date"],
        "expiry_time_ist": position.get("expiry_time_ist", "15:30"),
        "strike": position["strike"],
        "option_type": position["option_type"],
        "exchange": "NFO",
        "lot_size": position.get("lot_size", 1),
    }
    contract = FNOContract(**contract_dict)
    minutes_to_expiry = get_minutes_to_expiry(contract)

    if minutes_to_expiry <= 0:
        updated = await db.custom_positions.find_one_and_update(
            {"id": position["id"]},
            {
                "$set": {
                    "status": "EXPIRED",
                    "alert": "EXPIRED",
                    "minutes_to_expiry": minutes_to_expiry,
                    "last_update": _utc_now_iso(),
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        return updated

    latest_option_ltp = await asyncio.to_thread(market_data_client.fetch_option_ltp_for_contract, contract.model_dump())
    buy_price = float(position["buy_price"])
    pnl_pct = ((latest_option_ltp - buy_price) / buy_price) if buy_price > 0 else 0.0
    revised_target1 = round(max(buy_price * 1.12, latest_option_ltp * 1.05), 2)
    revised_target2 = round(max(buy_price * 1.5, latest_option_ltp * 1.2), 2)

    alert = None
    revised_exit_plan = "Hold with trailing stop once target1 hits"
    if minutes_to_expiry <= 15:
        alert = "EXIT_URGENT_TIME"
        revised_exit_plan = "URGENT EXIT: Less than 15 minutes to expiry"
    elif pnl_pct <= -0.12:
        alert = "EXIT_URGENT_LOSS"
        revised_exit_plan = "URGENT EXIT: Loss exceeded 12% from buy"
    elif minutes_to_expiry < 60 and ((position["target1"] - latest_option_ltp) / max(latest_option_ltp, 0.01)) > 0.12:
        alert = "RISKY_PREMIUM"
        revised_exit_plan = "High premium-risk near expiry; consider reducing exposure"

    updated = await db.custom_positions.find_one_and_update(
        {"id": position["id"]},
        {
            "$set": {
                "latest_option_ltp": round(float(latest_option_ltp), 2),
                "target1": revised_target1,
                "target2": revised_target2,
                "minutes_to_expiry": minutes_to_expiry,
                "alert": alert,
                "last_update": _utc_now_iso(),
                "revised_exit_plan": revised_exit_plan,
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return updated


@api_router.get("/")
async def root():
    return {"message": "AI Stock Research API"}


@api_router.post("/auth/access", response_model=AccessResponse)
async def auth_access(payload: AccessRequest):
    await _ensure_owner_exists()
    credential = (payload.username or payload.password or "").strip()
    if not credential:
        raise HTTPException(status_code=400, detail="Username is required")

    if credential == LEGACY_OWNER_ALIAS:
        credential = OWNER_BOOTSTRAP_USERNAME
    credential = _validate_username(credential)

    user = await _get_user_by_username(credential)
    if not user and credential == OWNER_BOOTSTRAP_USERNAME:
        user = await _ensure_owner_exists()
    if not user:
        raise HTTPException(status_code=404, detail="Username not found. Please contact admin.")

    token = str(uuid.uuid4())
    SESSION_STORE[token] = {
        "user_key": user["user_key"],
        "created_at": _utc_now_iso(),
    }
    return AccessResponse(
        token=token,
        role=user["role"],
        credits=int(user.get("credits", 0)),
        user_key=user["user_key"],
        username=user["username"],
        admin_exempt=_is_credit_exempt(user),
    )


@api_router.post("/auth/logout")
async def auth_logout(
    current_user: dict = Depends(get_current_user),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _ = current_user
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        SESSION_STORE.pop(token, None)
    return {"ok": True}


@api_router.get("/auth/me", response_model=MeResponse)
async def auth_me(current_user: dict = Depends(get_current_user)):
    return MeResponse(
        role=current_user["role"],
        credits=int(current_user.get("credits", 0)),
        user_key=current_user["user_key"],
        username=current_user["username"],
        admin_exempt=_is_credit_exempt(current_user),
    )


@api_router.get("/admin/users", response_model=List[AdminUserView])
async def admin_list_users(admin_user: dict = Depends(get_admin_user)):
    if _is_owner(admin_user):
        rows = await db.app_users.find({}, {"_id": 0}).to_list(5000)
    else:
        rows = await db.app_users.find(
            {
                "$or": [
                    {"username": admin_user["username"]},
                    {"created_by": admin_user["username"]},
                    {"role": "owner"},
                ]
            },
            {"_id": 0},
        ).to_list(5000)
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    unique_rows = []
    seen_usernames = set()
    for row in rows:
        username = row.get("username")
        if not username:
            continue
        if username in seen_usernames:
            continue
        seen_usernames.add(username)
        unique_rows.append(row)
    return [_map_user_view(row) for row in unique_rows]


@api_router.post("/admin/users", response_model=AdminUserView)
async def admin_create_user(payload: AdminCreateUserRequest, admin_user: dict = Depends(get_admin_user)):
    username = (payload.username or payload.password or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    username = _validate_username(username)

    if await _get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already exists")

    role = payload.role
    if admin_user["role"] == "sub_admin":
        if role != "user":
            raise HTTPException(status_code=403, detail="Sub-Admin can create only Basic Users")
        if int(admin_user.get("quota_used", 0)) >= int(admin_user.get("quota_limit", 0)):
            raise HTTPException(status_code=403, detail="Sub-Admin user creation quota exhausted")

    doc = {
        "user_key": str(uuid.uuid4()),
        "username": username,
        "role": role,
        "credits": max(0, int(payload.initial_credits)),
        "created_at": _utc_now_iso(),
        "created_by": admin_user["username"],
        "quota_limit": max(1, int(payload.quota_limit)) if role == "sub_admin" else 0,
        "quota_used": 0,
    }
    await db.app_users.insert_one(doc)

    if admin_user["role"] == "sub_admin":
        await db.app_users.update_one(
            {"user_key": admin_user["user_key"]},
            {"$inc": {"quota_used": 1}},
        )

    return _map_user_view(doc)


@api_router.patch("/admin/users/{user_ref}/credits", response_model=AdminUserView)
async def admin_set_credits(
    user_ref: str,
    payload: AdminSetCreditsRequest,
    admin_user: dict = Depends(get_admin_user),
):
    target = await _get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "owner" and not _is_owner(admin_user):
        raise HTTPException(status_code=403, detail="Only Owner can modify Owner")

    if admin_user["role"] == "sub_admin":
        if target.get("created_by") != admin_user["username"] or target["role"] != "user":
            raise HTTPException(status_code=403, detail="Sub-Admin can modify only own basic users")

    updated = await db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": {"credits": max(0, int(payload.credits))}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return _map_user_view(updated)


@api_router.patch("/admin/users/{user_ref}/quota", response_model=AdminUserView)
async def admin_set_quota(
    user_ref: str,
    payload: AdminSetQuotaRequest,
    owner_user: dict = Depends(get_owner_user),
):
    _ = owner_user
    target = await _get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] != "sub_admin":
        raise HTTPException(status_code=400, detail="Quota applies only to Sub-Admin")

    updated = await db.app_users.find_one_and_update(
        {"user_key": target["user_key"]},
        {"$set": {"quota_limit": max(1, int(payload.quota_limit))}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    return _map_user_view(updated)


@api_router.delete("/admin/users/{user_ref}")
async def admin_delete_user(user_ref: str, admin_user: dict = Depends(get_admin_user)):
    target = await _get_user_by_ref(user_ref)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "owner":
        raise HTTPException(status_code=400, detail="Owner cannot be deleted")

    if admin_user["role"] == "sub_admin":
        if target.get("created_by") != admin_user["username"] or target["role"] != "user":
            raise HTTPException(status_code=403, detail="Sub-Admin can delete only own basic users")

    await db.app_users.delete_one({"user_key": target["user_key"]})
    for token, session in list(SESSION_STORE.items()):
        if session.get("user_key") == target["user_key"]:
            SESSION_STORE.pop(token, None)
    return {"deleted": True}


@api_router.post("/multibagger/generate", response_model=MultibaggerGenerateResponse)
async def generate_multibaggers(current_user: dict = Depends(get_current_user)):
    updated_user, charged = await _consume_credits(current_user, 1)
    refreshed_at = _utc_now_iso()
    candidates = await _build_multibagger_candidates(refreshed_at)
    potential_count = len([row for row in candidates if row.is_potential_multibagger])
    return MultibaggerGenerateResponse(
        cost_charged=charged,
        credits_remaining=int(updated_user.get("credits", 0)),
        analysis_refreshed_at=refreshed_at,
        candidates=candidates,
        potential_count=potential_count,
    )


@api_router.post("/fno/generate", response_model=FNOGenerateResponse)
async def generate_fno_signals(payload: FNOGenerateRequest, current_user: dict = Depends(get_current_user)):
    updated_user, charged = await _consume_credits(current_user, 2)
    refreshed_at = _utc_now_iso()

    nifty_projection, banknifty_projection, stock_signals = await asyncio.gather(
        _build_index_projection("NIFTY", refreshed_at),
        _build_index_projection("BANKNIFTY", refreshed_at),
        _build_stock_fno_signals(refreshed_at),
    )

    potential_signals = [
        *nifty_projection.assured_signals,
        *banknifty_projection.assured_signals,
    ]
    signals = sorted(potential_signals, key=lambda row: row.confluence_score, reverse=True)

    custom_signal = None
    if payload.custom_script:
        contract = await _resolve_contract_from_input(payload.custom_script)
        try:
            custom_signal = await _build_signal_for_contract(contract, refreshed_at)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    top_pool = [*signals, *stock_signals]
    if custom_signal:
        top_pool.append(custom_signal)
    top_trades = sorted(top_pool, key=lambda row: (row.is_potential_trade, row.confluence_score), reverse=True)[:4]

    return FNOGenerateResponse(
        cost_charged=charged,
        credits_remaining=int(updated_user.get("credits", 0)),
        analysis_refreshed_at=refreshed_at,
        signals=signals,
        potential_signals=[row for row in signals if row.is_potential_trade],
        top_trades=top_trades,
        custom_signal=custom_signal,
        nifty_projection=nifty_projection,
        banknifty_projection=banknifty_projection,
        stock_signals=stock_signals,
    )


@api_router.post("/fno/custom-position", response_model=CustomPositionCreateResponse)
async def create_custom_position(
    payload: CustomPositionCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if payload.buy_price <= 0:
        raise HTTPException(status_code=400, detail="Buy price must be greater than 0")

    contract = await _resolve_contract_from_input(payload.script)
    minutes_to_expiry = get_minutes_to_expiry(contract)
    _validate_expiry_guard(minutes_to_expiry)

    updated_user, charged = await _consume_credits(current_user, 2)
    latest_option_ltp = await asyncio.to_thread(market_data_client.fetch_option_ltp_for_contract, contract.model_dump())

    position_id = str(uuid.uuid4())
    now_iso = _utc_now_iso()
    doc = {
        "id": position_id,
        "user_key": current_user["user_key"],
        "script": contract.script,
        "underlying": contract.underlying,
        "expiry_date": contract.expiry,
        "expiry_time_ist": contract.expiry_time_ist,
        "strike": contract.strike,
        "option_type": contract.option_type,
        "lot_size": contract.lot_size,
        "buy_price": round(float(payload.buy_price), 2),
        "created_at": now_iso,
        "last_update": now_iso,
        "status": "OPEN",
        "alert": None,
        "latest_option_ltp": round(float(latest_option_ltp), 2),
        "target1": round(float(payload.buy_price) * 1.12, 2),
        "target2": round(float(payload.buy_price) * 1.5, 2),
        "minutes_to_expiry": minutes_to_expiry,
        "revised_exit_plan": "Hold with trailing stop once target1 hits",
    }

    await db.custom_positions.insert_one(doc)
    return CustomPositionCreateResponse(
        cost_charged=charged,
        credits_remaining=int(updated_user.get("credits", 0)),
        position=_position_to_response(doc),
    )


@api_router.get("/fno/custom-positions", response_model=List[CustomPositionResponse])
async def list_custom_positions(current_user: dict = Depends(get_current_user)):
    rows = await db.custom_positions.find(
        {"user_key": current_user["user_key"], "status": "OPEN"},
        {"_id": 0},
    ).to_list(200)

    refreshed: list[CustomPositionResponse] = []
    for row in rows:
        try:
            updated = await _refresh_open_position(row)
            if updated and updated.get("status") == "OPEN":
                refreshed.append(_position_to_response(updated))
        except Exception:
            continue

    refreshed.sort(key=lambda item: item.created_at, reverse=True)
    return refreshed


@api_router.post("/fno/custom-position/{position_id}/close")
async def close_custom_position(position_id: str, current_user: dict = Depends(get_current_user)):
    updated = await db.custom_positions.find_one_and_update(
        {
            "id": position_id,
            "user_key": current_user["user_key"],
            "status": "OPEN",
        },
        {
            "$set": {
                "status": "CLOSED",
                "last_update": _utc_now_iso(),
                "alert": "CLOSED_BY_USER",
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Custom position not found")
    return {"closed": True, "id": position_id}


@api_router.get("/fno/scripts/search", response_model=ScriptSearchResult)
async def search_scripts(q: str = Query(default="")):
    query = q.strip().upper()
    suggestions = []
    for row in FNO_CONTRACTS:
        script = row["script"]
        if not query or query in script:
            suggestions.append(script)
    suggestions = sorted(set(suggestions))[:30]
    return ScriptSearchResult(query=query, suggestions=suggestions)


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


# Backward compatibility endpoints
@api_router.get("/multibagger/candidates", response_model=List[MultibaggerCandidate])
async def get_multibagger_candidates(refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    return await _build_multibagger_candidates(_utc_now_iso())


@api_router.get("/fno/contracts", response_model=List[FNOContract])
async def get_fno_contracts():
    return [FNOContract(**row) for row in FNO_CONTRACTS]


@api_router.get("/fno/signal/{script}", response_model=FNOSignalResponse)
async def get_single_fno_signal(script: str, refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    contract = await _resolve_contract_from_input(script)
    try:
        return await _build_signal_for_contract(contract, _utc_now_iso())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@api_router.get("/fno/signals/index", response_model=List[FNOSignalResponse])
async def get_index_fno_signals(refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    refreshed_at = _utc_now_iso()
    nifty_projection, bank_projection = await asyncio.gather(
        _build_index_projection("NIFTY", refreshed_at),
        _build_index_projection("BANKNIFTY", refreshed_at),
    )
    return sorted(
        [*nifty_projection.assured_signals, *bank_projection.assured_signals],
        key=lambda row: row.confluence_score,
        reverse=True,
    )


@api_router.get("/fno/signals/potential", response_model=List[FNOSignalResponse])
async def get_potential_index_signals(refresh_nonce: str | None = Query(default=None)):
    _ = refresh_nonce
    rows = await get_index_fno_signals(refresh_nonce=None)
    if rows:
        return rows[:6]
    return rows


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
