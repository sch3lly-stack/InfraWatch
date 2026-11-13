import { FormEvent, useState } from "react";
import { api } from "../api";
import { ago, useQuery } from "../hooks";
import { ErrorNote } from "../components/ui";

const TYPES = ["cpu_high", "mem_high", "disk_low", "host_down", "service_down", "response_slow"];
const needsThreshold = (t: string) => !["host_down", "service_down"].includes(t);

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card p-4 space-y-3"><h2 className="text-sm font-medium">{title}</h2>{children}</section>;
}

export default function Settings() {
  const rules = useQuery(() => api<any[]>("/rules"), [], 0);
  const chans = useQuery(() => api<any[]>("/channels"), [], 0);
  const maint = useQuery(() => api<any[]>("/maintenance"), [], 0);
  const toks = useQuery(() => api<any[]>("/enrollment-tokens"), [], 0);
  const users = useQuery(() => api<any[]>("/users"), [], 0);
  const audit = useQuery(() => api<any[]>("/audit?limit=20"), [], 0);
  const [err, setErr] = useState<string | null>(null);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [rule, setRule] = useState({ name: "", type: "cpu_high", threshold: "90", severity: "warning", for_seconds: "0", cooldown_seconds: "300", environment: "" });
  const [ch, setCh] = useState({ name: "", url: "", min_severity: "warning" });
  const [tk, setTk] = useState({ environment: "production", group: "", label: "", ttl_minutes: "60" });
  const [mw, setMw] = useState({ name: "", environment: "", minutes: "60" });
  const [us, setUs] = useState({ username: "", password: "", role: "viewer" });
  const run = async (fn: () => Promise<unknown>, after: { reload: () => void }[]) => { try { setErr(null); await fn(); after.forEach((a) => a.reload()); } catch (e: any) { setErr(e.message); } };

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Settings</h1>
      <ErrorNote error={err} />
      <Section title="Enrollment tokens (register a new agent)">
        <form className="flex flex-wrap gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); run(async () => { const r = await api("/enrollment-tokens", { method: "POST", body: { ...tk, ttl_minutes: +tk.ttl_minutes } }); setNewToken(r.token); }, [toks]); }}>
          <input className="input" aria-label="Token environment" placeholder="environment" value={tk.environment} onChange={(e) => setTk({ ...tk, environment: e.target.value })} />
          <input className="input" aria-label="Token group" placeholder="group" value={tk.group} onChange={(e) => setTk({ ...tk, group: e.target.value })} />
          <input className="input w-24" aria-label="Token TTL minutes" value={tk.ttl_minutes} onChange={(e) => setTk({ ...tk, ttl_minutes: e.target.value })} />
          <button className="btn btn-primary" type="submit">Create token</button></form>
        {newToken && <div className="text-sm p-2 rounded border" style={{ borderColor: "var(--warn)" }} data-testid="new-token">Copy now, it is shown once: <code className="select-all">{newToken}</code></div>}
        <table className="w-full"><tbody>{(toks.data ?? []).slice(0, 5).map((t) => <tr key={t.id}><td>#{t.id} {t.environment}</td><td className="muted">expires {ago(t.expires_at)}</td><td>{t.used_at ? "used" : "unused"}</td></tr>)}</tbody></table>
      </Section>
      <Section title="Alert rules">
        <form className="flex flex-wrap gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => api("/rules", { method: "POST", body: { name: rule.name, type: rule.type, severity: rule.severity, threshold: needsThreshold(rule.type) ? +rule.threshold : null, for_seconds: +rule.for_seconds, cooldown_seconds: +rule.cooldown_seconds, environment: rule.environment || null } }), [rules]); }}>
          <input className="input" aria-label="Rule name" placeholder="name" value={rule.name} onChange={(e) => setRule({ ...rule, name: e.target.value })} required />
          <select className="input" aria-label="Rule type" value={rule.type} onChange={(e) => setRule({ ...rule, type: e.target.value })}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select>
          {needsThreshold(rule.type) && <input className="input w-24" aria-label="Threshold" value={rule.threshold} onChange={(e) => setRule({ ...rule, threshold: e.target.value })} />}
          <select className="input" aria-label="Severity" value={rule.severity} onChange={(e) => setRule({ ...rule, severity: e.target.value })}><option>info</option><option>warning</option><option>critical</option></select>
          <input className="input w-28" aria-label="Duration seconds" title="Condition must hold for (s)" value={rule.for_seconds} onChange={(e) => setRule({ ...rule, for_seconds: e.target.value })} />
          <input className="input w-28" aria-label="Cooldown seconds" title="Cooldown (s)" value={rule.cooldown_seconds} onChange={(e) => setRule({ ...rule, cooldown_seconds: e.target.value })} />
          <input className="input" aria-label="Rule environment" placeholder="environment (all)" value={rule.environment} onChange={(e) => setRule({ ...rule, environment: e.target.value })} />
          <button className="btn btn-primary" type="submit">Add rule</button></form>
        <table className="w-full"><thead><tr><th>Name</th><th>Type</th><th>Threshold</th><th>Severity</th><th>Hold</th><th>Cooldown</th><th>Scope</th><th></th></tr></thead>
          <tbody>{(rules.data ?? []).map((r) => <tr key={r.id} data-testid="rule-row"><td>{r.name}</td><td>{r.type}</td><td>{r.threshold ?? "–"}</td><td>{r.severity}</td><td>{r.for_seconds}s</td><td>{r.cooldown_seconds}s</td><td>{r.environment ?? "all"}</td>
            <td><button className="btn" onClick={() => run(() => api(`/rules/${r.id}`, { method: "DELETE" }), [rules])}>Delete</button></td></tr>)}</tbody></table>
      </Section>
      <Section title="Notification channels (webhook)">
        <form className="flex flex-wrap gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => api("/channels", { method: "POST", body: ch }), [chans]); }}>
          <input className="input" aria-label="Channel name" placeholder="name" value={ch.name} onChange={(e) => setCh({ ...ch, name: e.target.value })} required />
          <input className="input w-80" aria-label="Webhook URL" placeholder="https://hooks.example.com/…" value={ch.url} onChange={(e) => setCh({ ...ch, url: e.target.value })} required />
          <select className="input" aria-label="Minimum severity" value={ch.min_severity} onChange={(e) => setCh({ ...ch, min_severity: e.target.value })}><option>info</option><option>warning</option><option>critical</option></select>
          <button className="btn btn-primary" type="submit">Add channel</button></form>
        <table className="w-full"><tbody>{(chans.data ?? []).map((c) => <tr key={c.id}><td>{c.name}</td><td className="ink2">{c.url}</td><td>≥ {c.min_severity}</td><td><button className="btn" onClick={() => run(() => api(`/channels/${c.id}`, { method: "DELETE" }), [chans])}>Delete</button></td></tr>)}</tbody></table>
      </Section>
      <Section title="Maintenance windows (suppress alerts)">
        <form className="flex flex-wrap gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); const s = new Date(); run(() => api("/maintenance", { method: "POST", body: { name: mw.name, environment: mw.environment || null, starts_at: s.toISOString(), ends_at: new Date(s.getTime() + +mw.minutes * 60000).toISOString() } }), [maint]); }}>
          <input className="input" aria-label="Window name" placeholder="name" value={mw.name} onChange={(e) => setMw({ ...mw, name: e.target.value })} required />
          <input className="input" aria-label="Window environment" placeholder="environment (all)" value={mw.environment} onChange={(e) => setMw({ ...mw, environment: e.target.value })} />
          <input className="input w-24" aria-label="Window minutes" value={mw.minutes} onChange={(e) => setMw({ ...mw, minutes: e.target.value })} />
          <button className="btn btn-primary" type="submit">Start window now</button></form>
        <table className="w-full"><tbody>{(maint.data ?? []).map((m) => <tr key={m.id}><td>{m.name}</td><td>{m.environment ?? "all"}</td><td className="muted">until {new Date(m.ends_at).toLocaleString()}</td><td><button className="btn" onClick={() => run(() => api(`/maintenance/${m.id}`, { method: "DELETE" }), [maint])}>End</button></td></tr>)}</tbody></table>
      </Section>
      <Section title="Users">
        <form className="flex flex-wrap gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => api("/users", { method: "POST", body: us }), [users]); }}>
          <input className="input" aria-label="New username" placeholder="username" value={us.username} onChange={(e) => setUs({ ...us, username: e.target.value })} required />
          <input className="input" aria-label="New password" type="password" placeholder="password (10+ chars)" value={us.password} onChange={(e) => setUs({ ...us, password: e.target.value })} required />
          <select className="input" aria-label="New role" value={us.role} onChange={(e) => setUs({ ...us, role: e.target.value })}><option>viewer</option><option>operator</option><option>admin</option></select>
          <button className="btn btn-primary" type="submit">Add user</button></form>
        <table className="w-full"><tbody>{(users.data ?? []).map((u) => <tr key={u.id}><td>{u.username}</td><td>{u.role}</td><td>{u.disabled ? "disabled" : "active"}</td></tr>)}</tbody></table>
      </Section>
      <Section title="Audit log (latest)">
        <table className="w-full"><tbody>{(audit.data ?? []).map((a) => <tr key={a.id}><td className="muted">{ago(a.ts)}</td><td>{a.actor}</td><td>{a.action}</td><td className="ink2">{a.target}</td><td className="muted">{a.ip}</td></tr>)}</tbody></table>
      </Section>
    </div>
  );
}
