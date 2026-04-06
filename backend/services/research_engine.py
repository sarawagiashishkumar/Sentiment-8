"""
Research Engine — Thin orchestrator that re-exports all batch modules.
All imports in server.py / tests continue to use:
    from services.research_engine import <function>
without any change.
"""
from __future__ import annotations

# ── Core indicators (basic) ───────────────────────────────────────────────────
from services.indicators import (
    HORIZON_TRADING_DAYS,
    compute_rsi,
    compute_macd,
    compute_bollinger,
    compute_atr,
    compute_adx,
    compute_obv,
    compute_sma,
    compute_ema,
    compute_stochastic,
    compute_historical_volatility,
    compute_realistic_price_bands,
    classify_market_regime,
    check_stock_eligibility,
    compute_atr_based_fno_targets,
    compute_portfolio_risk_metrics,
)

# ── Advanced indicators (Batch 1) ─────────────────────────────────────────────
from services.advanced_indicators import (
    compute_williams_r,
    compute_cci,
    compute_vpt,
    compute_ad_line,
    compute_ichimoku,
    compute_fibonacci_levels,
    compute_pivot_points,
    compute_support_resistance,
    detect_rsi_divergence,
    detect_candlestick_patterns,
    compute_multiframe_trend,
    detect_chart_patterns,
)

# ── Technical core (full snapshot + confluence + verdict) ─────────────────────
from services.technical_core import (
    compute_full_technical_snapshot,
    check_urgent_exit,
    compute_technical_confluence_bonus,
    compute_portfolio_verdict,
)

# ── Forensic audit (Batch 2) ──────────────────────────────────────────────────
from services.forensic_audit import (
    compute_altman_z_score,
    compute_earnings_quality,
    compute_forensic_red_flags,
    compute_roic_vs_wacc,
    compute_growth_quality,
    compute_forensic_audit,
)

# ── Macro & regime context (Batch 3) ─────────────────────────────────────────
from services.macro_context import (
    REGIME_STRATEGY_GRID,
    SECTOR_MACRO_IMPACT_MAP,
    classify_market_regime_enhanced,
    compute_macro_context,
    get_sector_macro_beneficiaries,
    get_all_macro_events,
)

# ── Portfolio risk analytics (Batch 4) ───────────────────────────────────────
from services.portfolio_risk import (
    STRESS_SCENARIOS,
    RBI_MEETING_DATES_2025_2026,
    FED_MEETING_DATES_2025_2026,
    compute_portfolio_correlation_matrix,
    compute_portfolio_stress_tests,
    compute_diversification_audit,
    compute_upcoming_catalysts,
    merge_duplicate_holdings,
    compute_master_stock_snapshot,
)

# ── Strategy library & state machine (Batch 5) ───────────────────────────────
from services.strategy_library import (
    STRATEGY_LIBRARY,
    NIFTY50_WEIGHTS,
    BANKNIFTY_WEIGHTS,
    SIGNAL_STATES,
    SIGNAL_TRANSITIONS,
    get_strategy_by_id,
    get_eligible_strategies,
    select_strategy_for_signal,
    update_backtest_stats,
    check_strategy_eligible,
    transition_signal_state,
    compute_index_constituent_bias,
)

__all__ = [
    # Core
    "HORIZON_TRADING_DAYS",
    "compute_rsi", "compute_macd", "compute_bollinger", "compute_atr", "compute_adx",
    "compute_obv", "compute_sma", "compute_ema", "compute_stochastic",
    "compute_historical_volatility", "compute_realistic_price_bands",
    "classify_market_regime", "check_stock_eligibility",
    "compute_atr_based_fno_targets", "compute_portfolio_risk_metrics",
    # Advanced
    "compute_williams_r", "compute_cci", "compute_vpt", "compute_ad_line",
    "compute_ichimoku", "compute_fibonacci_levels", "compute_pivot_points",
    "compute_support_resistance", "detect_rsi_divergence",
    "detect_candlestick_patterns", "compute_multiframe_trend", "detect_chart_patterns",
    # Technical core
    "compute_full_technical_snapshot", "check_urgent_exit",
    "compute_technical_confluence_bonus", "compute_portfolio_verdict",
    # Forensic
    "compute_altman_z_score", "compute_earnings_quality",
    "compute_forensic_red_flags", "compute_roic_vs_wacc",
    "compute_growth_quality", "compute_forensic_audit",
    # Macro
    "REGIME_STRATEGY_GRID", "SECTOR_MACRO_IMPACT_MAP",
    "classify_market_regime_enhanced", "compute_macro_context",
    "get_sector_macro_beneficiaries", "get_all_macro_events",
    # Portfolio risk
    "STRESS_SCENARIOS",
    "compute_portfolio_correlation_matrix", "compute_portfolio_stress_tests",
    "compute_diversification_audit", "compute_upcoming_catalysts",
    "merge_duplicate_holdings", "compute_master_stock_snapshot",
    # Strategy
    "STRATEGY_LIBRARY", "NIFTY50_WEIGHTS", "BANKNIFTY_WEIGHTS",
    "SIGNAL_STATES", "SIGNAL_TRANSITIONS",
    "get_strategy_by_id", "get_eligible_strategies", "select_strategy_for_signal",
    "update_backtest_stats", "check_strategy_eligible", "transition_signal_state",
    "compute_index_constituent_bias",
]
