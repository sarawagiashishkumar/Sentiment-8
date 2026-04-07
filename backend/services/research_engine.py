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

# ── Batch 1 NEW: Index Constituents & Breadth (Section 2) ─────────────────────
from services.index_constituents import (
    get_constituents,
    get_constituents_sync,
    get_all_nifty500_symbols,
    update_constituents,
    compute_weighted_breadth,
)

# ── Batch 1 NEW: Intraday Features & Order Flow (Section 3) ──────────────────
from services.intraday_features import (
    compute_multi_timeframe_emas,
    compute_vwap_features,
    compute_intraday_technicals,
    compute_order_book_imbalance,
    compute_volume_delta,
    classify_flow_band,
    classify_regime_enhanced,
    build_intraday_feature_vector,
)

# ── Batch 1 NEW: Options Chain Features (Section 3.2) ────────────────────────
from services.options_features import (
    classify_oi_buildup,
    compute_iv_rank,
    compute_bid_ask_spread,
    compute_depth_score,
    compute_enhanced_option_features,
)

# ── Batch 1 NEW: News Sentiment (Section 4) ──────────────────────────────────
from services.news_sentiment import (
    refresh_news_cache,
    get_symbol_sentiment,
    get_sector_sentiment,
    get_market_sentiment_summary,
)

# ── Batch 2 NEW: MFE/MAE Engine, Probability Models, Theta Curves ────────────
from services.mfe_mae_engine import (
    STRATEGY_PROFILES,
    DTE_BANDS,
    compute_mfe_mae_from_ohlcv,
    build_mfe_mae_library,
    build_probability_table,
    select_targets_from_probability,
    compute_empirical_theta,
    compute_forward_mfe,
    compute_best_exit_online,
    reevaluate_signal_targets,
    check_no_chasing_rule,
    check_0dte_atm_safety,
)

# ── Batch 3 NEW: 4-Bucket Confluence Score (Section 7) ───────────────────────
from services.confluence_score_v2 import (
    compute_bucket_a,
    compute_bucket_b,
    compute_bucket_c,
    compute_bucket_d,
    compute_confluence_score_v2,
    CONFLUENCE_THRESHOLD,
    BUCKET_WEIGHTS,
)

# ── Mini-Batch: F&O Universe ─────────────────────────────────────────────────
from services.fo_universe import (
    NSE_FO_STOCKS,
    INDEX_FO_UNDERLYINGS,
    get_fo_universe,
    get_fo_universe_from_db,
    get_fo_universe_size,
)

# ── Batch 4 NEW: Position Monitoring & Alerts (Section 8) ─────────────────────
from services.position_monitor import (
    recompute_position_features,
    generate_position_alerts,
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
    # NEW: Index Constituents & Breadth
    "get_constituents", "get_constituents_sync", "get_all_nifty500_symbols",
    "update_constituents", "compute_weighted_breadth",
    # NEW: Intraday Features & Order Flow
    "compute_multi_timeframe_emas", "compute_vwap_features",
    "compute_intraday_technicals", "compute_order_book_imbalance",
    "compute_volume_delta", "classify_flow_band", "classify_regime_enhanced",
    "build_intraday_feature_vector",
    # NEW: Options Chain Features
    "classify_oi_buildup", "compute_iv_rank", "compute_bid_ask_spread",
    "compute_depth_score", "compute_enhanced_option_features",
    # NEW: News Sentiment
    "refresh_news_cache", "get_symbol_sentiment", "get_sector_sentiment",
    "get_market_sentiment_summary",
    # NEW: MFE/MAE Engine (Batch 2)
    "STRATEGY_PROFILES", "DTE_BANDS",
    "compute_mfe_mae_from_ohlcv", "build_mfe_mae_library",
    "build_probability_table", "select_targets_from_probability",
    "compute_empirical_theta", "compute_forward_mfe",
    "compute_best_exit_online", "reevaluate_signal_targets",
    "check_no_chasing_rule", "check_0dte_atm_safety",
    # NEW: Confluence Score V2 (Batch 3)
    "compute_bucket_a", "compute_bucket_b", "compute_bucket_c", "compute_bucket_d",
    "compute_confluence_score_v2", "CONFLUENCE_THRESHOLD", "BUCKET_WEIGHTS",
    # NEW: F&O Universe
    "NSE_FO_STOCKS", "INDEX_FO_UNDERLYINGS",
    "get_fo_universe", "get_fo_universe_from_db", "get_fo_universe_size",
    # NEW: Position Monitoring & Alerts (Batch 4)
    "recompute_position_features", "generate_position_alerts",
]
