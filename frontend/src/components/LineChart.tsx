import { useMemo, useRef, useState } from "react";

export type Series = { key: string; label: string; color: string };
type Pt = { ts: string; [k: string]: number | string | null };

/** Dependency-free SVG line chart: one y-axis, recessive grid, hover crosshair + tooltip, legend, table view. */
export default function LineChart({ title, points, series, unit = "", max, format, height = 180 }: {
  title: string; points: Pt[]; series: Series[]; unit?: string; max?: number; height?: number;
  format?: (v: number) => string;
}) {
  const W = 640, H = height, pad = { l: 66, r: 12, t: 10, b: 22 };
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const ref = useRef<SVGSVGElement>(null);
  const fmt = format ?? ((v: number) => `${v.toFixed(1)}${unit}`);

  const { xs, ymax, x, y } = useMemo(() => {
    const xs = points.map((p) => new Date(p.ts).getTime());
    const vals = points.flatMap((p) => series.map((s) => p[s.key] as number | null).filter((v): v is number => v != null));
    const ymax = max ?? Math.max(1, ...vals) * 1.15;
    const x0 = xs[0] ?? 0, x1 = xs[xs.length - 1] ?? 1;
    return { xs, ymax,
      x: (t: number) => pad.l + ((t - x0) / Math.max(1, x1 - x0)) * (W - pad.l - pad.r),
      y: (v: number) => pad.t + (1 - v / ymax) * (H - pad.t - pad.b) };
  }, [points, series, max, H]);

  const path = (key: string) => {
    let d = "", pen = false;
    points.forEach((p, i) => {
      const v = p[key] as number | null;
      if (v == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(xs[i]).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
    });
    return d;
  };
  const onMove = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    let best = 0, bd = Infinity;
    xs.forEach((t, i) => { const d = Math.abs(x(t) - px); if (d < bd) { bd = d; best = i; } });
    setHover(best);
  };
  const ticks = [0, 0.5, 1].map((f) => f * ymax);
  const fmtTime = (t: number) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const hp = hover != null ? points[hover] : null;

  return (
    <div className="card p-4" data-testid={`chart-${title}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium">{title}</h3>
        <div className="flex items-center gap-3">
          {series.length > 1 && series.map((s) => (
            <span key={s.key} className="text-xs ink2 flex items-center gap-1">
              <span style={{ background: s.color, width: 10, height: 2, display: "inline-block" }} />{s.label}
            </span>
          ))}
          <button className="btn" onClick={() => setTable(!table)}>{table ? "Chart" : "Table"}</button>
        </div>
      </div>
      {points.length === 0 ? (
        <div className="muted text-sm py-10 text-center">No data in this time range</div>
      ) : table ? (
        <div className="max-h-48 overflow-auto"><table className="w-full"><thead><tr><th>Time</th>{series.map((s) => <th key={s.key}>{s.label}</th>)}</tr></thead>
          <tbody>{points.slice(-50).reverse().map((p) => (
            <tr key={p.ts}><td>{new Date(p.ts).toLocaleString()}</td>{series.map((s) => <td key={s.key}>{p[s.key] != null ? fmt(p[s.key] as number) : "–"}</td>)}</tr>))}</tbody></table></div>
      ) : (
        <div className="relative">
          <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${title} chart`}
            onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
            {ticks.map((t) => (
              <g key={t}><line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--line)" />
                <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--muted)">{fmt(t)}</text></g>))}
            <text x={pad.l} y={H - 6} fontSize="10" fill="var(--muted)">{fmtTime(xs[0])}</text>
            <text x={W - pad.r} y={H - 6} fontSize="10" textAnchor="end" fill="var(--muted)">{fmtTime(xs[xs.length - 1])}</text>
            {series.map((s) => <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" />)}
            {hp && hover != null && <g>
              <line x1={x(xs[hover])} x2={x(xs[hover])} y1={pad.t} y2={H - pad.b} stroke="var(--muted)" strokeDasharray="3 3" />
              {series.map((s) => hp[s.key] != null && <circle key={s.key} cx={x(xs[hover])} cy={y(hp[s.key] as number)} r={4}
                fill={s.color} stroke="var(--surface)" strokeWidth={2} />)}</g>}
          </svg>
          {hp && hover != null && (
            <div className="absolute pointer-events-none card px-2 py-1 text-xs shadow" style={{ left: `${(x(xs[hover]) / W) * 100}%`, top: 0, transform: "translateX(-50%)" }}>
              <div className="muted">{new Date(hp.ts).toLocaleString()}</div>
              {series.map((s) => <div key={s.key}><span style={{ color: s.color }}>●</span> {s.label}: {hp[s.key] != null ? fmt(hp[s.key] as number) : "–"}</div>)}
            </div>)}
        </div>
      )}
    </div>
  );
}
