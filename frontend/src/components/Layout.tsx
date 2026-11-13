import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { auth } from "../api";
import { useMe } from "../session";

export default function Layout() {
  const nav = useNavigate();
  const me = useMe();
  const link = ({ isActive }: { isActive: boolean }) => `px-3 py-1.5 rounded-md text-sm ${isActive ? "font-medium" : "ink2"}`;
  return (
    <div className="min-h-screen">
      <header className="border-b" style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-4">
          <span className="font-semibold tracking-tight">▣ InfraWatch</span>
          <nav className="flex gap-1 flex-1">
            <NavLink to="/" end className={link}>Overview</NavLink>
            <NavLink to="/hosts" className={link}>Hosts</NavLink>
            <NavLink to="/alerts" className={link}>Alerts</NavLink>
            <NavLink to="/reports" className={link}>Reports</NavLink>
            {me?.role === "admin" && <NavLink to="/settings" className={link}>Settings</NavLink>}
          </nav>
          <span className="text-xs ink2">{me?.username} · {me?.role}</span>
          <button className="btn" onClick={() => { auth.set(null); nav("/login"); }}>Sign out</button>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6"><Outlet /></main>
    </div>
  );
}
