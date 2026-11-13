import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api";

export default function Login() {
  const nav = useNavigate();
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [err, setErr] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr("");
    try { const r = await api("/auth/login", { method: "POST", body: { username: u, password: p } }); auth.set(r.access_token); nav("/"); }
    catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="min-h-screen flex items-center justify-center">
      <form onSubmit={submit} className="card p-6 w-80 space-y-3">
        <h1 className="text-lg font-semibold">▣ InfraWatch</h1>
        <input className="input w-full" placeholder="Username" aria-label="Username" value={u} onChange={(e) => setU(e.target.value)} autoFocus />
        <input className="input w-full" placeholder="Password" aria-label="Password" type="password" value={p} onChange={(e) => setP(e.target.value)} />
        {err && <div role="alert" className="text-sm" style={{ color: "var(--crit)" }}>{err}</div>}
        <button className="btn btn-primary w-full" type="submit">Sign in</button>
      </form>
    </div>
  );
}
