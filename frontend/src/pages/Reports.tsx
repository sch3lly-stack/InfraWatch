import { useState } from "react";
import { api } from "../api";
import { useQuery } from "../hooks";
import { useFilters } from "../session";
import { ErrorNote, Meter } from "../components/ui";
import FilterBar from "./Filters";

export default function Reports() {
  const { f } = useFilters();
  const [range, setRange] = useState("7d");
  const { data, error } = useQuery(() => api(`/reports/summary?range=${range}&include_simulated=${f.sim}${f.env ? `&environment=${f.env}` : ""}`), [range, f.sim, f.env], 60000);
  const envs = useQuery(() => api(`/overview?include_simulated=${f.sim}`), [f.sim]);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-semibold">Historical report</h1>
        <div className="flex gap-3 items-center"><FilterBar environments={envs.data?.environments ?? []} /><select className="input" aria-label="Report range" value={range} onChange={(e) => setRange(e.target.value)}>{["24h", "7d", "30d"].map((r) => <option key={r}>{r}</option>)}</select></div></div>
      <ErrorNote error={error} />
      <div className="card"><table className="w-full"><thead><tr><th>Host</th><th>Environment</th><th>Availability</th><th>Avg CPU</th><th>Max CPU</th><th>Avg mem</th><th>Max mem</th><th>Max disk</th><th>Alerts</th></tr></thead>
        <tbody>{(data?.hosts ?? []).map((h: any) => (
          <tr key={h.host_id}><td>{h.hostname}</td><td>{h.environment}</td><td><Meter value={h.availability_percent} label="availability" goodHigh /></td>
            <td>{h.avg_cpu ?? "–"}%</td><td>{h.max_cpu ?? "–"}%</td><td>{h.avg_mem ?? "–"}%</td><td>{h.max_mem ?? "–"}%</td><td>{h.max_disk ?? "–"}%</td><td>{h.alerts}</td></tr>))}
          {data?.hosts.length === 0 && <tr><td colSpan={9} className="muted text-center py-8">No hosts.</td></tr>}</tbody></table></div>
    </div>
  );
}
