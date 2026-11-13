const TOKEN_KEY = "infrawatch_token";
export type Role = "viewer" | "operator" | "admin";
export const auth = {
  get token() { return sessionStorage.getItem(TOKEN_KEY); },
  set(t: string | null) { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY); },
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const r = await fetch("/api/v1" + path, {
    method: opts.method ?? "GET",
    headers: { ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (r.status === 401 && auth.token) { auth.set(null); location.href = "/login"; }
  if (!r.ok) {
    let msg = r.statusText;
    try { const d = await r.json(); msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail); } catch { /* ignore */ }
    throw new ApiError(r.status, msg);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

export async function download(path: string, filename: string) {
  const r = await fetch("/api/v1" + path, { headers: { Authorization: `Bearer ${auth.token}` } });
  if (!r.ok) throw new ApiError(r.status, "export failed");
  const url = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click(); URL.revokeObjectURL(url);
}
