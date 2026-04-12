import { useState } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function AdminControlsTab({ authHeaders, adminConfig, loadAdminConfig, adminError, setAdminError }) {
  const [apiControlsEdit, setApiControlsEdit] = useState(adminConfig?.api_controls || { kite_data_enabled: true, moneycontrol_data_enabled: true, strict_live_only: true });
  const [domainForm, setDomainForm] = useState({ domain: "", target_record: "" });
  const [domainDeleteConfirm, setDomainDeleteConfirm] = useState(null);
  const [domainMapStatus, setDomainMapStatus] = useState({});
  const [expandedDns, setExpandedDns] = useState({});

  const saveApiControls = async () => {
    try { await axios.patch(`${API}/admin/api-controls`, apiControlsEdit, { headers: authHeaders }); await loadAdminConfig(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to update API controls"); }
  };

  const addDomainMapping = async (event) => {
    event.preventDefault();
    try { await axios.post(`${API}/admin/domain-mappings`, domainForm, { headers: authHeaders }); setDomainForm({ domain: "", target_record: "" }); await loadAdminConfig(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to save domain mapping"); }
  };

  const updateDomainStatus = async (domain, status) => {
    try { await axios.patch(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}`, { status }, { headers: authHeaders }); await loadAdminConfig(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to update domain status"); }
  };

  const deleteDomainMapping = async (domain) => {
    try { await axios.delete(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}`, { headers: authHeaders }); setDomainDeleteConfirm(null); await loadAdminConfig(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to delete domain mapping"); }
  };

  const mapDomain = async (domain) => {
    setDomainMapStatus(p => ({ ...p, [domain]: { loading: true, result: null } }));
    try { const resp = await axios.post(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}/map`, {}, { headers: authHeaders }); setDomainMapStatus(p => ({ ...p, [domain]: { loading: false, result: resp.data } })); await loadAdminConfig(); }
    catch (e) { setDomainMapStatus(p => ({ ...p, [domain]: { loading: false, result: { error: e?.response?.data?.detail || "Map failed" } } })); }
  };

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="admin-advanced-controls-card">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white">Advanced Controls</CardTitle>
        <Button type="button" onClick={loadAdminConfig} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="admin-refresh-config-button">Refresh Controls</Button>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-kite-enabled">
            <input type="checkbox" checked={Boolean(apiControlsEdit.kite_data_enabled)} onChange={(e) => setApiControlsEdit(p => ({ ...p, kite_data_enabled: e.target.checked }))} /> Market Data API enabled
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-moneycontrol-enabled">
            <input type="checkbox" checked={Boolean(apiControlsEdit.moneycontrol_data_enabled)} onChange={(e) => setApiControlsEdit(p => ({ ...p, moneycontrol_data_enabled: e.target.checked }))} /> Secondary API enabled
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-strict-live-only">
            <input type="checkbox" checked={Boolean(apiControlsEdit.strict_live_only)} onChange={(e) => setApiControlsEdit(p => ({ ...p, strict_live_only: e.target.checked }))} /> Strict live-only mode
          </label>
        </div>
        <Button type="button" onClick={saveApiControls} className="bg-slate-800 text-slate-100 hover:bg-slate-700" data-testid="admin-save-api-controls">Save API Controls</Button>

        <form onSubmit={addDomainMapping} className="grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="admin-domain-form">
          <Input value={domainForm.domain} onChange={(e) => setDomainForm(p => ({ ...p, domain: e.target.value }))} placeholder="Domain or Subdomain" className="border-slate-700 bg-slate-900 text-slate-100" data-testid="admin-domain-input" />
          <Input value={domainForm.target_record} onChange={(e) => setDomainForm(p => ({ ...p, target_record: e.target.value }))} placeholder="A-Record target (IP/host)" className="border-slate-700 bg-slate-900 text-slate-100" data-testid="admin-domain-target-input" />
          <Button type="submit" className="bg-slate-800 text-slate-100 hover:bg-slate-700" data-testid="admin-domain-submit">Save Domain Mapping</Button>
        </form>

        {adminConfig?.hosting_dns_reference && (
          <div className="rounded-md border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-300" data-testid="admin-hosting-dns-reference">
            <p>Hosting Domain: <span className="font-mono text-cyan-300">{adminConfig.hosting_dns_reference.hosting_domain || "-"}</span></p>
            <p>Resolved IPv4: <span className="font-mono text-cyan-300">{adminConfig.hosting_dns_reference.resolved_ipv4 || "Unavailable"}</span></p>
          </div>
        )}

        <DomainList
          mappings={adminConfig?.domain_mappings || []}
          mapDomain={mapDomain} updateDomainStatus={updateDomainStatus}
          deleteDomainMapping={deleteDomainMapping}
          domainMapStatus={domainMapStatus} domainDeleteConfirm={domainDeleteConfirm}
          setDomainDeleteConfirm={setDomainDeleteConfirm}
          expandedDns={expandedDns} setExpandedDns={setExpandedDns}
        />
      </CardContent>
    </Card>
  );
}

function DomainList({ mappings, mapDomain, updateDomainStatus, deleteDomainMapping, domainMapStatus, domainDeleteConfirm, setDomainDeleteConfirm, expandedDns, setExpandedDns }) {
  if (mappings.length === 0) return <p className="text-xs text-slate-500">No domain mappings yet.</p>;
  return (
    <div className="space-y-3" data-testid="admin-domain-list">
      {mappings.map((row) => {
        const mapInfo = domainMapStatus[row.domain];
        const statusColor = row.status === "ACTIVE" ? "bg-emerald-600" : row.status === "PENDING_DNS" || row.status === "NGINX_CONFIG_GENERATED" ? "bg-yellow-600" : row.status === "FAILED" ? "bg-rose-600" : "bg-slate-600";
        return (
          <div key={row.domain} className="rounded-lg border border-slate-700 bg-slate-900/80 p-3 space-y-2" data-testid={`admin-domain-card-${row.domain}`}>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="space-y-0.5 text-xs"><p className="font-mono font-semibold text-cyan-300">{row.domain}</p><p className="text-slate-400">A Record: {row.resolved_target_ip || row.target_record || "\u2014"}</p></div>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold text-white ${statusColor}`}>{row.status}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" onClick={() => mapDomain(row.domain)} disabled={mapInfo?.loading} className="h-7 bg-cyan-700 px-3 text-xs text-white hover:bg-cyan-600" data-testid={`admin-domain-map-${row.domain}`}>{mapInfo?.loading ? "Mapping\u2026" : "MAP"}</Button>
              <Button type="button" size="sm" onClick={() => updateDomainStatus(row.domain, "ACTIVE")} className="h-7 bg-emerald-700 px-3 text-xs text-white hover:bg-emerald-600" data-testid={`admin-domain-active-${row.domain}`}>Mark Active</Button>
              <Button type="button" size="sm" onClick={() => setExpandedDns(p => ({ ...p, [row.domain]: !p[row.domain] }))} className="h-7 bg-slate-700 px-3 text-xs text-white hover:bg-slate-600" data-testid={`admin-domain-dns-toggle-${row.domain}`}>{expandedDns[row.domain] ? "Hide DNS" : "DNS Instructions"}</Button>
              <Button type="button" size="sm" onClick={() => setDomainDeleteConfirm(row.domain)} className="h-7 bg-rose-700 px-3 text-xs text-white hover:bg-rose-600" data-testid={`admin-domain-delete-${row.domain}`}>Delete</Button>
            </div>
            {expandedDns[row.domain] && (
              <div className="rounded-md border border-slate-700 bg-slate-950 p-3 text-xs text-slate-300 space-y-1" data-testid={`admin-domain-dns-${row.domain}`}>
                <p className="font-semibold text-cyan-300 mb-1">DNS Setup Instructions</p>
                <p>1. Open your domain registrar / DNS provider</p>
                <p>2. Add an <strong>A Record</strong>: Host = <code className="text-yellow-300">{row.host_label || "@"}</code>, Value = <code className="text-yellow-300">{row.resolved_target_ip || row.target_record || "[server IP]"}</code>, TTL = 300</p>
                <p>3. Wait 5-30 minutes for propagation, then click <strong>MAP</strong></p>
              </div>
            )}
            {mapInfo?.result && <div className={`rounded-md p-2 text-xs ${mapInfo.result.error ? "bg-rose-900/40 text-rose-300" : "bg-emerald-900/40 text-emerald-300"}`}>{mapInfo.result.error ? `Error: ${mapInfo.result.error}` : `Mapped (${mapInfo.result.nginx_status})`}</div>}
            {domainDeleteConfirm === row.domain && (
              <div className="rounded-md border border-rose-700 bg-rose-950/60 p-3 text-xs space-y-2">
                <p className="text-rose-300 font-semibold">Confirm delete: <span className="font-mono">{row.domain}</span>?</p>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => deleteDomainMapping(row.domain)} className="h-7 bg-rose-600 px-3 text-xs text-white hover:bg-rose-500">Yes, Delete</Button>
                  <Button size="sm" onClick={() => setDomainDeleteConfirm(null)} className="h-7 bg-slate-700 px-3 text-xs text-white hover:bg-slate-600">Cancel</Button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
