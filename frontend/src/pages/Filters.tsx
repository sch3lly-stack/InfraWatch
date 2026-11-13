import { useFilters } from "../session";

export default function FilterBar({ environments }: { environments: string[] }) {
  const { f, set } = useFilters();
  return (
    <div className="flex items-center gap-3 text-sm">
      <select className="input" aria-label="Environment" value={f.env} onChange={(e) => set({ env: e.target.value })}>
        <option value="">All environments</option>
        {environments.map((e) => <option key={e}>{e}</option>)}
      </select>
      <label className="flex items-center gap-1.5 ink2"><input type="checkbox" checked={f.sim} onChange={(e) => set({ sim: e.target.checked })} />Show simulated data</label>
    </div>
  );
}
