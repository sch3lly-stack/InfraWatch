import { Link } from "react-router-dom";
import { api } from "../api";
import { ago, pct, useQuery } from "../hooks";
import { useFilters } from "../session";
import { ErrorNote, Meter, SeverityBadge, SimBadge, Stat, StatusBadge } from "../components/ui";
import FilterBar from "./Filters";

export default function Overview() {
  const { f } = useFilters();
  const qs = `include_simulated=${f.sim}${f.env ? `&environment=${encodeURIComponent(f.env)}` : ""}`;
  const ov = useQuery(() => api(`/overview?${qs}`), [qs]);
  const hosts = useQuery(() => api<any[]>(`/hosts?${qs}`), [qs]);
  const alerts = useQuery(() => api<any[]>(`/alerts?status=active&limit=8&include_simulated=${f.sim}`), [f.sim]);
  const o = ov.data;
  const attention = (hosts.data ?? []).filter((h) => h.status === "offline" || h.open_alerts > 0);
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><h1 className="text-xl font-semibold">Overview</h1><FilterBar environments={o?.environments ?? []} /></div>
      <ErrorNote error={ov.error || hosts.error} />
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Monitored systems" value={o?.total ?? "–"} sub={o?.pending ? `${o.pending} awaiting first report` : undefined} />
        <Stat label="Online" value={o?.online ?? "–"} />
        <Stat label="Offline" value={o?.offline ?? "–"} tone={o?.offline ? "crit" : undefined} />
        <Stat label="Needs attention" value={o?.needs_attention ?? "–"} tone={o?.needs_attention ? "warn" : undefined} />
        <Stat label="Services up" value={o ? `${o.services_up}/${o.services_total}` : "–"} />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Avg CPU" value={pct(o?.avg_cpu)} /><Stat label="Avg memory" value={pct(o?.avg_mem)} /><Stat label="Avg disk" value={pct(o?.avg_disk)} />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <section className="card" data-testid="attention">
          <h2 className="text-sm font-medium p-4 pb-2">Systems requiring attention</h2>
          {attention.length === 0 ? <p className="muted text-sm px-4 pb-4">Nothing needs attention.</p> : (
            <table className="w-full"><tbody>{attention.map((h) => (
              <tr key={h.id}><td><Link className="underline" to={`/hosts/${h.id}`}>{h.hostname}</Link>{h.is_simulated && <SimBadge />}</td>
                <td><StatusBadge status={h.status} /></td><td className="ink2">{h.open_alerts} alert{h.open_alerts === 1 ? "" : "s"}</td></tr>))}</tbody></table>)}
        </section>
        <section className="card" data-testid="recent-alerts">
          <div className="flex justify-between p-4 pb-2"><h2 className="text-sm font-medium">Recent alerts</h2><Link to="/alerts" className="text-xs underline ink2">All alerts</Link></div>
          {(alerts.data ?? []).length === 0 ? <p className="muted text-sm px-4 pb-4">No active alerts.</p> : (
            <table className="w-full"><tbody>{alerts.data!.map((a) => (
              <tr key={a.id}><td><SeverityBadge severity={a.severity} /></td><td>{a.title}</td><td className="muted">{ago(a.opened_at)}</td></tr>))}</tbody></table>)}
        </section>
      </div>
      <section className="card">
        <h2 className="text-sm font-medium p-4 pb-2">Systems</h2>
        <table className="w-full"><thead><tr><th>Host</th><th>Status</th><th>CPU</th><th>Memory</th><th>Disk</th><th>Last seen</th></tr></thead>
          <tbody>{(hosts.data ?? []).map((h) => (
            <tr key={h.id}><td><Link className="underline" to={`/hosts/${h.id}`}>{h.hostname}</Link>{h.is_simulated && <SimBadge />}<div className="text-xs muted">{h.environment}</div></td>
              <td><StatusBadge status={h.status} /></td><td><Meter value={h.latest?.cpu_percent} label="CPU" /></td>
              <td><Meter value={h.latest?.mem_percent} label="Memory" /></td><td><Meter value={h.latest?.disk_percent} label="Disk" /></td>
              <td className="ink2">{ago(h.last_seen)}</td></tr>))}
            {hosts.data?.length === 0 && <tr><td colSpan={6} className="muted text-center py-8">No systems yet. Register an agent (Settings → Enrollment) or enable simulated data.</td></tr>}</tbody></table>
      </section>
    </div>
  );
}
