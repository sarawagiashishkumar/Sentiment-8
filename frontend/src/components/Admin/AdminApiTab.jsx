import useSWR from "swr";
import { Button } from "components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";

const fetchKiteAuthUrl = async ([url, token]) => {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.auth_url) {
    throw new Error(data.detail || "Unable to load the Kite OAuth URL.");
  }
  return data;
};

export function AdminApiTab({ kiteStatus, kiteConfig, checkKiteStatus, token }) {
  const {
    data: kiteAuth,
    error: kiteAuthError,
    isLoading: isAuthUrlLoading,
  } = useSWR(token ? ["/api/kite/auth-url", token] : null, fetchKiteAuthUrl, {
    shouldRetryOnError: false,
  });
  const authUrl = kiteAuth?.auth_url;

  const connectToKite = () => {
    if (!authUrl) return;

    const authWindow = window.open(authUrl, "_blank");
    if (authWindow) {
      authWindow.opener = null;
    } else {
      window.location.assign(authUrl);
    }
  };

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70">
      <CardHeader><CardTitle className="text-white">Market Data API Integration</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4 rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <div className="flex flex-col gap-2">
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
          <Button
            type="button"
            onClick={connectToKite}
            disabled={!authUrl || isAuthUrlLoading}
            aria-busy={isAuthUrlLoading}
            className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
            data-testid="admin-connect-api-btn"
          >
            {isAuthUrlLoading ? "Loading OAuth URL..." : "Connect Market Data API"}
          </Button>
        </div>
        {kiteAuthError && <p role="alert" className="text-sm text-red-400">{kiteAuthError.message}</p>}
        <div className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <div>
            <p className="text-xs font-semibold text-slate-300">OAuth URL</p>
            {authUrl ? (
              <a
                href={authUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="break-all font-mono text-xs text-cyan-400 underline underline-offset-4"
                data-testid="admin-kite-oauth-url"
              >
                {authUrl}
              </a>
            ) : (
              <p className="text-xs text-slate-500">{isAuthUrlLoading ? "Loading OAuth URL..." : "Not available"}</p>
            )}
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-300">Redirect URL</p>
            <p className="break-all font-mono text-xs text-cyan-400">{kiteConfig?.redirect_url || "Not configured"}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-300">Postback URL</p>
            <p className="break-all font-mono text-xs text-cyan-400">{kiteConfig?.postback_url || "Not configured"}</p>
          </div>
          <p className="text-xs text-slate-500">
            Register the redirect URL exactly in the Kite Developer Console. Postbacks are for order updates, not login, and apply only to orders placed with this API key. The API secret is used only for the server-side token checksum and is never included in the OAuth URL.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button type="button" onClick={checkKiteStatus} className="bg-slate-800 text-slate-100 hover:bg-slate-700" data-testid="admin-refresh-api-status">Refresh Status</Button>
          <p className="text-xs text-slate-500">After approving Kite login, return here and refresh the connection status.</p>
        </div>
      </CardContent>
    </Card>
  );
}
