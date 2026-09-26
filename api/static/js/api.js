// Thin fetch wrappers over the FastAPI endpoints (api/main.py). No logic here.

async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${url} -> ${res.status}`);
  return res.json();
}

export const fetchOffers = () => request("GET", "/offers");
export const fetchOffer = (id) => request("GET", `/offers/${id}`);
export const fetchHealth = () => request("GET", "/health").catch(() => null);
export const postVerdict = (id, verdict) => request("POST", `/offers/${id}/verdict`, { verdict });
