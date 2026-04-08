"""
Pydantic models for the Trading Research application.
All models are defined here and re-exported.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    credits: float
    user_key: str
    username: str
    admin_exempt: bool


class MeResponse(BaseModel):
    role: Literal["owner", "sub_admin", "user"]
    credits: float
    user_key: str
    username: str
    admin_exempt: bool


class AdminUserView(BaseModel):
    user_key: str
    username: str
    role: Literal["owner", "sub_admin", "user"]
    credits: float
    created_at: str
    created_by: str
    quota_limit: int
    quota_used: int
    credential_label: str


class AdminCreateUserRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    role: Literal["sub_admin", "user"] = "user"
    initial_credits: float = 0
    quota_limit: int = 10


class AdminSetCreditsRequest(BaseModel):
    credits: float


class AdminSetQuotaRequest(BaseModel):
    quota_limit: int


class AdminUserProfileUpdateRequest(BaseModel):
    username: str | None = None
    role: Literal["owner", "sub_admin", "user"] | None = None


class DomainMappingCreateRequest(BaseModel):
    domain: str
    target_record: str
    record_type: Literal["A"] = "A"


class DomainMappingStatusUpdateRequest(BaseModel):
    status: Literal["PENDING", "ACTIVE", "FAILED"]


class ApiControlUpdateRequest(BaseModel):
    kite_data_enabled: bool | None = None
    moneycontrol_data_enabled: bool | None = None
    strict_live_only: bool | None = None


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
    thesis: str
    analysis_refreshed_at: str
    roe: float | None = None
    roce: float | None = None
    piotroski_score: int | None = None
    beneish_m_score: float | None = None
    eps_growth_pct: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    gross_margin: float | None = None
    vol_bands: dict | None = None

    from pydantic import model_validator

    @model_validator(mode="before")
    @classmethod
    def _sanitize_nan_floats(cls, values):
        import math
        _float_fields = {
            "ltp", "market_cap_cr", "pe_ratio", "year_high", "year_low",
            "upside_to_52w_high_pct", "pb_ratio_est", "peg_ratio_est",
            "current_rsi_level", "gtt_buy_price",
            "roe", "roce", "beneish_m_score", "eps_growth_pct",
            "debt_to_equity", "current_ratio", "gross_margin",
        }
        if isinstance(values, dict):
            for field in _float_fields:
                v = values.get(field)
                if v is not None:
                    try:
                        f = float(v)
                        if math.isnan(f) or math.isinf(f):
                            values[field] = None
                    except (TypeError, ValueError):
                        values[field] = None
        return values


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
    underlying_day_high: float | None = None
    underlying_day_low: float | None = None
    underlying_day_change_pct: float | None = None
    underlying_bias_score: float | None = None
    option_ltp: float
    option_day_high: float | None = None
    option_day_low: float | None = None
    ltp_margin_to_t1_amount: float
    ltp_margin_to_t1_pct: float
    achievable_profit_pct: float
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    strategy: str
    strategy_library_id: str | None = None
    strategy_library_name: str | None = None
    market_regime: str | None = None
    macro_context: dict | None = None
    index_breadth: dict | None = None
    entry_price: float
    stop_loss: float
    target1: float
    target2: float
    risk_reward_target1: float
    risk_reward_target2: float
    max_ltp_projection: float | None = None
    best_exit_days: int | None = None
    best_exit_price: float | None = None
    remaining_trading_days: int = 0
    best_exit_date_str: str | None = None
    near_expiry_badge: bool = False   # True when remaining_trading_days == 2 (next-day expiry)
    expiry_today_badge: bool = False  # True when option expires TODAY (same-day expiry)
    best_budget_entry: float | None = None    # Pullback entry: wait for this price before buying
    budget_entry_alert: bool = False          # True when meaningful pullback zone ≥ 3% below entry
    trigger_factors: List[str]
    confluence_score: int
    signal_quality: Literal["HIGH", "MEDIUM", "LOW"]
    conviction_level: str = "MEDIUM"
    is_potential_trade: bool
    minutes_to_expiry: int
    expiry_risk: Literal["LOW", "MEDIUM", "HIGH"]
    data_source: Literal["LIVE_OPTION_CHAIN", "MODELED_FROM_SPOT"]
    analysis_refreshed_at: str
    # Option chain analytics (computed from live Kite OI / IV / Gamma data)
    max_pain: float | None = None
    iv_rank: float | None = None       # IV percentile within current chain (0-100 proxy)
    iv_rank_52w: float | None = None   # True 52-week IV percentile (from iv_history)
    atm_iv: float | None = None        # Current ATM implied volatility
    oi_buildup: str | None = None      # LONG_BUILDUP | SHORT_BUILDUP | SHORT_COVERING | LONG_UNWINDING | NEUTRAL
    gex: float | None = None           # Net gamma exposure (scaled, CE-minus-PE)
    # Step 4: Position sizing annotation (additive, does NOT block signals)
    not_affordable: bool = False
    sizing_info: dict | None = None


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
    watchlist_signals: List[FNOSignalResponse]
    non_directional_strategies: List[NonDirectionalStrategy]
    rejection_note: str | None = None
    with_consolidated_report: IndexAnalysisReport
    without_consolidated_report: IndexAnalysisReport


class MultibaggerGenerateResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    analysis_refreshed_at: str
    candidates: List[MultibaggerCandidate]
    potential_count: int


class FNOGenerateRequest(BaseModel):
    custom_script: str | None = None


class FNOGenerateResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    analysis_refreshed_at: str
    signals: List[FNOSignalResponse]
    potential_signals: List[FNOSignalResponse]
    top_trades: List[FNOSignalResponse]
    custom_signal: FNOSignalResponse | None = None
    nifty_projection: IndexProjectionPane
    banknifty_projection: IndexProjectionPane
    stock_signals: List[FNOSignalResponse]
    no_signals_alert: str | None = None
    market_regime: dict | None = None
    market_session: dict | None = None


class PortfolioPositionInput(BaseModel):
    symbol: str
    avg_price: float
    quantity: float


class PortfolioAnalyzeRequest(BaseModel):
    positions: List[PortfolioPositionInput]


class PortfolioHorizonRange(BaseModel):
    upside_pct: float
    downside_pct: float
    flag: Literal["GREEN", "RED"]


class PortfolioExpectedSignal(BaseModel):
    max_expected_price: float
    min_expected_price: float | None = None
    amount_signal: str
    percent_signal: str
    direction: Literal["PROFIT", "LOSS"]


class PortfolioStockAnalysis(BaseModel):
    symbol: str
    company_name: str
    sector: str
    ltp: float
    market_cap: float | None = None
    pe_ratio: float | None = None
    year_high: float | None = None
    year_low: float | None = None
    eps: float | None = None
    avg_price: float
    quantity: float
    allocation_pct: float
    pnl_pct: float
    value_flag: Literal["Attractive", "Fair", "Expensive"]
    price_zone: Literal["Near 52W low", "Mid range", "Near 52W high"]
    momentum_proxy: Literal["Positive trend", "Flat", "Negative trend"]
    quality_proxy: Literal["Stable quality", "Speculative", "Moderate"]
    expected_ranges: dict[str, PortfolioHorizonRange]
    expected_signals: dict[str, PortfolioExpectedSignal]
    recommendation: str
    comments: str
    master_snapshot: dict | None = None
    altman_z_zone: str | None = None
    roic_wacc_spread: float | None = None
    piotroski_score: int | None = None
    beneish_m_score: float | None = None


class PortfolioAnalyzeResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    parsed_positions_count: int
    stocks: List[PortfolioStockAnalysis]
    failed_symbols: List[str] = []
    portfolio_risk_metrics: dict | None = None
    enhanced_analytics: dict | None = None


class CustomPositionCreateRequest(BaseModel):
    script: str
    buy_price: float
    quantity_lots: int = Field(default=1, ge=1, le=500)


class CustomPositionSellRequest(BaseModel):
    sold_price: float
    confirm: bool = True


class MonitoringEvent(BaseModel):
    """Batch 4: Monitoring event for sticky F&O positions."""
    type: str  # NEWS_IMPACT, REGIME_SHIFT, URGENT_EXIT
    symbol: str = ""
    underlying: str = ""
    script: str = ""
    direction: str = ""
    timestamp: str = ""
    severity: str = "MEDIUM"
    reason: str = ""
    details: dict = Field(default_factory=dict)


class CustomPositionResponse(BaseModel):
    id: str
    script: str
    underlying: str
    expiry_date: str
    expiry_time_ist: str
    lot_size: int
    quantity_lots: int = 1
    units: int = 1
    buy_price: float
    created_at: str
    last_update: str
    status: Literal["OPEN", "CLOSED", "EXPIRED", "SOLD"]
    alert: str | None = None
    latest_option_ltp: float | None = None
    target1: float | None = None
    target2: float | None = None
    buy_to_ltp_diff: float | None = None
    buy_to_ltp_pct: float | None = None
    floating_pnl_amount: float | None = None
    floating_pnl_pct: float | None = None
    ltp_to_t1_diff: float | None = None
    ltp_to_t2_diff: float | None = None
    target1_achieved: bool = False
    target2_achieved: bool = False
    can_sell: bool = False
    sold_price: float | None = None
    realized_pnl: float | None = None
    projected_exit_price: float | None = None
    best_exit_price: float | None = None
    best_exit_days: int | None = None
    best_exit_date_str: str | None = None
    remaining_trading_days: int = 0
    recovery_potential: float | None = None
    minutes_to_expiry: int
    revised_exit_plan: str
    monitoring_events: list[MonitoringEvent] = Field(default_factory=list)


class CustomPositionCreateResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    position: CustomPositionResponse


class ScriptSearchResult(BaseModel):
    query: str
    suggestions: List[str]


class MacroEventsUpdateRequest(BaseModel):
    events: List[str]


__all__ = [
    "StatusCheck", "StatusCheckCreate",
    "AccessRequest", "AccessResponse", "MeResponse",
    "AdminUserView", "AdminCreateUserRequest", "AdminSetCreditsRequest",
    "AdminSetQuotaRequest", "AdminUserProfileUpdateRequest",
    "DomainMappingCreateRequest", "DomainMappingStatusUpdateRequest",
    "ApiControlUpdateRequest", "StockCoreNormalized",
    "MultibaggerCandidate", "FNOContract", "FNOSignalResponse",
    "NonDirectionalStrategy", "IndexAnalysisReport", "IndexProjectionPane",
    "MultibaggerGenerateResponse", "FNOGenerateRequest", "FNOGenerateResponse",
    "PortfolioPositionInput", "PortfolioAnalyzeRequest",
    "PortfolioHorizonRange", "PortfolioExpectedSignal", "PortfolioStockAnalysis",
    "PortfolioAnalyzeResponse", "CustomPositionCreateRequest",
    "MonitoringEvent",
    "CustomPositionSellRequest", "CustomPositionResponse",
    "CustomPositionCreateResponse", "ScriptSearchResult",
    "MacroEventsUpdateRequest",
]
