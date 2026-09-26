// "Offres" — the full list: search, filters, sort, keyboard navigation and
// one-key verdicts.

import { esc, icon, fold, searchText, ZONE_LABELS, ZONE_ORDER, SOURCE_LABELS, VERDICTS, VERDICT_META, companyOf, parsePublished, isTriageable, plural, titleOf } from "../format.js";
import { store, isNew, prefs } from "../store.js";
import { $, $$, metaLine, zoneChip, sectorChip, newDot, dateLabel, verdictControl, decide, scorePill, twinBadge, staleChip } from "../ui.js";
import { drawerOpenId } from "../drawer.js";

const DEFAULTS = { q: "", verdict: "", zone: "", sector: "", source: "", min: 0, onlyNew: false, sort: "score" };
let f = { ...DEFAULTS };
let root;
let ctx;
let dedup = prefs.get("dedup", false); // per-viewer preference, not a filter reset by "Réinitialiser"
let cursor = -1; // keyboard-selected row index
let animateNext = true;
let visible = [];

const SORTS = {
  score: { label: "Score", fn: (a, b) => (b.score ?? -1) - (a.score ?? -1) || b.id - a.id },
  recent: { label: "Repérées récemment", fn: (a, b) => (b._firstSeen ?? 0) - (a._firstSeen ?? 0) || (b.score ?? -1) - (a.score ?? -1) },
  published: { label: "Date de publication", fn: (a, b) => (parsePublished(b.published_at) ?? 0) - (parsePublished(a.published_at) ?? 0) },
  company: { label: "Entreprise (A→Z)", fn: (a, b) => companyOf(a).localeCompare(companyOf(b), "fr") },
};

export function mount(el, context) {
  root = el;
  ctx = context;
  root.innerHTML = `
    <header class="page-head reveal">
      <div>
        <p class="kicker">Toutes les offres</p>
        <h1 class="page-title">Offres <span class="page-title__count" id="of-count"></span></h1>
      </div>
      <label class="sort">Trier par
        <select id="of-sort">${Object.entries(SORTS).map(([k, s]) => `<option value="${k}">${s.label}</option>`).join("")}</select>
      </label>
    </header>

    <div class="toolbar reveal" style="--d:1">
      <label class="search">
        ${icon("i-search")}
        <input id="of-q" type="search" placeholder="Titre, entreprise, ville, secteur…" autocomplete="off" aria-label="Filtrer les offres">
        <kbd>/</kbd>
      </label>
      <button type="button" class="btn btn--ghost filters-toggle" id="of-more" aria-expanded="false">${icon("i-filter")}Filtres<span class="filters-toggle__n" id="of-active-n" hidden></span></button>
      <div class="seg" id="of-verdict" role="radiogroup" aria-label="Filtrer par avis"></div>
      <div class="toolbar__row">
        <select id="of-zone" aria-label="Zone"><option value="">Toutes les zones</option></select>
        <select id="of-sector" aria-label="Secteur"><option value="">Tous les secteurs</option></select>
        <select id="of-source" aria-label="Source"><option value="">Toutes les sources</option></select>
        <label class="range" title="Score minimum">
          <span>Score ≥ <b id="of-min-val">0</b></span>
          <input id="of-min" type="range" min="0" max="95" step="5" value="0">
        </label>
        <label class="toggle"><input id="of-new" type="checkbox"><span class="toggle__ui"></span>Nouveautés</label>
        <label class="toggle" title="Ne garder qu'une offre par groupe « même intitulé, même lieu » (la mieux scorée)"><input id="of-dedup" type="checkbox"><span class="toggle__ui"></span>Masquer les doublons</label>
        <button type="button" class="btn btn--text" id="of-reset" hidden>Réinitialiser</button>
      </div>
    </div>

    <ol class="rows" id="of-rows" aria-label="Offres"></ol>
  `;

  $("#of-sort", root).addEventListener("change", (e) => { f.sort = e.target.value; renderList(); });
  $("#of-q", root).addEventListener("input", (e) => { f.q = e.target.value; cursor = -1; renderList(); });
  $("#of-zone", root).addEventListener("change", (e) => { f.zone = e.target.value; renderList(); });
  $("#of-sector", root).addEventListener("change", (e) => { f.sector = e.target.value; renderList(); });
  $("#of-source", root).addEventListener("change", (e) => { f.source = e.target.value; renderList(); });
  $("#of-min", root).addEventListener("input", (e) => { f.min = Number(e.target.value); $("#of-min-val", root).textContent = f.min; renderList(); });
  $("#of-new", root).addEventListener("change", (e) => { f.onlyNew = e.target.checked; renderList(); });
  $("#of-dedup", root).checked = dedup;
  $("#of-dedup", root).addEventListener("change", (e) => { dedup = e.target.checked; prefs.set("dedup", dedup); renderList(); });
  $("#of-more", root).addEventListener("click", (e) => {
    const bar = $(".toolbar", root);
    const open = bar.classList.toggle("is-expanded");
    e.currentTarget.setAttribute("aria-expanded", open);
  });
  $("#of-reset", root).addEventListener("click", () => { f = { ...DEFAULTS, sort: f.sort }; syncControls(); renderList(); });
  $("#of-verdict", root).addEventListener("click", (e) => {
    const b = e.target.closest("[data-v]");
    if (!b) return;
    f.verdict = b.dataset.v;
    renderList();
  });

  $("#of-rows", root).addEventListener("click", async (e) => {
    const row = e.target.closest(".row");
    if (!row) return;
    const id = Number(row.dataset.id);
    const vb = e.target.closest("[data-verdict]");
    if (vb) {
      e.stopPropagation();
      const o = store.byId.get(id);
      await decide(o, o.user_verdict === vb.dataset.verdict ? null : vb.dataset.verdict);
      return;
    }
    if (e.target.closest("a")) return;
    cursor = visible.findIndex((o) => o.id === id);
    ctx.openOffer(id, visible.map((o) => o.id));
  });
}

function populateSelects() {
  const zones = new Set(store.offers.map((o) => o.geography_zone).filter(Boolean));
  $("#of-zone", root).innerHTML = `<option value="">Toutes les zones</option>` + ZONE_ORDER.filter((z) => zones.has(z)).map((z) => `<option value="${z}">${ZONE_LABELS[z]}</option>`).join("");
  const sectors = [...new Set(store.offers.map((o) => o.sector).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr"));
  $("#of-sector", root).innerHTML = `<option value="">Tous les secteurs</option>` + sectors.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  const sources = [...new Set(store.offers.map((o) => o.source).filter(Boolean))];
  $("#of-source", root).innerHTML = `<option value="">Toutes les sources</option>` + sources.map((s) => `<option value="${s}">${SOURCE_LABELS[s] || s}</option>`).join("");
}

function syncControls() {
  $("#of-q", root).value = f.q;
  $("#of-zone", root).value = f.zone;
  $("#of-sector", root).value = f.sector;
  $("#of-source", root).value = f.source;
  $("#of-min", root).value = f.min;
  $("#of-min-val", root).textContent = f.min;
  $("#of-new", root).checked = f.onlyNew;
  $("#of-sort", root).value = f.sort;
}

function matches(o, ignoreVerdict = false) {
  if (f.zone && o.geography_zone !== f.zone) return false;
  if (f.sector && o.sector !== f.sector) return false;
  if (f.source && o.source !== f.source) return false;
  if (f.min && (o.score ?? -1) < f.min) return false;
  if (f.onlyNew && !isNew(o)) return false;
  if (f.q) {
    const hay = searchText(o);
    if (!fold(f.q).split(/\s+/).filter(Boolean).every((t) => hay.includes(t))) return false;
  }
  if (ignoreVerdict || !f.verdict) return true;
  if (f.verdict === "__pending__") return isTriageable(o) && !o.user_verdict;
  return o.user_verdict === f.verdict;
}

function renderSegments(base) {
  const counts = { "": base.length, __pending__: 0 };
  VERDICTS.forEach((v) => (counts[v] = 0));
  for (const o of base) {
    if (o.user_verdict) counts[o.user_verdict] += 1;
    else if (isTriageable(o)) counts.__pending__ += 1;
  }
  const seg = [["", "Toutes"], ["__pending__", "À trier"], ...VERDICTS.map((v) => [v, VERDICT_META[v].label])];
  $("#of-verdict", root).innerHTML = seg
    .map(([v, label]) => `<button type="button" role="radio" aria-checked="${f.verdict === v}" class="seg__btn ${v ? `seg__btn--${v}` : ""} ${f.verdict === v ? "is-on" : ""}" data-v="${v}">${v && VERDICT_META[v] ? icon(VERDICT_META[v].icon) : ""}${label}<span>${counts[v]}</span></button>`)
    .join("");
}

function rowHtml(o, i) {
  const d = dateLabel(o);
  return `
    <li class="row ${i === cursor ? "is-cursor" : ""} ${o.user_verdict ? `row--${o.user_verdict}` : ""} ${drawerOpenId() === o.id ? "is-open" : ""}" data-id="${o.id}" style="--i:${Math.min(i, 20)}">
      <div class="row__score">${scorePill(o.score)}</div>
      <div class="row__main">
        <h3 class="row__title">${highlight(titleOf(o))} ${twinBadge(o)}${newDot(o)}</h3>
        <p class="row__company">${highlight(companyOf(o))}</p>
        <p class="meta">${metaLine(o, { withSource: true })}</p>
      </div>
      <div class="row__chips chips">${staleChip(o)}${zoneChip(o.geography_zone)}${sectorChip(o.sector)}</div>
      <div class="row__date" title="${esc(d.title)}">${d.text}</div>
      <div class="row__verdict">${isTriageable(o) ? verdictControl(o, { compact: true }) : ""}</div>
    </li>`;
}

// Highlights query terms: matched on the accent-folded raw text, each
// segment escaped separately so a mark can never split an HTML entity.
function highlight(text) {
  const raw = String(text ?? "");
  const terms = fold(f.q).split(/\s+/).filter((t) => t.length > 1);
  if (!terms.length) return esc(raw);
  const folded = fold(raw);
  const marks = [];
  for (const t of terms) {
    let idx = folded.indexOf(t);
    while (idx !== -1) {
      marks.push([idx, idx + t.length]);
      idx = folded.indexOf(t, idx + t.length);
    }
  }
  if (!marks.length || folded.length !== raw.length) return esc(raw);
  marks.sort((a, b) => a[0] - b[0]);
  let out = "";
  let pos = 0;
  for (const [s, e] of marks) {
    if (s < pos) continue;
    out += esc(raw.slice(pos, s)) + `<mark>${esc(raw.slice(s, e))}</mark>`;
    pos = e;
  }
  return out + esc(raw.slice(pos));
}

// Keeps the best-scored offer of each duplicate group (ties: most recent),
// preserving the current sort order for the survivors.
function collapseTwins(list) {
  const keep = new Set();
  const seen = new Set();
  const ranked = [...list].sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || b.id - a.id);
  for (const o of ranked) {
    if (seen.has(o.id)) continue;
    keep.add(o.id);
    seen.add(o.id);
    (o._twins || []).forEach((t) => seen.add(t));
  }
  return list.filter((o) => keep.has(o.id));
}

function renderList() {
  const base = store.offers.filter((o) => matches(o, true));
  renderSegments(base);
  visible = base.filter((o) => matches(o)).sort(SORTS[f.sort].fn);
  if (dedup) visible = collapseTwins(visible);
  $("#of-count", root).textContent = visible.length === store.offers.length ? store.offers.length : `${visible.length} / ${store.offers.length}`;
  const dirty = JSON.stringify({ ...f, sort: "" }) !== JSON.stringify({ ...DEFAULTS, sort: "" });
  $("#of-reset", root).hidden = !dirty;
  const nActive = [f.zone, f.sector, f.source, f.min, f.onlyNew].filter(Boolean).length;
  $("#of-active-n", root).hidden = !nActive;
  $("#of-active-n", root).textContent = nActive;

  const list = $("#of-rows", root);
  if (!visible.length) {
    list.innerHTML = `
      <li class="empty-state">
        <svg viewBox="0 0 120 80" class="empty-state__art" aria-hidden="true"><rect x="18" y="14" width="60" height="44" rx="6"/><rect x="34" y="24" width="60" height="44" rx="6"/><circle cx="84" cy="56" r="12"/><path d="m93 65 10 10"/></svg>
        <h3>Aucune offre ne correspond.</h3>
        <p>${f.q ? `Rien pour « ${esc(f.q)} » avec ces filtres.` : "Élargis les filtres pour en voir davantage."}</p>
      </li>`;
    return;
  }
  if (cursor >= visible.length) cursor = visible.length - 1;
  list.innerHTML = visible.map(rowHtml).join("");
  // Staggered entrance only when arriving on the page — not on every
  // keystroke of the search box, where it reads as flicker.
  if (!animateNext) list.classList.add("no-anim");
  animateNext = false;
}

export function enter(params = {}) {
  if (!store.loaded) return;
  animateNext = true;
  $("#of-rows", root).classList.remove("no-anim");
  if (Object.keys(params).some((k) => k in DEFAULTS)) {
    f = { ...DEFAULTS, sort: f.sort };
    for (const [k, v] of Object.entries(params)) if (k in DEFAULTS) f[k] = k === "min" ? Number(v) : k === "onlyNew" ? v === "1" : v;
  }
  populateSelects();
  syncControls();
  renderList();
}

export const render = () => { if (store.loaded) { populateSelects(); syncControls(); renderList(); } };

export function onStoreChange(change) {
  if (change.type === "verdict") {
    const row = $(`.row[data-id="${change.id}"]`, root);
    // Re-render the whole list only when the change can move the row out of
    // the current verdict filter; otherwise patch the one row in place.
    if (row && !f.verdict) {
      const o = store.byId.get(change.id);
      const i = visible.findIndex((x) => x.id === change.id);
      row.outerHTML = rowHtml(o, i);
      renderSegments(store.offers.filter((x) => matches(x, true)));
    } else renderList();
  } else render();
}

function moveCursor(delta) {
  if (!visible.length) return;
  cursor = Math.max(0, Math.min(visible.length - 1, cursor + delta));
  $$(".row", root).forEach((r, i) => r.classList.toggle("is-cursor", i === cursor));
  const row = $$(".row", root)[cursor];
  row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (drawerOpenId() !== null) ctx.openOffer(visible[cursor].id, visible.map((o) => o.id), { replace: true });
}

export function onKey(e) {
  if (e.key === "/") {
    e.preventDefault();
    $("#of-q", root).focus();
    $("#of-q", root).select();
    return true;
  }
  if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); moveCursor(1); return true; }
  if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); moveCursor(-1); return true; }
  if (e.key === "Enter" && cursor >= 0 && drawerOpenId() === null) {
    ctx.openOffer(visible[cursor].id, visible.map((o) => o.id));
    return true;
  }
  const v = VERDICTS.find((x) => VERDICT_META[x].key === e.key);
  if (v) {
    const id = drawerOpenId() ?? visible[cursor]?.id;
    const o = id !== undefined ? store.byId.get(id) : null;
    if (o && isTriageable(o)) {
      decide(o, o.user_verdict === v ? null : v);
      return true;
    }
  }
  return false;
}

export function onSearchKey(e) {
  if (e.key === "Escape" || e.key === "Enter" || e.key === "ArrowDown") {
    e.target.blur();
    if (e.key !== "Escape" && visible.length) { cursor = -1; moveCursor(1); }
    return true;
  }
  return false;
}

export const summaryText = () => plural(visible.length, "offre", "offres");
