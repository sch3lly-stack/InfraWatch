import { ReactNode } from "react";

const STATUS: Record<string, { icon: string; label: string; color: string }> = {
  online: { icon: "●", label: "Online", color: "var(--ok)" },
  offline: { icon: "✕", label: "Offline", color: "var(--crit)" },
  pending: { icon: "○", label: "Pending", color: "var(--muted)" },
  revoked: { icon: "⊘", label: "Revoked", color: "var(--muted)" },
};
export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? STATUS.pending;
  return <span className="text-xs inline-flex items-center gap-1" style={{ color: s.color }} data-testid="status">{s.icon} {s.label}</span>;
}

const SEV: Record<string, { icon: string; color: string }> = {
  critical: { icon: "▲", color: "var(--crit)" }, warning: { icon: "◆", color: "var(--warn)" }, info: { icon: "ℹ", color: "var(--s1)" },
};
export function SeverityBadge({ severity }: { severity: string }) {
  const s = SEV[severity] ?? SEV.info;
  return <span className="text-xs inline-flex items-center gap-1" style={{ color: s.color }}>{s.icon} {severity}</span>;
}
export function SimBadge() {
  return <span className="text-[10px] ml-2 px-1.5 py-0.5 rounded border muted" style={{ borderColor: "var(--line)" }} title="Simulated data, not a real monitored system">SIMULATED</span>;
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: string; tone?: "crit" | "warn" }) {
  return (
    <div className="card p-4" data-testid={`stat-${label}`}>
      <div className="text-xs ink2">{label}</div>
      <div className="text-2xl font-semibold mt-1" style={{ color: tone === "crit" ? "var(--crit)" : tone === "warn" ? "var(--warn)" : undefined }}>{value}</div>
      {sub && <div className="text-xs muted mt-0.5">{sub}</div>}
    </div>
  );
}

/** Utilization meter (high = bad). With goodHigh (e.g. availability) low values are flagged instead. */
export function Meter({ value, label, goodHigh }: { value?: number | null; label: string; goodHigh?: boolean }) {
  const v = value ?? 0;
  const bad = goodHigh ? 100 - v : v;
  const color = bad >= 90 ? "var(--crit)" : bad >= 75 ? "var(--warn)" : "var(--s1)";
  return (
    <div className="min-w-[90px]" title={label}>
      <div className="text-xs">{value == null ? "–" : `${v.toFixed(goodHigh ? 1 : 0)}%`}</div>
      <div className="h-1.5 rounded-full" style={{ background: "var(--line)" }}>
        <div className="h-1.5 rounded-full" style={{ width: `${Math.min(100, v)}%`, background: color }} />
      </div>
    </div>
  );
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? <div role="alert" className="card p-3 text-sm" style={{ color: "var(--crit)" }}>⚠ {error}</div> : null;
}
