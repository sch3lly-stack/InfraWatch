import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, download } from "../api";
import { ago, bytes, dur, pct, useQuery } from "../hooks";
import { canAtLeast, useMe } from "../session";
import LineChart from "../components/LineChart";
import { ErrorNote, Meter, SeverityBadge, SimBadge, Stat, StatusBadge } from "../components/ui";

const RANGES = ["15m", "1h", "6h", "24h", "7d", "30d"];
const S1 = "var(--s1)", S2 = "var(--s2)";

export default function HostDetail() {
  const { id } = useParams();
  const [range, setRange] = useState("1h");
  const host = useQuery(() => api(`/hosts/${id}`), [id]);
  const m = useQuery(() => api(`/hosts/${id}/metrics?range=${range}`), [id, range]);
  const svc = useQuery(() => api<any[]>(`/hosts/${id}/services?range=${range === "15m" || range === "1h" ? "24h" : range}`), [id, range]);
  const al = useQuery(() => api<any[]>(`/alerts?host_id=${id}&limit=10&include_simulated=true`), [id]);
  const me = useMe();
  const h = host.data, l = h?.latest;
  const pts = m.data?.points ?? [];
  if (host.error) return <ErrorNote error={host.error} />;
  if (!h) return <div className="muted">Loading…</div>;
  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{h.hostname}{h.is_simulated && <SimBadge />}</h1>
          <div className="text-sm ink2 mt-1 flex gap-3 items-center"><StatusBadge status={h.status} /><span>{h.os} {h.os_version} {h.arch}</span><span>{h.environment}{h.group ? ` / ${h.group}` : ""}</span>
            <span>agent {h.agent_version || "–"}{h.agent_outdated ? " (update available)" : ""}</span><span>last seen {ago(h.last_seen)}</span></div>
        </div>
        <div className="flex gap-2 items-center">
          <select className="input" aria-label="Time range" value={range} onChange={(e) => setRange(e.target.value)}>{RANGES.map((r) => <option key={r}>{r}</option>)}</select>
          <button className="btn" onClick={() => download(`/hosts/${id}/metrics/export?format=csv&range=${range}`, `${h.hostname}-${range}.csv`)}>Export CSV</button>
          {canAtLeast(me, "admin") && !h.is_simulated && <button className="btn" onClick={async () => { if (confirm("Revoke this agent's credentials?")) { await api(`/hosts/${id}`, { method: "PATCH", body: { revoked: true } }); host.reload(); } }}>Revoke agent</button>}
        </div>
      </div>
      {h.status === "pending" && <div className="card p-3 text-sm ink2">This host is registered but has not reported yet. It is not being monitored until the agent communicates successfully.</div>}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="CPU" value={pct(l?.cpu_percent)} /><Stat label="Memory" value={pct(l?.mem_percent)} sub={l ? `${bytes(l.mem_available_bytes)} available` : undefined} />
        <Stat label="Disk" value={pct(l?.disk_percent)} sub={l ? `${bytes(l.disk_free_bytes)} free` : undefined} />
        <Stat label="Uptime" value={dur(l?.uptime_seconds)} /><Stat label="Load (1/5/15)" value={l?.load1 != null ? `${l.load1} / ${l.load5} / ${l.load15}` : "n/a"} sub={l?.load1 == null ? "not supported on this OS" : undefined} />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <LineChart title="CPU utilization" points={pts} series={[{ key: "cpu_percent", label: "CPU", color: S1 }]} unit="%" max={100} />
        <LineChart title="Memory utilization" points={pts} series={[{ key: "mem_percent", label: "Memory", color: S1 }]} unit="%" max={100} />
        <LineChart title="Disk utilization" points={pts} series={[{ key: "disk_percent", label: "Disk", color: S1 }]} unit="%" max={100} />
        <LineChart title="Network throughput" points={pts} series={[{ key: "net_recv_bps", label: "Received", color: S1 }, { key: "net_sent_bps", label: "Sent", color: S2 }]} format={(v) => `${bytes(v)}/s`} />
      </div>
      <section className="card" data-testid="services">
        <h2 className="text-sm font-medium p-4 pb-2">Services & health checks</h2>
        <table className="w-full"><thead><tr><th>Name</th><th>Status</th><th>Target</th><th>Availability</th><th>Avg response</th><th>Failed checks</th></tr></thead>
          <tbody>{(svc.data ?? []).map((s) => (
            <tr key={s.name}><td>{s.name}</td><td style={{ color: s.ok ? "var(--ok)" : "var(--crit)" }}>{s.ok ? "● Up" : `✕ Down${s.error ? ` (${s.error})` : ""}`}</td>
              <td className="ink2">{s.target}</td><td><Meter value={s.availability_percent} label="availability" goodHigh /></td>
              <td>{s.avg_response_ms != null ? `${s.avg_response_ms} ms` : "–"}</td><td>{s.failed_checks}/{s.checks}</td></tr>))}
            {svc.data?.length === 0 && <tr><td colSpan={6} className="muted text-center py-6">No service checks configured on this agent.</td></tr>}</tbody></table>
      </section>
      <section className="card"><h2 className="text-sm font-medium p-4 pb-2">Alert history</h2>
        <table className="w-full"><tbody>{(al.data ?? []).map((a) => (
          <tr key={a.id}><td><SeverityBadge severity={a.severity} /></td><td>{a.title}</td><td className="ink2">{a.status}</td><td className="muted">{ago(a.opened_at)}</td></tr>))}
          {al.data?.length === 0 && <tr><td className="muted text-center py-6">No alerts for this host.</td></tr>}</tbody></table></section>
    </div>
  );
}
