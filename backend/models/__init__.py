"""
Pydantic models for the Trading Research application.
All models are defined here and re-exported.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ── Auth & Session ────────────────────────────────────────────────────────────

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
    role: str  # "owner" | "sub_admin" | "user"
    credits: float
    user_key: str
    username: str
    admin_exempt: bool
    fno_budget: float = 500000.0
    account_risk_pct: float = 2.0


class MeResponse(BaseModel):
    role: str  # "owner" | "sub_admin" | "user"
    credits: float
    user_key: str
    username: str
    admin_exempt: bool
    fno_budget: float = 500000.0
    account_risk_pct: float = 2.0
    package: str = "free"
    suspended: bool = False


class UserSettingsUpdate(BaseModel):
    fno_budget: float | None = None
    account_risk_pct: float | None = None


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminUserView(BaseModel):
    user_key: str
    username: str
    role: str  # "owner" | "sub_admin" | "user"
    credits: float
    created_at: str
    created_by: str
    quota_limit: int
    quota_used: int
    credential_label: str
    suspended: bool = False
    package: str = "free"


class AdminCreateUserRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    role: str = "user"  # "sub_admin" | "user"
    initial_credits: float = 0
    quota_limit: int = 10


class AdminSetCreditsRequest(BaseModel):
    credits: float


class AdminSetQuotaRequest(BaseModel):
    quota_limit: int


class AdminUserProfileUpdateRequest(BaseModel):
    username: str | None = None
    role: str | None = None  # "owner" | "sub_admin" | "user"


class DomainMappingCreateRequest(BaseModel):
    domain: str
    target_record: str
    record_type: str = "A"


class DomainMappingStatusUpdateRequest(BaseModel):
    status: str  # "PENDING" | "ACTIVE" | "FAILED"


class ApiControlUpdateRequest(BaseModel):
    kite_data_enabled: bool | None = None
    moneycontrol_data_enabled: bool | None = None
    strict_live_only: bool | None = None


class MacroEventsUpdateRequest(BaseModel):
    events: list[str]


# ── Stock Data ────────────────────────────────────────────────────────────────

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


# ── Multibagger ───────────────────────────────────────────────────────────────

_FLOAT_FIELDS_MB: set[str] = {
    "ltp", "market_cap_cr", "pe_ratio", "year_high", "year_low",
    "upside_to_52w_high_pct", "pb_ratio_est", "peg_ratio_est",
    "current_rsi_level", "gtt_buy_price",
    "roe", "roce", "beneish_m_score", "eps_growth_pct",
    "debt_to_equity", "current_ratio", "gross_margin",
    "pct_below_ath", "roic_vs_wacc", "fcf_yield_val", "eps_cagr_3y",
}


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
    targeted_upside_price: dict[str, Any]
    targeted_upside_profit_pct: dict[str, Any]
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
    vol_bands: dict[str, Any] | None = None
    # Price Band Upgrade fields
    price_bands: dict[str, Any] | None = None
    band_computation_status: str | None = None
    forensic_flag: str | None = None
    conviction_penalty: int = 0
    sf2_high_conviction: bool = False
    macro_tailwind: bool = False
    pli_beneficiary: bool = False
    govt_capex_beneficiary: bool = False
    trend_alignment: str | None = None
    regime_label: str | None = None
    pct_below_ath: float | None = None
    roic_vs_wacc: float | None = None
    fcf_yield_val: float | None = None
    eps_cagr_3y: float | None = None
    ebitda_margin_trend: str | None = None
    data_source: str | None = None
    cache_as_of: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _sanitize_nan_floats(cls, values: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict):
            return values
        for field in _FLOAT_FIELDS_MB:
            v = values.get(field)
            if v is None:
                continue
            try:
                f = float(v)
                values[field] = None if (math.isnan(f) or math.isinf(f)) else f
            except (TypeError, ValueError):
                values[field] = None
        return values


# ── F&O ───────────────────────────────────────────────────────────────────────

class FNOContract(BaseModel):
    script: str
    underlying: str
    expiry: str
    expiry_time_ist: str = "15:30"
    strike: float
    option_type: str  # "CE" | "PE"
    exchange: str
    lot_size: int


class FNOSignalResponse(BaseModel):
    script: str
    underlying: str
    expiry: str
    strike: float
    option_type: str  # "CE" | "PE"
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
    direction: str  # "BULLISH" | "BEARISH" | "NEUTRAL"
    strategy: str
    strategy_library_id: str | None = None
    strategy_library_name: str | None = None
    market_regime: str | None = None
    macro_context: dict[str, Any] | None = None
    index_breadth: dict[str, Any] | None = None
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
    near_expiry_badge: bool = False
    expiry_today_badge: bool = False
    best_budget_entry: float | None = None
    budget_entry_alert: bool = False
    trigger_factors: list[str]
    confluence_score: int
    signal_quality: str  # "HIGH" | "MEDIUM" | "LOW"
    conviction_level: str = "MEDIUM"
    is_potential_trade: bool
    minutes_to_expiry: int
    expiry_risk: str  # "LOW" | "MEDIUM" | "HIGH"
    data_source: str  # "LIVE_OPTION_CHAIN" | "MODELED_FROM_SPOT"
    analysis_refreshed_at: str
    # Option chain analytics
    max_pain: float | None = None
    iv_rank: float | None = None
    iv_rank_52w: float | None = None
    atm_iv: float | None = None
    oi_buildup: str | None = None
    gex: float | None = None
    # Position sizing
    not_affordable: bool = False
    sizing_info: dict[str, Any] | None = None
    # V2 Scoring Breakdown
    confluence_score_v2: float | None = None
    score_bucket_A: float | None = None
    score_bucket_B: float | None = None
    score_bucket_C: float | None = None
    score_bucket_D: float | None = None
    score_suppress_reason: str | None = None
    score_regime_label: str | None = None
    score_flow_band: str | None = None
    score_news_flag: str | None = None


class NonDirectionalStrategy(BaseModel):
    strike: float
    strategy: str
    ce_script: str
    pe_script: str
    combined_entry: float
    rationale: str
    confidence_score: int


class IndexAnalysisReport(BaseModel):
    report_type: str  # "with_consolidated" | "without_consolidated"
    breadth_score: float
    momentum_score: float
    bias: str  # "BULLISH" | "BEARISH" | "NEUTRAL"
    top_contributors: list[str]
    summary: str


class IndexProjectionPane(BaseModel):
    index_name: str  # "NIFTY" | "BANKNIFTY"
    spot: float
    strike_range_min: float
    strike_range_max: float
    assured_signals: list[FNOSignalResponse]
    watchlist_signals: list[FNOSignalResponse]
    non_directional_strategies: list[NonDirectionalStrategy]
    rejection_note: str | None = None
    with_consolidated_report: IndexAnalysisReport
    without_consolidated_report: IndexAnalysisReport


class FNOGenerateRequest(BaseModel):
    custom_script: str | None = None


class FNOGenerateResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    analysis_refreshed_at: str
    signals: list[FNOSignalResponse]
    potential_signals: list[FNOSignalResponse]
    top_trades: list[FNOSignalResponse]
    custom_signal: FNOSignalResponse | None = None
    nifty_projection: IndexProjectionPane
    banknifty_projection: IndexProjectionPane
    stock_signals: list[FNOSignalResponse]
    no_signals_alert: str | None = None
    market_regime: dict[str, Any] | None = None
    market_session: dict[str, Any] | None = None


class MultibaggerGenerateResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    analysis_refreshed_at: str
    candidates: list[MultibaggerCandidate]
    potential_count: int


class ScriptSearchResult(BaseModel):
    query: str
    suggestions: list[str]


# ── Portfolio ─────────────────────────────────────────────────────────────────

class PortfolioPositionInput(BaseModel):
    symbol: str
    avg_price: float
    quantity: float


class PortfolioAnalyzeRequest(BaseModel):
    positions: list[PortfolioPositionInput]


class PortfolioHorizonRange(BaseModel):
    upside_pct: float
    downside_pct: float
    flag: str  # "GREEN" | "RED"


class PortfolioExpectedSignal(BaseModel):
    max_expected_price: float
    min_expected_price: float | None = None
    amount_signal: str
    percent_signal: str
    direction: str  # "PROFIT" | "LOSS"


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
    value_flag: str  # "Attractive" | "Fair" | "Expensive"
    price_zone: str  # "Near 52W low" | "Mid range" | "Near 52W high"
    momentum_proxy: str  # "Positive trend" | "Flat" | "Negative trend"
    quality_proxy: str  # "Stable quality" | "Speculative" | "Moderate"
    expected_ranges: dict[str, PortfolioHorizonRange]
    expected_signals: dict[str, PortfolioExpectedSignal]
    recommendation: str
    comments: str
    master_snapshot: dict[str, Any] | None = None
    altman_z_zone: str | None = None
    roic_wacc_spread: float | None = None
    piotroski_score: int | None = None
    beneish_m_score: float | None = None
    # Price Band + Verdict Integration
    price_bands: dict[str, Any] | None = None
    band_error: str | None = None
    holding_verdict: str | None = None


class PortfolioAnalyzeResponse(BaseModel):
    cost_charged: float
    credits_remaining: float
    parsed_positions_count: int
    stocks: list[PortfolioStockAnalysis]
    failed_symbols: list[str] = []
    portfolio_risk_metrics: dict[str, Any] | None = None
    enhanced_analytics: dict[str, Any] | None = None


# ── Custom Positions ──────────────────────────────────────────────────────────

class CustomPositionCreateRequest(BaseModel):
    script: str
    buy_price: float
    quantity_lots: int = Field(default=1, ge=1, le=500)


class CustomPositionSellRequest(BaseModel):
    sold_price: float
    confirm: bool = True


class MonitoringEvent(BaseModel):
    type: str  # NEWS_IMPACT | REGIME_SHIFT | URGENT_EXIT
    symbol: str = ""
    underlying: str = ""
    script: str = ""
    direction: str = ""
    timestamp: str = ""
    severity: str = "MEDIUM"
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


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
    status: str  # "OPEN" | "CLOSED" | "EXPIRED" | "SOLD"
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


# ── Exports ───────────────────────────────────────────────────────────────────

__all__: list[str] = [
    "StatusCheck", "StatusCheckCreate",
    "AccessRequest", "AccessResponse", "MeResponse", "UserSettingsUpdate",
    "AdminUserView", "AdminCreateUserRequest", "AdminSetCreditsRequest",
    "AdminSetQuotaRequest", "AdminUserProfileUpdateRequest",
    "DomainMappingCreateRequest", "DomainMappingStatusUpdateRequest",
    "ApiControlUpdateRequest", "MacroEventsUpdateRequest",
    "StockCoreNormalized",
    "MultibaggerCandidate", "MultibaggerGenerateResponse",
    "FNOContract", "FNOSignalResponse", "NonDirectionalStrategy",
    "IndexAnalysisReport", "IndexProjectionPane",
    "FNOGenerateRequest", "FNOGenerateResponse",
    "ScriptSearchResult",
    "PortfolioPositionInput", "PortfolioAnalyzeRequest",
    "PortfolioHorizonRange", "PortfolioExpectedSignal",
    "PortfolioStockAnalysis", "PortfolioAnalyzeResponse",
    "CustomPositionCreateRequest", "CustomPositionSellRequest",
    "MonitoringEvent", "CustomPositionResponse", "CustomPositionCreateResponse",
]
