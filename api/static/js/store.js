// Shared client state: the offer list, the one piece of state this UI writes
// back (user_verdict — a pure human triage decision, never read or
// influenced by the scoring pipeline), and per-viewer conveniences.

import { fetchOffers, fetchOffer, postVerdict } from "./api.js";
import { isTriageable, parseSqlUtc, duplicateKey } from "./format.js";

const listeners = new Set();
const detailCache = new Map();

export const store = {
  offers: [],
  byId: new Map(),
  loaded: false,
  previousVisit: null, // Date — offers first seen after it are "new"
  lastRun: null, // Date — most recent scraping activity seen in the data
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(change) {
  listeners.forEach((fn) => fn(change));
}

// ---------------------------------------------------------------------
// localStorage can throw (private mode, blocked storage) — never let that
// break the page, it's only ever used for conveniences.
// ---------------------------------------------------------------------
export const prefs = {
  get(key, fallback = null) {
    try {
      const v = localStorage.getItem(`ja-${key}`);
      return v === null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(`ja-${key}`, JSON.stringify(value));
    } catch {}
  },
};

// "New since your last visit": the previous visit's timestamp is frozen for
// the whole browsing session (sessionStorage) so reloading doesn't wipe the
// markers, while the stored "last visit" moves forward to now.
function resolvePreviousVisit() {
  let prev = null;
  try {
    const frozen = sessionStorage.getItem("ja-prev-visit");
    if (frozen !== null) prev = frozen === "" ? null : new Date(frozen);
    else {
      const last = prefs.get("last-visit");
      prev = last ? new Date(last) : null;
      sessionStorage.setItem("ja-prev-visit", last || "");
    }
  } catch {}
  prefs.set("last-visit", new Date().toISOString());
  return prev;
}

export async function loadOffers() {
  const offers = await fetchOffers();
  store.offers = offers;
  store.byId = new Map(offers.map((o) => [o.id, o]));
  store.loaded = true;

  let latest = null;
  for (const o of offers) {
    o._firstSeen = parseSqlUtc(o.first_seen_at);
    const seen = parseSqlUtc(o.last_seen_at);
    for (const d of [o._firstSeen, seen]) if (d && (!latest || d > latest)) latest = d;
  }
  store.lastRun = latest;

  const groups = new Map();
  for (const o of offers) {
    const k = duplicateKey(o);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(o.id);
  }
  for (const o of offers) o._twins = groups.get(duplicateKey(o)).filter((id) => id !== o.id);

  // First visit ever: treat the most recent scraping day as "new", so the
  // brief has something meaningful to say instead of flagging all 300 offers.
  const prev = resolvePreviousVisit();
  store.previousVisit = prev || (latest ? new Date(latest.getTime() - 20 * 3600 * 1000) : null);
  emit({ type: "load" });
}

// Days since an offer last showed up in a scraping run, measured against the
// most recent run (not "now"), so a paused pipeline doesn't flag everything.
// The scraper only reads the first result pages: absence means "no longer
// found by the collection", not proof the position is filled.
export function staleDays(o) {
  const seen = parseSqlUtc(o.last_seen_at) || o._firstSeen;
  if (!seen || !store.lastRun) return 0;
  return Math.floor((store.lastRun - seen) / 86400000);
}
export const STALE_AFTER = 3;

export const isNew = (o) => !!(store.previousVisit && o._firstSeen && o._firstSeen > store.previousVisit);

export const triageable = () => store.offers.filter(isTriageable);
export const pending = () => triageable().filter((o) => !o.user_verdict);

export async function getDetail(id) {
  if (detailCache.has(id)) return detailCache.get(id);
  const p = fetchOffer(id).then((d) => {
    const o = store.byId.get(id);
    if (o) d.user_verdict = o.user_verdict; // the list is the source of truth once loaded
    return d;
  });
  detailCache.set(id, p);
  p.catch(() => detailCache.delete(id));
  return p;
}

// Optimistic: updates the cache and notifies every view immediately, rolls
// back (and rethrows) if the server refuses. Returns the previous verdict so
// callers can offer an undo.
export async function setVerdict(id, verdict) {
  const o = store.byId.get(id);
  if (!o) return undefined;
  const previous = o.user_verdict ?? null;
  if (previous === verdict) return previous;
  o.user_verdict = verdict;
  emit({ type: "verdict", id, verdict, previous });
  try {
    await postVerdict(id, verdict);
  } catch (err) {
    o.user_verdict = previous;
    emit({ type: "verdict", id, verdict: previous, previous: verdict });
    throw err;
  }
  return previous;
}
