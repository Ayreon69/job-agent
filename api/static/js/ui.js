// Shared UI fragments and small widgets (toasts, tooltip, verdict controls).

import { esc, icon, VERDICTS, VERDICT_META, ZONE_LABELS, SOURCE_LABELS, companyOf, locationOf, cleanContract, cleanSalary, parsePublished, relDay, fmtDate, scoreTier, titleOf } from "./format.js";
import { setVerdict, isNew } from "./store.js";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------------------------------------------------------------------
// Errors & toasts
// ---------------------------------------------------------------------

export function showError(message) {
  const banner = $("#error-banner");
  banner.innerHTML = `${icon("i-alert")}<span>${esc(message)}</span><button type="button" class="icon-btn" aria-label="Fermer">${icon("i-x")}</button>`;
  banner.hidden = false;
  banner.querySelector("button").onclick = () => (banner.hidden = true);
}

export function toast(message, { action, onAction, tone = "", timeout = 4200 } = {}) {
  const host = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast ${tone ? `toast--${tone}` : ""}`;
  el.innerHTML = `<span>${message}</span>${action ? `<button type="button">${esc(action)}</button>` : ""}`;
  host.appendChild(el);
  const close = () => {
    el.classList.add("is-leaving");
    setTimeout(() => el.remove(), 260);
  };
  if (action) el.querySelector("button").onclick = () => { onAction?.(); close(); };
  setTimeout(close, timeout);
  while (host.children.length > 3) host.firstElementChild.remove();
}

// Sets a verdict from any view, with a toast offering an undo.
export async function decide(offer, verdict, { quiet = false } = {}) {
  try {
    const previous = await setVerdict(offer.id, verdict);
    if (quiet) return true;
    const meta = VERDICT_META[verdict];
    const msg = verdict
      ? `${icon(meta.icon, `tone-${verdict}`)} <b>${esc(truncate(titleOf(offer), 42))}</b> → ${meta.label}`
      : `Avis effacé pour <b>${esc(truncate(titleOf(offer), 42))}</b>`;
    toast(msg, { action: "Annuler", onAction: () => setVerdict(offer.id, previous ?? null).catch(() => {}) });
    return true;
  } catch (err) {
    showError(`Impossible d'enregistrer l'avis (${err.message}).`);
    return false;
  }
}

export const truncate = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s || "");

// ---------------------------------------------------------------------
// Tooltip (charts)
// ---------------------------------------------------------------------

export function wireTooltips(root) {
  const tip = $("#tooltip");
  root.addEventListener("pointermove", (e) => {
    const t = e.target.closest("[data-tip]");
    if (!t) {
      tip.hidden = true;
      return;
    }
    tip.innerHTML = t.dataset.tip;
    tip.hidden = false;
    const pad = 14;
    const { innerWidth: W } = window;
    const r = tip.getBoundingClientRect();
    let x = e.clientX + pad;
    if (x + r.width > W - 8) x = e.clientX - r.width - pad;
    tip.style.transform = `translate(${x}px, ${e.clientY - r.height - pad}px)`;
  });
  root.addEventListener("pointerleave", () => (tip.hidden = true));
}

// ---------------------------------------------------------------------
// Offer fragments
// ---------------------------------------------------------------------

export function zoneChip(zone) {
  if (!zone) return "";
  return `<span class="chip chip--zone chip--${zone === "inconnu" ? "warn" : "zone"}">${icon("i-pin")}${esc(ZONE_LABELS[zone] || zone)}</span>`;
}

export function sectorChip(sector) {
  return sector ? `<span class="chip chip--sector" title="${esc(sector)}">${esc(sector)}</span>` : "";
}

export function scorePill(score) {
  return `<span class="score-pill score-pill--${scoreTier(score)}" title="Score d'adéquation">${score ?? "–"}</span>`;
}

export function newDot(o) {
  return isNew(o) ? '<span class="new-dot" title="Nouvelle depuis ta dernière visite">Nouveau</span>' : "";
}

export function twinBadge(o) {
  if (!o._twins?.length) return "";
  const n = o._twins.length + 1;
  return `<span class="twin-badge" title="Même intitulé, même lieu : probablement la même offre publiée ${n} fois">×${n}</span>`;
}

export function metaLine(o, { withSource = false } = {}) {
  const bits = [];
  const loc = locationOf(o);
  if (loc) bits.push(`${icon("i-pin")}${esc(loc)}`);
  const contract = cleanContract(o.contract_type);
  if (contract) bits.push(`${icon("i-case")}${esc(contract)}`);
  const salary = cleanSalary(o.salary);
  if (salary) bits.push(`${icon("i-coins")}${esc(salary)}`);
  if (withSource && o.source) bits.push(`${icon("i-source")}${esc(SOURCE_LABELS[o.source] || o.source)}`);
  return bits.map((b) => `<span>${b}</span>`).join("");
}

export function dateLabel(o) {
  const pub = parsePublished(o.published_at);
  if (pub) return { text: relDay(pub), title: `Publiée le ${fmtDate(pub)}` };
  if (o._firstSeen) return { text: relDay(o._firstSeen), title: `Vue pour la première fois le ${fmtDate(o._firstSeen)}` };
  return { text: "—", title: "Date inconnue" };
}

export function verdictBadge(o) {
  if (!o.user_verdict) return "";
  const m = VERDICT_META[o.user_verdict];
  return `<span class="verdict-badge verdict-badge--${o.user_verdict}">${icon(m.icon)}${m.label}</span>`;
}

// Segmented control used in the drawer and on list rows.
export function verdictControl(o, { compact = false } = {}) {
  return `
    <div class="verdict-control ${compact ? "verdict-control--compact" : ""}" role="group" aria-label="Mon avis">
      ${VERDICTS.map((v) => {
        const m = VERDICT_META[v];
        const on = o.user_verdict === v;
        return `<button type="button" class="vbtn vbtn--${v} ${on ? "is-on" : ""}" data-verdict="${v}" aria-pressed="${on}" title="${m.label} (${m.key})">${icon(m.icon)}<span>${compact ? m.short : m.label}</span></button>`;
      }).join("")}
    </div>`;
}

// Animated count-up for headline numbers.
export function countUp(el, to, duration = 900) {
  if (reducedMotion() || !Number.isFinite(to)) {
    el.textContent = to;
    return;
  }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(to * eased);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
