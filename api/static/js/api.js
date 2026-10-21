// Thin fetch wrappers over the FastAPI endpoints (api/main.py). No logic here.

// The owner token (OWNER_TOKEN, see api/main.py) is kept in this browser
// only and sent with every request, so the API can tell the owner (verdicts,
// analyses) from a visitor (public view).
const TOKEN_KEY = "ja-owner-token";

export function ownerToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setOwnerToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {}
}

async function request(method, url, body, token = ownerToken()) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (!res.ok) {
    const err = new Error(`${method} ${url} -> ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const fetchOffers = () => request("GET", "/offers");
export const fetchOffer = (id) => request("GET", `/offers/${id}`);
export const fetchHealth = () => request("GET", "/health").catch(() => null);
export const postVerdict = (id, verdict) => request("POST", `/offers/${id}/verdict`, { verdict });
// Whether `token` (default: the stored one) is the owner's.
export const fetchOwner = (token) => request("GET", "/owner", undefined, token).then((r) => r.owner).catch(() => false);
