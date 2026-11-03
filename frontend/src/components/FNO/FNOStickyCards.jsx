import { useState } from "react";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { Badge } from "components/ui/badge";
import { Button } from "components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";
import { Input } from "components/ui/input";
import { formatNumber, formatSignedInr } from "utils/formatters";

export function FNOStickyCards({
  customPositions,
  loadCustomPositions,
  authHeaders,
  syncCredits,
  alertSoundEnabled,
  enableAlertSound,
  playAlertSound,
}) {
  const API = "/api";
  const [showSoundPrompt, setShowSoundPrompt] = useState(false);
  const [customScript, setCustomScript] = useState("");
  const [customBuyPrice, setCustomBuyPrice] = useState("");
  const [customLots, setCustomLots] = useState("1");
  const [customPositionLoading, setCustomPositionLoading] = useState(false);
  const [customPositionError, setCustomPositionError] = useState("");
  const [sellDialogOpen, setSellDialogOpen] = useState(false);
  const [sellDialogPosition, setSellDialogPosition] = useState(null);
  const [sellPriceInput, setSellPriceInput] = useState("");
  const [sellConfirmChecked, setSellConfirmChecked] = useState(false);
  const [sellLoading, setSellLoading] = useState(false);

  const createCustomProjection = async (event) => {
    event.preventDefault();
    setCustomPositionError("");
    if (!alertSoundEnabled) {
      setShowSoundPrompt(true);
      return;
    }
    if (!customScript.trim()) {
      setCustomPositionError("Please enter a script or symbol.");
      return;
    }
    const buyPriceNum = Number(customBuyPrice);
    const lotsNum = Number(customLots);
    if (!buyPriceNum || buyPriceNum <= 0) {
      setCustomPositionError("Enter a valid buy price.");
      return;
    }
    if (!lotsNum || lotsNum <= 0) {
      setCustomPositionError("Enter valid no. of lots (minimum 1).");
      return;
    }
    setCustomPositionLoading(true);
    try {
      const axios = (await import("axios")).default;
      const response = await axios.post(
        `${API}/fno/custom-position`,
        { script: customScript.trim().toUpperCase(), buy_price: buyPriceNum, quantity_lots: Math.floor(lotsNum) },
        { headers: authHeaders },
      );
      syncCredits(response.data.credits_remaining);
      setCustomBuyPrice("");
      setCustomLots("1");
      await loadCustomPositions();
    } catch (error) {
      setCustomPositionError(error?.response?.data?.detail || "Unable to create custom projection.");
    } finally {
      setCustomPositionLoading(false);
    }
  };

  const removeCustomProjection = async (positionId) => {
    try {
      const axios = (await import("axios")).default;
      await axios.delete(`${API}/fno/custom-position/${positionId}`, { headers: authHeaders });
      await loadCustomPositions();
    } catch (error) {
      await loadCustomPositions();
      setCustomPositionError(error?.response?.data?.detail || "Unable to remove custom projection.");
    }
  };

  const openSellDialog = (position) => {
    setSellDialogPosition(position);
    setSellPriceInput("");
    setSellConfirmChecked(false);
    setSellDialogOpen(true);
  };

  const submitSoldPosition = async (event) => {
    event.preventDefault();
    if (!sellDialogPosition) return;
    const soldPrice = Number(sellPriceInput);
    if (!soldPrice || soldPrice <= 0) {
      setCustomPositionError("Please enter a valid sold price.");
      return;
    }
    if (!sellConfirmChecked) {
      setCustomPositionError("Please confirm before submitting sold price.");
      return;
    }
    setSellLoading(true);
    setCustomPositionError("");
    try {
      const axios = (await import("axios")).default;
      await axios.post(
        `${API}/fno/custom-position/${sellDialogPosition.id}/sell`,
        { sold_price: soldPrice, confirm: true },
        { headers: authHeaders },
      );
      setSellDialogOpen(false);
      setSellDialogPosition(null);
      setSellPriceInput("");
      setSellConfirmChecked(false);
      await loadCustomPositions();
    } catch (error) {
      setCustomPositionError(error?.response?.data?.detail || "Unable to mark position as sold.");
    } finally {
      setSellLoading(false);
    }
  };

  const handleEnableAlertSound = async () => {
    try {
      await enableAlertSound();
      setCustomPositionError("");
      setShowSoundPrompt(false);
      setTimeout(() => playAlertSound("target"), 50);
    } catch {
      setCustomPositionError("Unable to enable buzzer. Please check browser audio settings.");
    }
  };

  return (
    <>
      <form onSubmit={createCustomProjection} className="flex flex-col gap-3 lg:flex-row" data-testid="fno-custom-script-form">
        <Input
          value={customScript}
          onChange={(event) => setCustomScript(event.target.value.toUpperCase())}
          placeholder="Custom script/symbol (e.g. NIFTY10MAR26500PE / RELIANCE)"
          className="font-mono border-slate-700 bg-slate-900 text-slate-100"
          data-testid="fno-custom-script-input"
        />
        <Input
          value={customBuyPrice}
          onChange={(event) => setCustomBuyPrice(event.target.value)}
          type="number" min="0" step="0.01"
          placeholder="Buy Price"
          className="w-full border-slate-700 bg-slate-900 text-slate-100 lg:w-44"
          data-testid="fno-custom-buy-price-input"
        />
        <Input
          value={customLots}
          onChange={(event) => setCustomLots(event.target.value)}
          type="number" min="1" step="1"
          placeholder="No. of Lots"
          className="w-full border-slate-700 bg-slate-900 text-slate-100 lg:w-36"
          data-testid="fno-custom-lots-input"
        />
        <Button type="submit" className="border border-slate-700 bg-slate-900 text-yellow-200 hover:bg-yellow-200 hover:text-slate-900" data-testid="fno-custom-script-submit">
          {customPositionLoading ? "Saving..." : "RUN CUSTOM PROJECTION (-1)"}
        </Button>
      </form>

      <div className="flex items-center gap-2 text-xs text-slate-300" data-testid="fno-alert-sound-control">
        <Button type="button" onClick={handleEnableAlertSound} className="h-8 border border-cyan-500/60 bg-cyan-500/10 px-3 text-cyan-200 hover:bg-cyan-500/20" data-testid="enable-alert-buzzer-button">
          {alertSoundEnabled ? "Buzzer Enabled" : "Enable Alert Buzzer"}
        </Button>
        <span>Alerts on: Urgent exits, T1/T2 target hits, and warnings — loud multi-tone sound.</span>
      </div>

      {showSoundPrompt ? (
        <div className="rounded-md border border-cyan-500/40 bg-cyan-500/10 p-3 text-xs text-cyan-100" data-testid="sound-permission-note">
          <p className="mb-2 font-semibold">Enable alert sound before custom projection?</p>
          <p className="mb-2">Loud multi-tone alerts for: T1/T2 target hits, urgent exit conditions, SL warnings, and high-loss signals.</p>
          <div className="flex items-center gap-2">
            <Button type="button" onClick={handleEnableAlertSound} className="h-8 bg-cyan-500 px-3 text-slate-900 hover:bg-cyan-400" data-testid="sound-permission-enable">
              Allow Buzzer
            </Button>
            <Button type="button" onClick={() => { setShowSoundPrompt(false); }} className="h-8 border border-slate-600 bg-transparent px-3 text-slate-300 hover:bg-slate-800" data-testid="sound-permission-skip">
              Continue Without Sound
            </Button>
          </div>
        </div>
      ) : null}

      {customPositionError ? <p className="text-sm text-rose-400" data-testid="fno-custom-position-error">{customPositionError}</p> : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3" data-testid="custom-position-list">
        {customPositions.length ? (
          customPositions.map((position) => {
            const urgent = ["EXIT_URGENT_TIME", "EXIT_URGENT_LOSS", "RISKY_PREMIUM", "EXIT_NOW_HIGH_LOSS", "EXIT_URGENT_NO_RECOVERY"].includes(position.alert || "");
            const exitPrice = position.best_exit_price ?? position.projected_exit_price;
            const ltpDeltaClass = Number(position.buy_to_ltp_diff || 0) >= 0 ? "text-emerald-300" : "text-rose-300";
            return (
              <div key={position.id} className={`result-card result-hover custom-position-yellow-card rounded-lg border p-3 ${urgent ? "urgent-alert-card" : "border-amber-500"}`} data-testid={`custom-position-card-${position.id}`}>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="font-mono text-slate-900" data-testid={`custom-position-script-${position.id}`}>{position.script}</p>
                  <Badge className="border border-emerald-600 bg-emerald-500/20 text-emerald-200" data-testid={`custom-position-status-${position.id}`}>{position.status}</Badge>
                </div>
                <div className="grid grid-cols-1 gap-1 text-xs md:grid-cols-2">
                  <p>Buy Price: <span className="font-mono">₹{formatNumber(position.buy_price)}</span></p>
                  <p>Lots / Units: <span className="font-mono">{position.quantity_lots} / {position.units}</span></p>
                  <p>Live LTP: <span className="font-mono text-sm font-extrabold text-slate-900" data-testid={`custom-position-live-ltp-${position.id}`}>{position.latest_option_ltp == null ? "Unavailable" : `₹${formatNumber(position.latest_option_ltp)}`}</span></p>
                  <p>LTP vs Buy: <span className={`font-mono font-semibold ${ltpDeltaClass}`} data-testid={`custom-position-buy-diff-${position.id}`}>{formatSignedInr(position.buy_to_ltp_diff)}</span></p>
                  {position.latest_option_ltp == null ? <p className="md:col-span-2 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-200" role="status">Position saved. Waiting for a confirmed live option quote; P&amp;L alerts resume when pricing is available.</p> : null}
                  {position.sold_price !== null && position.sold_price !== undefined ? (
                    <p className="md:col-span-2 custom-position-pnl-box" data-testid={`custom-position-realized-pnl-${position.id}`}>
                      Sold @ <span className="font-mono">₹{formatNumber(position.sold_price)}</span> | Realized P&L: <span className={`ml-1 font-mono font-extrabold ${Number(position.realized_pnl || 0) >= 0 ? "text-emerald-100" : "text-rose-100"}`}>{formatSignedInr(position.realized_pnl)}</span>
                    </p>
                  ) : (
                    <p className="md:col-span-2 custom-position-pnl-box" data-testid={`custom-position-pnl-box-${position.id}`}>
                      P/L (Lot Size Based):
                      <span className={`ml-1 font-mono font-extrabold ${Number(position.floating_pnl_amount || 0) >= 0 ? "text-emerald-100" : "text-rose-100"}`}>
                        {formatSignedInr(position.floating_pnl_amount)} ({position.floating_pnl_pct !== null && position.floating_pnl_pct !== undefined ? `${position.floating_pnl_pct > 0 ? "+" : ""}${formatNumber(position.floating_pnl_pct)}%` : "-"})
                      </span>
                    </p>
                  )}
                  <p>Target1 / Target2: <span className="font-mono">₹{formatNumber(position.target1)} / ₹{formatNumber(position.target2)}</span></p>
                  <p>To T1 / T2: <span className="font-mono" data-testid={`custom-position-target-diff-${position.id}`}>₹{formatNumber(position.ltp_to_t1_diff)} / ₹{formatNumber(position.ltp_to_t2_diff)}</span></p>
                  <p>Expiry in: <span className="font-mono">{position.minutes_to_expiry} min</span></p>
                  <p>Recovery Potential: <span className="font-mono" data-testid={`custom-position-recovery-${position.id}`}>{position.recovery_potential !== null && position.recovery_potential !== undefined ? `${formatNumber(position.recovery_potential * 100)}%` : "-"}</span></p>
                  <p>T1 Status: <span className="inline-flex items-center gap-1 font-semibold" data-testid={`custom-position-t1-status-${position.id}`}>{position.target1_achieved ? <><CheckCircle2 size={14} className="text-blue-600" /> Achieved</> : "Pending"}</span></p>
                  <p>T2 Status: <span className="inline-flex items-center gap-1 font-semibold" data-testid={`custom-position-t2-status-${position.id}`}>{position.target2_achieved ? <><CheckCircle2 size={14} className="text-blue-600" /> Achieved</> : "Pending"}</span></p>
                  <p className="md:col-span-2">Exit Plan: <span className="font-mono">{position.revised_exit_plan}</span></p>
                </div>
                {exitPrice && position.status !== "SOLD" ? (
                  <div className="mt-2">
                    {position.best_exit_date_str?.includes("Today") || position.remaining_trading_days === 0 ? (
                      <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-red-600/30 text-red-300 border border-red-500/70 mb-1 animate-pulse" data-testid={`expiry-today-badge-${position.id}`}>
                        EXPIRY TODAY — Exit Before 3:30 PM
                      </span>
                    ) : position.remaining_trading_days <= 2 && position.remaining_trading_days > 0 ? (
                      <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 mb-1">
                        {"\u26a0"} Near Expiry ({position.remaining_trading_days} trading days left)
                      </span>
                    ) : null}
                    <p className="text-sm font-semibold text-green-400" data-testid={`custom-position-best-exit-${position.id}`}>
                      BEST EXIT: T+{position.best_exit_days ?? "?"} Trading Days{position.best_exit_date_str ? ` (${position.best_exit_date_str})` : ""} @ ₹{formatNumber(exitPrice)}
                    </p>
                  </div>
                ) : null}
                <div className="mt-3 flex items-center justify-end gap-2">
                  {position.can_sell ? (
                    <Button type="button" onClick={() => openSellDialog(position)} className="h-8 border border-emerald-500 bg-emerald-500/10 px-3 text-emerald-200 hover:bg-emerald-500/20" data-testid={`custom-position-sold-button-${position.id}`}>
                      Sold
                    </Button>
                  ) : null}
                  <Button type="button" onClick={() => removeCustomProjection(position.id)} className="h-8 border border-rose-600 bg-rose-500/10 px-3 text-rose-800 hover:bg-rose-500/20" data-testid={`custom-position-close-${position.id}`}>
                    <X size={14} />
                  </Button>
                </div>
                {urgent ? (
                  <div className="mt-2 flex items-center gap-2 rounded-md border border-red-500 bg-red-500/20 px-2 py-1 text-xs font-bold text-red-100" data-testid={`custom-position-alert-${position.id}`}>
                    <AlertTriangle size={14} />
                    URGENT EXIT ALERT — Review this position now
                  </div>
                ) : null}
                {(position.alert === "EXIT_NOW_HIGH_LOSS" || position.alert === "EXIT_URGENT_NO_RECOVERY") && exitPrice ? (
                  <p className="mt-2 text-sm font-extrabold text-red-200" data-testid={`custom-position-projected-exit-${position.id}`}>
                    EXIT AT PROJECTED PRICE: ₹{formatNumber(exitPrice)}
                  </p>
                ) : null}
              </div>
            );
          })
        ) : (
          <p className="text-xs text-slate-400" data-testid="custom-position-empty-note">
            No sticky custom projections yet. Create one using script + buy price.
          </p>
        )}
      </div>

      {sellDialogOpen && sellDialogPosition ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4" data-testid="custom-position-sell-modal">
          <Card className="w-full max-w-md border-slate-700 bg-slate-950">
            <CardHeader>
              <CardTitle className="text-white">Mark Position as Sold</CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-3" onSubmit={submitSoldPosition} data-testid="custom-position-sell-form">
                <p className="text-sm text-slate-300">{sellDialogPosition.script}</p>
                <Input type="number" min="0" step="0.01" value={sellPriceInput} onChange={(event) => setSellPriceInput(event.target.value)} placeholder="Enter Sold Price" data-testid="custom-position-sell-price-input" className="border-slate-700 bg-slate-900 text-slate-100" />
                <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="custom-position-sell-confirm">
                  <input type="checkbox" checked={sellConfirmChecked} onChange={(event) => setSellConfirmChecked(event.target.checked)} data-testid="custom-position-sell-confirm-checkbox" />
                  I confirm this sold price is correct.
                </label>
                <div className="flex items-center justify-end gap-2">
                  <Button type="button" className="border border-slate-600 bg-transparent text-slate-200 hover:bg-slate-800" onClick={() => { setSellDialogOpen(false); setSellDialogPosition(null); }} data-testid="custom-position-sell-cancel">Cancel</Button>
                  <Button type="submit" className="bg-emerald-500 text-slate-900 hover:bg-emerald-400" disabled={sellLoading} data-testid="custom-position-sell-submit">{sellLoading ? "Saving..." : "Confirm Sold"}</Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </>
  );
}
