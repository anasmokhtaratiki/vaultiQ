export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function request(path, { token, ...opts } = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  const type = res.headers.get("content-type") || "";
  const body = type.includes("json") ? await res.json() : await res.blob();
  if (!res.ok) throw Object.assign(new Error("request failed"), { status: res.status, body });
  return { status: res.status, body };
}

export const errText = (e) => {
  const b = e.body;
  if (b?.message) return b.message;
  if (typeof b?.detail === "string") return b.detail;
  if (b?.detail?.message) return `${b.detail.message}${b.detail.trust_score != null ? ` (score ${b.detail.trust_score})` : ""}`;
  return e.message;
};
