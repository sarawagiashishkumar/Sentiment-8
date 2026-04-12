import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function AdminApiTab({ kiteStatus, checkKiteStatus, token }) {
  return (
    <Card className="result-card border-slate-800 bg-slate-950/70">
      <CardHeader><CardTitle className="text-white">Market Data API Integration</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-slate-200">Connection Status</p>
            <div className="flex items-center gap-2">
              {kiteStatus?.connected ? (
                <><span className="inline-block h-3 w-3 rounded-full bg-green-500"></span><span className="text-sm text-green-400">{"\u2705"} Connected</span><span className="text-xs text-slate-400">| User: {kiteStatus.user_id}</span></>
              ) : (
                <><span className="inline-block h-3 w-3 rounded-full bg-red-500"></span><span className="text-sm text-red-400">{"\u274c"} Disconnected</span></>
              )}
            </div>
            {kiteStatus?.date && <p className="text-xs text-slate-500">Last authenticated: {kiteStatus.date}</p>}
          </div>
          <Button type="button" onClick={async () => {
            try { const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/kite/auth-url`, { headers: { Authorization: `Bearer ${token}` } }); const data = await res.json(); if (data.auth_url) { window.open(data.auth_url, '_blank'); setTimeout(() => checkKiteStatus(), 3000); } } catch (err) { console.error('Market Data API auth error:', err); }
          }} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="admin-connect-api-btn">Connect Market Data API</Button>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <p className="text-xs font-semibold text-slate-300 mb-2">OAuth URL:</p>
          <p className="text-xs text-cyan-400 break-all font-mono">https://kite.zerodha.com/connect/login?v=3&api_key=wgbgees3zbjpn254</p>
          <p className="text-xs text-slate-500 mt-2">Note: Market Data API authentication expires daily. Re-authenticate each trading day for live data.</p>
        </div>
        <Button type="button" onClick={checkKiteStatus} className="bg-slate-800 text-slate-100 hover:bg-slate-700" data-testid="admin-refresh-api-status">Refresh Status</Button>
      </CardContent>
    </Card>
  );
}
