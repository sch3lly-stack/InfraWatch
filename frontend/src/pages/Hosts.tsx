import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ago, useQuery } from "../hooks";
import { useFilters } from "../session";
import { ErrorNote, SimBadge, StatusBadge } from "../components/ui";
import FilterBar from "./Filters";

export default function Hosts() {
  const { f } = useFilters();
  const [search, setSearch] = useState(""); const [status, setStatus] = useState(""); const [group, setGroup] = useState("");
  const qs = new URLSearchParams({ include_simulated: String(f.sim), ...(f.env && { environment: f.env }), ...(search && { search }), ...(status && { status }), ...(group && { group }) }).toString();
  const { data, error } = useQuery(() => api<any[]>(`/hosts?${qs}`), [qs]);
  const envs = useQuery(() => api(`/overview?include_simulated=${f.sim}`), [f.sim]);
  const groups = [...new Set((data ?? []).map((h) => h.group).filter(Boolean))];
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-semibold">Hosts</h1><FilterBar environments={envs.data?.environments ?? []} /></div>
      <div className="flex gap-2">
        <input className="input" placeholder="Search hostname…" aria-label="Search hostname" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="input" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option><option>online</option><option>offline</option><option>pending</option></select>
        <select className="input" aria-label="Group" value={group} onChange={(e) => setGroup(e.target.value)}>
          <option value="">Any group</option>{groups.map((g) => <option key={g}>{g}</option>)}</select>
      </div>
      <ErrorNote error={error} />
      <div className="card"><table className="w-full"><thead><tr><th>Hostname</th><th>Status</th><th>Environment</th><th>Group</th><th>OS</th><th>Agent</th><th>Last communication</th></tr></thead>
        <tbody>{(data ?? []).map((h) => (
          <tr key={h.id}><td><Link className="underline" to={`/hosts/${h.id}`}>{h.hostname}</Link>{h.is_simulated && <SimBadge />}</td><td><StatusBadge status={h.status} /></td>
            <td>{h.environment}</td><td>{h.group || "–"}</td><td>{h.os} {h.os_version}</td><td>{h.agent_version || "–"}</td><td className="ink2">{ago(h.last_seen)}</td></tr>))}
          {data?.length === 0 && <tr><td colSpan={7} className="muted text-center py-8">No hosts match.</td></tr>}</tbody></table></div>
    </div>
  );
}
