import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api, Role } from "./api";

type Me = { username: string; role: Role };
const Ctx = createContext<Me | null>(null);
export const useMe = () => useContext(Ctx);
export const canAtLeast = (me: Me | null, r: Role) => !!me && ["viewer", "operator", "admin"].indexOf(me.role) >= ["viewer", "operator", "admin"].indexOf(r);

/** Global dashboard filters (shared across pages, persisted for the session). */
type Filters = { env: string; sim: boolean };
const F = createContext<{ f: Filters; set: (p: Partial<Filters>) => void }>({ f: { env: "", sim: false }, set: () => {} });
export const useFilters = () => useContext(F);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [f, setF] = useState<Filters>(() => JSON.parse(sessionStorage.getItem("iw_filters") ?? '{"env":"","sim":false}'));
  useEffect(() => { api("/auth/me").then(setMe).catch(() => {}); }, []);
  const set = (p: Partial<Filters>) => setF((o) => { const n = { ...o, ...p }; sessionStorage.setItem("iw_filters", JSON.stringify(n)); return n; });
  return <Ctx.Provider value={me}><F.Provider value={{ f, set }}>{children}</F.Provider></Ctx.Provider>;
}
