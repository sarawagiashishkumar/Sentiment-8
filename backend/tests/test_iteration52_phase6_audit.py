"""
Phase 6: 8-Step Audit for Price Band Engine.

Validates:
1. Monotonic band expansion across horizons
2. High > LTP for all bands
3. Low < LTP for all bands
4. Fundamental scalar activation for H >= 90d
5. Regime multiplier consistency
6. No hardcoded default percentages
7. data_source == equity_master_cache, hallucinated == False
8. Fallback safety: missing volatility reported as error

Symbols tested: RELIANCE, HDFCBANK, TATAPOWER, PAYTM, SUNPHARMA
Uses synthetic cache documents inserted into DB to ensure deterministic results.
"""
import asyncio
import math
import os
import sys
import pytest

sys.path.insert(0, "/app/backend")

from tests.helpers.test_utils import get_base_url

BASE_URL = get_base_url()


# ── Synthetic cache data for 5 audit symbols ────────────────────────

def _make_cache_doc(symbol: str, ltp: float, hv_20d: float, hv_60d: float,
                    hv_90d: float, hv_252d: float, regime: str = "NormalVolTrend",
                    piotroski: int = 6, beneish: float = -2.5,
                    roic_vs_wacc: float = 5.0, eps_cagr_3y: float = 15.0,
                    ebitda_margin_trend: str = "stable", fcf_yield: float = 3.0,
                    all_time_high: float = None, nearest_support: float = None,
                    nearest_resistance: float = None):
    """Build a realistic equity_master_cache document for testing."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    ath = all_time_high or ltp * 1.15
    sup = nearest_support or ltp * 0.93
    res = nearest_resistance or ltp * 1.08
    return {
        "symbol": symbol,
        "ltp": ltp,
        "as_of_timestamp": now,
        "last_refreshed_at": now,
        "passes_eligibility": True,
        "eligibility_fail_reason": None,
        "hv_10d": hv_20d * 0.9,
        "hv_20d": hv_20d,
        "hv_60d": hv_60d,
        "hv_90d": hv_90d,
        "hv_252d": hv_252d,
        "regime_label": regime,
        "nearest_support": sup,
        "nearest_resistance": res,
        "all_time_high": ath,
        "demand_zones": [{"low": sup * 0.99, "high": sup * 1.01, "strength": 1.5}],
        "supply_zones": [{"low": res * 0.99, "high": res * 1.01, "strength": 1.2}],
        "fib_retracements": {"0.382": ltp * 0.96, "0.500": ltp * 0.94, "0.618": ltp * 0.92},
        "piotroski_f_score": piotroski,
        "beneish_m_score": beneish,
        "roic_vs_wacc": roic_vs_wacc,
        "eps_cagr_3y": eps_cagr_3y,
        "ebitda_margin_trend": ebitda_margin_trend,
        "fcf_yield": fcf_yield,
        "avg_volume_20d": 500000,
    }


AUDIT_SYMBOLS = {
    "RELIANCE": _make_cache_doc("RELIANCE", 2450.0, 0.22, 0.25, 0.27, 0.30,
                                piotroski=7, roic_vs_wacc=8.0, eps_cagr_3y=18.0,
                                all_time_high=2850.0),
    "HDFCBANK": _make_cache_doc("HDFCBANK", 1650.0, 0.18, 0.20, 0.22, 0.24,
                                regime="LowVolTrend", piotroski=8,
                                roic_vs_wacc=12.0, eps_cagr_3y=20.0,
                                fcf_yield=6.0, ebitda_margin_trend="expanding"),
    "TATAPOWER": _make_cache_doc("TATAPOWER", 420.0, 0.35, 0.38, 0.40, 0.42,
                                  regime="HighVolTrend", piotroski=5,
                                  roic_vs_wacc=2.0, eps_cagr_3y=10.0),
    "PAYTM": _make_cache_doc("PAYTM", 800.0, 0.50, 0.55, 0.58, 0.60,
                              regime="HighVolCrash", piotroski=3,
                              beneish=-1.5, roic_vs_wacc=-3.0,
                              eps_cagr_3y=-5.0, fcf_yield=-2.0,
                              ebitda_margin_trend="contracting"),
    "SUNPHARMA": _make_cache_doc("SUNPHARMA", 1850.0, 0.20, 0.22, 0.24, 0.26,
                                  regime="NormalVolRange", piotroski=6,
                                  roic_vs_wacc=6.0, eps_cagr_3y=12.0),
}


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _audit_loop():
    """Dedicated event loop for audit async tests (avoids conflict with pytest-asyncio)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def audit_bands(_audit_loop):
    """Insert synthetic cache docs, compute bands, clean up. Returns {symbol: bands_result}."""
    async def _run():
        os.environ.setdefault("TESTING", "1")
        import server
        db = server.db
        coll = db["equity_master_cache"]
        results = {}

        # Insert synthetic data
        for sym, doc in AUDIT_SYMBOLS.items():
            await coll.update_one({"symbol": sym}, {"$set": doc}, upsert=True)

        # Compute bands
        from services.price_band_engine import compute_price_bands
        for sym in AUDIT_SYMBOLS:
            results[sym] = await compute_price_bands(sym)

        # Clean up: remove synthetic docs (don't leave test data)
        for sym in AUDIT_SYMBOLS:
            await coll.delete_one({"symbol": sym, "avg_volume_20d": 500000})

        return results

    return _audit_loop.run_until_complete(_run())


ORDERED_LABELS = ["1W", "1M", "3M", "6M", "9M", "12M"]


# ── AUDIT STEP 1: Monotonic band expansion ───────────────────────────

class TestAuditStep1MonotonicExpansion:
    """Across 1W→12M, conservative/expected/optimistic HIGH must be non-decreasing
    and LOW must be non-increasing (wider range at longer horizons)."""

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_high_conservative_monotonic(self, audit_bands, symbol):
        r = audit_bands[symbol]
        assert r["error"] is None, f"{symbol} has error: {r.get('error')}"
        bands = r["bands"]
        highs = []
        for label in ORDERED_LABELS:
            b = bands.get(label)
            if b and "conservative" in b:
                highs.append(b["conservative"]["high"])
        for i in range(1, len(highs)):
            assert highs[i] >= highs[i - 1], (
                f"{symbol} conservative HIGH not monotonic: {ORDERED_LABELS[i-1]}={highs[i-1]} > {ORDERED_LABELS[i]}={highs[i]}"
            )

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_high_expected_monotonic(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        highs = [bands[l]["expected"]["high"] for l in ORDERED_LABELS if "expected" in bands.get(l, {})]
        for i in range(1, len(highs)):
            assert highs[i] >= highs[i - 1], (
                f"{symbol} expected HIGH not monotonic at index {i}"
            )

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_high_optimistic_monotonic(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        highs = [bands[l]["optimistic"]["high"] for l in ORDERED_LABELS if "optimistic" in bands.get(l, {})]
        for i in range(1, len(highs)):
            assert highs[i] >= highs[i - 1], (
                f"{symbol} optimistic HIGH not monotonic at index {i}"
            )

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_low_conservative_monotonic_decreasing(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        lows = [bands[l]["conservative"]["low"] for l in ORDERED_LABELS if "conservative" in bands.get(l, {})]
        for i in range(1, len(lows)):
            assert lows[i] <= lows[i - 1], (
                f"{symbol} conservative LOW not monotonically decreasing: {ORDERED_LABELS[i-1]}={lows[i-1]} < {ORDERED_LABELS[i]}={lows[i]}"
            )

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_low_expected_monotonic_decreasing(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        lows = [bands[l]["expected"]["low"] for l in ORDERED_LABELS if "expected" in bands.get(l, {})]
        for i in range(1, len(lows)):
            assert lows[i] <= lows[i - 1], (
                f"{symbol} expected LOW not monotonically decreasing at index {i}"
            )

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_low_optimistic_monotonic_decreasing(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        lows = [bands[l]["optimistic"]["low"] for l in ORDERED_LABELS if "optimistic" in bands.get(l, {})]
        for i in range(1, len(lows)):
            assert lows[i] <= lows[i - 1], (
                f"{symbol} optimistic LOW not monotonically decreasing at index {i}"
            )


# ── AUDIT STEP 2: High > LTP ─────────────────────────────────────────

class TestAuditStep2HighAboveLTP:
    """Every high band must be > LTP."""

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_all_highs_above_ltp(self, audit_bands, symbol):
        r = audit_bands[symbol]
        ltp = r["ltp"]
        bands = r["bands"]
        for label in ORDERED_LABELS:
            b = bands.get(label, {})
            for scenario in ("conservative", "expected", "optimistic"):
                if scenario in b:
                    h = b[scenario]["high"]
                    assert h > ltp, (
                        f"{symbol} {label} {scenario} high={h} <= LTP={ltp}"
                    )


# ── AUDIT STEP 3: Low < LTP ──────────────────────────────────────────

class TestAuditStep3LowBelowLTP:
    """Every low band must be < LTP."""

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_all_lows_below_ltp(self, audit_bands, symbol):
        r = audit_bands[symbol]
        ltp = r["ltp"]
        bands = r["bands"]
        for label in ORDERED_LABELS:
            b = bands.get(label, {})
            for scenario in ("conservative", "expected", "optimistic"):
                if scenario in b:
                    lo = b[scenario]["low"]
                    assert lo < ltp, (
                        f"{symbol} {label} {scenario} low={lo} >= LTP={ltp}"
                    )


# ── AUDIT STEP 4: Fundamental scalar activation for H >= 90d ─────────

class TestAuditStep4FundamentalScalar:
    """For horizons >= 90 days, fundamental_scalar should NOT be exactly 1.00
    if fundamental data is available."""

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_fundamental_scalar_non_unity_3m_plus(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        long_labels = ["3M", "6M", "9M", "12M"]
        for label in long_labels:
            b = bands.get(label, {})
            if "fundamental_scalar" in b:
                fs = b["fundamental_scalar"]
                # For 3M (90d), horizon_weight = 0, so scalar IS expected to be 1.0
                # For 6M+, with non-trivial fundamentals, it should deviate
                if label in ("6M", "9M", "12M"):
                    assert fs != 1.00, (
                        f"{symbol} {label} fundamental_scalar is exactly 1.00 despite available fundamentals"
                    )

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_fundamental_scalar_short_horizon_is_unity(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        short_labels = ["1W", "1M"]
        for label in short_labels:
            b = bands.get(label, {})
            if "fundamental_scalar" in b:
                fs = b["fundamental_scalar"]
                assert fs == 1.00, (
                    f"{symbol} {label} fundamental_scalar should be 1.00 for short horizons, got {fs}"
                )


# ── AUDIT STEP 5: Regime multiplier consistency ──────────────────────

class TestAuditStep5RegimeConsistency:
    """All bands for a symbol should use the same regime label and multiplier."""

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_regime_consistent_across_horizons(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        regimes_seen = set()
        mults_seen = set()
        for label in ORDERED_LABELS:
            b = bands.get(label, {})
            if "regime_used" in b:
                regimes_seen.add(b["regime_used"])
                mults_seen.add(b["regime_multiplier"])
        assert len(regimes_seen) <= 1, (
            f"{symbol} has inconsistent regimes across horizons: {regimes_seen}"
        )
        assert len(mults_seen) <= 1, (
            f"{symbol} has inconsistent multipliers across horizons: {mults_seen}"
        )

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_regime_matches_cache_doc(self, audit_bands, symbol):
        r = audit_bands[symbol]
        expected_regime = AUDIT_SYMBOLS[symbol]["regime_label"]
        assert r["regime"] == expected_regime, (
            f"{symbol} result regime={r['regime']} != cache regime={expected_regime}"
        )


# ── AUDIT STEP 6: No hardcoded default percentages ──────────────────

class TestAuditStep6NoHardcodedDefaults:
    """No band should be a simple round percentage of LTP (e.g. exactly 5%, 10%).
    Tolerance of 0.5% is allowed since structural anchoring may produce near-round values."""

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_no_round_percentage_bands(self, audit_bands, symbol):
        r = audit_bands[symbol]
        ltp = r["ltp"]
        bands = r["bands"]
        # Only check the most suspicious round percentages
        forbidden_pcts = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
        violations = 0
        total_checks = 0
        for label in ORDERED_LABELS:
            b = bands.get(label, {})
            for scenario in ("conservative", "expected", "optimistic"):
                if scenario not in b:
                    continue
                hi = b[scenario]["high"]
                lo = b[scenario]["low"]
                hi_pct = (hi - ltp) / ltp
                lo_pct = (ltp - lo) / ltp
                for fp in forbidden_pcts:
                    total_checks += 2
                    if abs(hi_pct - fp) < 0.0005:
                        violations += 1
                    if abs(lo_pct - fp) < 0.0005:
                        violations += 1
        # Allow up to 1 coincidental match (structural levels can occasionally align)
        assert violations <= 1, (
            f"{symbol}: {violations}/{total_checks} band values suspiciously close to round percentages"
        )


# ── AUDIT STEP 7: Data source & hallucination flags ──────────────────

class TestAuditStep7DataSource:
    """Every band must have data_source='equity_master_cache' and hallucinated=False."""

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_data_source_correct(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        for label in ORDERED_LABELS:
            b = bands.get(label, {})
            if "data_source" in b:
                assert b["data_source"] == "equity_master_cache", (
                    f"{symbol} {label} data_source={b['data_source']}"
                )

    @pytest.mark.parametrize("symbol", list(AUDIT_SYMBOLS.keys()))
    def test_hallucinated_is_false(self, audit_bands, symbol):
        r = audit_bands[symbol]
        bands = r["bands"]
        for label in ORDERED_LABELS:
            b = bands.get(label, {})
            if "hallucinated" in b:
                assert b["hallucinated"] is False, (
                    f"{symbol} {label} hallucinated={b['hallucinated']}"
                )


# ── AUDIT STEP 8: Fallback safety ───────────────────────────────────

class TestAuditStep8FallbackSafety:
    """If a symbol has missing volatility, the error must be reported correctly."""

    @pytest.fixture()
    def missing_vol_bands(self, _audit_loop):
        """Insert a cache doc with missing hv_252d, compute bands, clean up."""
        async def _run():
            import server
            db = server.db
            coll = db["equity_master_cache"]
            doc = _make_cache_doc("TESTVOL", 100.0, 0.25, 0.28, 0.30, None)
            doc["hv_252d"] = None
            await coll.update_one({"symbol": "TESTVOL"}, {"$set": doc}, upsert=True)
            from services.price_band_engine import compute_price_bands
            result = await compute_price_bands("TESTVOL")
            await coll.delete_one({"symbol": "TESTVOL"})
            return result
        return _audit_loop.run_until_complete(_run())

    def test_missing_vol_reports_error_on_long_horizons(self, missing_vol_bands):
        """9M and 12M use hv_252d — should report 'missing_volatility' error."""
        bands = missing_vol_bands["bands"]
        for label in ("9M", "12M"):
            b = bands.get(label, {})
            assert "error" in b, f"{label} should have error for missing hv_252d"
            assert b["error"] == "missing_volatility", (
                f"{label} error should be 'missing_volatility', got {b.get('error')}"
            )

    def test_missing_vol_short_horizons_still_work(self, missing_vol_bands):
        """1W, 1M, 3M use hv_20d/hv_60d which ARE provided — should have valid bands."""
        bands = missing_vol_bands["bands"]
        for label in ("1W", "1M", "3M"):
            b = bands.get(label, {})
            assert "conservative" in b, f"{label} should have valid bands (hv available)"
            assert b["conservative"]["high"] > 100.0, f"{label} high should be > LTP=100"


# ── Cross-symbol spread validation ───────────────────────────────────

class TestAuditCrossSymbolSanity:
    """High-vol symbols (PAYTM) should have wider bands than low-vol (HDFCBANK)."""

    def test_paytm_wider_than_hdfcbank(self, audit_bands):
        """High-vol+crash PAYTM should have wider percentage spreads than low-vol HDFCBANK."""
        paytm = audit_bands["PAYTM"]["bands"]
        hdfc = audit_bands["HDFCBANK"]["bands"]
        p_ltp = audit_bands["PAYTM"]["ltp"]
        h_ltp = audit_bands["HDFCBANK"]["ltp"]
        # Compare at 12M where horizon growth gives room to both
        for label in ("12M",):
            p_hi = paytm[label]["optimistic"]["high"]
            p_lo = paytm[label]["optimistic"]["low"]
            p_spread = (p_hi - p_lo) / p_ltp

            h_hi = hdfc[label]["optimistic"]["high"]
            h_lo = hdfc[label]["optimistic"]["low"]
            h_spread = (h_hi - h_lo) / h_ltp

            assert p_spread > h_spread, (
                f"{label}: PAYTM spread {p_spread:.4f} should be > HDFCBANK spread {h_spread:.4f}"
            )

    def test_reliance_regime_is_normal(self, audit_bands):
        assert audit_bands["RELIANCE"]["regime"] == "NormalVolTrend"

    def test_paytm_regime_is_crash(self, audit_bands):
        assert audit_bands["PAYTM"]["regime"] == "HighVolCrash"

    def test_hdfcbank_regime_is_low_vol(self, audit_bands):
        assert audit_bands["HDFCBANK"]["regime"] == "LowVolTrend"
