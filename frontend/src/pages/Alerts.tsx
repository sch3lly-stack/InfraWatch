import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ago, useQuery } from "../hooks";
import { canAtLeast, useFilters, useMe } from "../session";
import { ErrorNote, SeverityBadge, SimBadge } from "../components/ui";
import FilterBar from "./Filters";

export default function Alerts() {
  const { f } = useFilters();
  const me = useMe();
  const [status, setStatus] = useState("active"); const [sev, setSev] = useState("");
  const qs = `status=${status}&include_simulated=${f.sim}${sev ? `&severity=${sev}` : ""}`;
  const { data, error, reload } = useQuery(() => api<any[]>(`/alerts?${qs}`), [qs]);
  const act = async (id: number, what: string) => { try { await api(`/alerts/${id}/${what}`, { method: "POST" }); } finally { reload(); } };
  const op = canAtLeast(me, "operator");
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-semibold">Alerts</h1>
        <div className="flex gap-2 items-center"><FilterBar environments={[]} />
          <select className="input" aria-label="Alert status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="active">Active</option><option value="open">Open</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved (history)</option></select>
          <select className="input" aria-label="Severity" value={sev} onChange={(e) => setSev(e.target.value)}><option value="">Any severity</option><option>critical</option><option>warning</option><option>info</option></select>
        </div></div>
      <ErrorNote error={error} />
      <div className="card"><table className="w-full"><thead><tr><th>Severity</th><th>Alert</th><th>Host</th><th>Status</th><th>Opened</th><th>Seen</th><th></th></tr></thead>
        <tbody>{(data ?? []).map((a) => (
          <tr key={a.id} data-testid="alert-row"><td><SeverityBadge severity={a.severity} /></td><td>{a.title}<div className="text-xs muted">{a.message}</div></td>
            <td><Link className="underline" to={`/hosts/${a.host_id}`}>{a.hostname}</Link>{a.is_simulated && <SimBadge />}</td>
            <td>{a.status}{a.acknowledged_by && <div className="text-xs muted">by {a.acknowledged_by}</div>}{a.resolved_by && <div className="text-xs muted">by {a.resolved_by}</div>}</td>
            <td className="ink2">{ago(a.opened_at)}</td><td className="muted">×{a.occurrences}</td>
            <td className="whitespace-nowrap">{op && a.status === "open" && <button className="btn mr-1" onClick={() => act(a.id, "acknowledge")}>Acknowledge</button>}
              {op && a.status !== "resolved" && <button className="btn" onClick={() => act(a.id, "resolve")}>Resolve</button>}</td></tr>))}
          {data?.length === 0 && <tr><td colSpan={7} className="muted text-center py-8">No alerts.</td></tr>}</tbody></table></div>
    </div>
  );
}
