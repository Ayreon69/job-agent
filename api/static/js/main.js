// job·agent dashboard — entry point: hash router, masthead, keyboard,
// command palette, theme. Display layer only: every number comes straight
// from GET /offers and GET /offers/{id}; the only write is user_verdict.

import { store, loadOffers, subscribe, pending, prefs } from "./store.js";
import { esc, icon, fold, searchText, companyOf, locationOf, fmtDate, relTime, titleOf } from "./format.js";
import { $, $$, showError, reducedMotion, scorePill, newDot, decide } from "./ui.js";
import { initDrawer, openDrawer, closeDrawer, drawerOpenId, setDrawerContext, step, refreshDrawerVerdict } from "./drawer.js";
import * as brief from "./views/brief.js";
import * as offres from "./views/offres.js";
import * as trier from "./views/trier.js";
import * as selection from "./views/selection.js";
import * as coulisses from "./views/coulisses.js";

const VIEWS = { brief, offres, trier, selection, coulisses };
const PATHS = { "": "brief", offres: "offres", trier: "trier", selection: "selection", coulisses: "coulisses" };
const TITLES = { brief: "Brief", offres: "Offres", trier: "Trier", selection: "Sélection", coulisses: "Coulisses" };

let current = null;
let currentParams = "";

// ---------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const route = PATHS[path.replace(/\/$/, "")] || "brief";
  const params = Object.fromEntries(new URLSearchParams(query));
  return { route, params };
}

function buildHash(route, params = {}) {
  const path = Object.keys(PATHS).find((k) => PATHS[k] === route) ?? "";
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();
  return `#/${path}${q ? `?${q}` : ""}`;
}

function setHash(hash, replace = false) {
  if (location.hash === hash) return;
  if (replace) {
    history.replaceState(null, "", hash);
    onRoute();
  } else location.hash = hash;
}

const ctx = {
  go(route, params = {}) {
    setHash(buildHash(route, params));
  },
  openOffer(id, contextIds = [], { replace = false } = {}) {
    setDrawerContext(contextIds.length ? contextIds : [id]);
    const { route, params } = parseHash();
    setHash(buildHash(route, { ...params, offre: id }), replace || drawerOpenId() !== null);
  },
  updateBadge,
};

function navigateDrawer(id, { replace = false } = {}) {
  const { route, params } = parseHash();
  if (id === null) {
    delete params.offre;
    setHash(buildHash(route, params), true);
  } else setHash(buildHash(route, { ...params, offre: id }), replace);
}

function switchView(route, params) {
  const apply = () => {
    $$(".view").forEach((v) => (v.hidden = v.dataset.view !== route));
    current = route;
    VIEWS[route].enter?.(params);
    if (!VIEWS[route].enter) VIEWS[route].render?.();
    document.title = `${TITLES[route]} · job·agent`;
    $$(".nav__link").forEach((a) => a.classList.toggle("is-active", a.dataset.route === route));
    moveInk();
    window.scrollTo({ top: 0, behavior: "instant" });
  };
  if (current) withTransition(apply);
  else apply();
}

// View Transitions are a progressive enhancement: skipped when unsupported,
// in background tabs, or with reduced motion. A transition interrupted by
// the next navigation rejects its promises — expected, so swallowed (the
// DOM update itself still runs either way).
function withTransition(update, { className } = {}) {
  if (!document.startViewTransition || reducedMotion() || document.visibilityState !== "visible") {
    update();
    return;
  }
  if (className) document.documentElement.classList.add(className);
  const t = document.startViewTransition(update);
  t.ready.catch(() => {});
  t.updateCallbackDone.catch(() => {});
  t.finished.catch(() => {}).finally(() => className && document.documentElement.classList.remove(className));
}

function onRoute() {
  const { route, params } = parseHash();
  const { offre, ...rest } = params;
  const restKey = JSON.stringify(rest);
  if (route !== current) switchView(route, rest);
  else if (restKey !== currentParams) VIEWS[route].enter?.(rest);
  currentParams = restKey;

  if (offre && store.loaded) {
    const id = Number(offre);
    if (store.byId.has(id)) openDrawer(id);
    else closeDrawer();
  } else closeDrawer();
}

// ---------------------------------------------------------------------
// Masthead
// ---------------------------------------------------------------------

function moveInk() {
  const active = $(".nav__link.is-active");
  const ink = $(".nav__ink");
  if (!active || !ink) return;
  ink.style.width = `${active.offsetWidth}px`;
  ink.style.transform = `translateX(${active.offsetLeft}px)`;
}

function updateBadge() {
  const n = pending().length;
  const b = $("#nav-pending");
  b.hidden = n === 0;
  b.textContent = n > 99 ? "99+" : n;
}

function dateline() {
  const now = new Date();
  const first = store.offers.reduce((m, o) => (o._firstSeen && (!m || o._firstSeen < m) ? o._firstSeen : m), null);
  const edition = first ? Math.floor((now - first) / 86400000) + 1 : null;
  const hours = store.lastRun ? (now - store.lastRun) / 3600000 : Infinity;
  const fresh = hours < 30 ? "ok" : hours < 72 ? "late" : "stale";
  const freshLabel = { ok: "pipeline à jour", late: "pipeline en retard", stale: "pipeline à l'arrêt ?" }[fresh];
  $("#dateline").innerHTML = `
    <span>${fmtDate(now, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</span>
    ${edition ? `<span class="dateline__sep dateline__edition">·</span><span class="dateline__edition" title="Jours depuis la première offre enregistrée">Édition n° ${edition}</span>` : ""}
    <span class="dateline__sep">·</span>
    <span class="pulse pulse--${fresh}" title="${store.lastRun ? `Dernière activité du scraper : ${fmtDate(store.lastRun, { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}` : ""}"><i></i>${freshLabel}${store.lastRun ? ` · ${relTime(store.lastRun, now)}` : ""}</span>`;
}

// ---------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------

function effectiveTheme() {
  const forced = document.documentElement.dataset.theme;
  if (forced) return forced;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function toggleTheme() {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  const apply = () => {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("ja-theme", next);
    } catch {}
  };
  withTransition(apply, { className: "theme-swap" });
}

// ---------------------------------------------------------------------
// Command palette
// ---------------------------------------------------------------------

const COMMANDS = [
  { label: "Aller au brief", hint: "g b", icon: "i-brief", run: () => ctx.go("brief") },
  { label: "Aller aux offres", hint: "g o", icon: "i-list", run: () => ctx.go("offres") },
  { label: "Trier les offres en attente", hint: "g t", icon: "i-cards", run: () => ctx.go("trier") },
  { label: "Ouvrir ma sélection", hint: "g s", icon: "i-board", run: () => ctx.go("selection") },
  { label: "Voir les coulisses du pipeline", hint: "g c", icon: "i-flow", run: () => ctx.go("coulisses") },
  { label: "Offres à 80 et plus", hint: "", icon: "i-sparkle", run: () => ctx.go("offres", { min: 80 }) },
  { label: "Nouveautés depuis ma dernière visite", hint: "", icon: "i-clock", run: () => ctx.go("offres", { onlyNew: "1", sort: "score" }) },
  { label: "Changer de thème (clair / sombre)", hint: "", icon: "i-moon", run: toggleTheme },
  { label: "Raccourcis clavier", hint: "?", icon: "i-keyboard", run: () => openHelp() },
];

let palItems = [];
let palIndex = 0;

function openPalette() {
  const p = $("#palette");
  p.hidden = false;
  void p.offsetWidth; // commit the hidden->shown frame so the fade-in runs
  p.classList.add("is-open");
  const input = $("#palette-input");
  input.value = "";
  renderPalette("");
  input.focus();
}

function closePalette() {
  const p = $("#palette");
  p.classList.remove("is-open");
  setTimeout(() => (p.hidden = true), 150);
}

function renderPalette(q) {
  const terms = fold(q).split(/\s+/).filter(Boolean);
  const cmds = COMMANDS.filter((c) => terms.every((t) => fold(c.label).includes(t)));
  const offers = terms.length
    ? store.offers.filter((o) => {
        const h = searchText(o);
        return terms.every((t) => h.includes(t));
      })
    : store.offers.filter((o) => !o.user_verdict).sort((a, b) => (b._firstSeen ?? 0) - (a._firstSeen ?? 0));
  const topOffers = offers.sort((a, b) => (terms.length ? (b.score ?? -1) - (a.score ?? -1) : 0)).slice(0, 7);

  palItems = [
    ...topOffers.map((o) => ({ kind: "offer", o, run: () => ctx.openOffer(o.id, offers.map((x) => x.id)) })),
    ...cmds.map((c) => ({ kind: "cmd", c, run: c.run })),
  ];
  if (!terms.length) palItems = [...palItems.filter((i) => i.kind === "cmd").slice(0, 5), ...palItems.filter((i) => i.kind === "offer").slice(0, 5)];
  palIndex = 0;

  const list = $("#palette-list");
  if (!palItems.length) {
    list.innerHTML = `<li class="palette__empty">Aucun résultat pour « ${esc(q)} ».</li>`;
    return;
  }
  let lastKind = null;
  list.innerHTML = palItems
    .map((it, i) => {
      const head = it.kind !== lastKind ? `<li class="palette__group">${it.kind === "offer" ? (terms.length ? `Offres · ${offers.length}` : "Dernières offres repérées") : "Commandes"}</li>` : "";
      lastKind = it.kind;
      if (it.kind === "offer") {
        return `${head}<li class="palette__item" role="option" data-i="${i}">${scorePill(it.o.score)}<span class="palette__main"><b>${esc(titleOf(it.o))}</b><small>${esc(companyOf(it.o))}${locationOf(it.o) ? ` · ${esc(locationOf(it.o))}` : ""}</small></span>${newDot(it.o)}</li>`;
      }
      return `${head}<li class="palette__item" role="option" data-i="${i}">${icon(it.c.icon, "palette__icon")}<span class="palette__main"><b>${esc(it.c.label)}</b></span>${it.c.hint ? `<kbd>${it.c.hint}</kbd>` : ""}</li>`;
    })
    .join("");
  highlightPalette();
}

function highlightPalette() {
  $$(".palette__item").forEach((el) => {
    const on = Number(el.dataset.i) === palIndex;
    el.classList.toggle("is-on", on);
    el.setAttribute("aria-selected", on);
    if (on) el.scrollIntoView({ block: "nearest" });
  });
}

function runPalette(i) {
  const it = palItems[i];
  if (!it) return;
  closePalette();
  it.run();
}

function wirePalette() {
  $("#open-palette").onclick = openPalette;
  $("#palette").addEventListener("click", (e) => {
    if (e.target.id === "palette") return closePalette();
    const it = e.target.closest(".palette__item");
    if (it) runPalette(Number(it.dataset.i));
  });
  $("#palette-list").addEventListener("pointermove", (e) => {
    const it = e.target.closest(".palette__item");
    if (it && Number(it.dataset.i) !== palIndex) {
      palIndex = Number(it.dataset.i);
      highlightPalette();
    }
  });
  $("#palette-input").addEventListener("input", (e) => renderPalette(e.target.value));
  $("#palette-input").addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); palIndex = Math.min(palItems.length - 1, palIndex + 1); highlightPalette(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); palIndex = Math.max(0, palIndex - 1); highlightPalette(); }
    else if (e.key === "Enter") { e.preventDefault(); runPalette(palIndex); }
    else if (e.key === "Escape") { e.preventDefault(); closePalette(); }
  });
}

// ---------------------------------------------------------------------
// Help overlay
// ---------------------------------------------------------------------

function openHelp() {
  const h = $("#help");
  h.hidden = false;
  void h.offsetWidth;
  h.classList.add("is-open");
  $("[data-close-help]", h).focus();
}

function closeHelp() {
  const h = $("#help");
  h.classList.remove("is-open");
  setTimeout(() => (h.hidden = true), 150);
}

// ---------------------------------------------------------------------
// Keyboard
// ---------------------------------------------------------------------

let chord = null; // "g" pressed, waiting for the destination key

function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    $("#palette").hidden ? openPalette() : closePalette();
    return;
  }
  if (!$("#palette").hidden) return; // the palette input handles its own keys
  if (!$("#help").hidden) {
    if (e.key === "Escape" || e.key === "?") closeHelp();
    return;
  }
  const typing = e.target.closest?.("input, textarea, select, [contenteditable]");
  if (typing) {
    if (e.target.id === "of-q") offres.onSearchKey(e);
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;

  if (chord) {
    const dest = { b: "brief", o: "offres", t: "trier", s: "selection", c: "coulisses" }[e.key];
    chord = null;
    if (dest) ctx.go(dest);
    return;
  }

  if (drawerOpenId() !== null) {
    const o = store.byId.get(drawerOpenId());
    if (e.key === "Escape") return navigateDrawer(null);
    if (["j", "ArrowDown", "ArrowRight"].includes(e.key)) { e.preventDefault(); return step(1); }
    if (["k", "ArrowUp", "ArrowLeft"].includes(e.key)) { e.preventDefault(); return step(-1); }
    const v = { 1: "interessante", 2: "peut_etre", 3: "pas_interessante" }[e.key];
    if (v && o) return decide(o, o.user_verdict === v ? null : v);
    if (e.key === "?") return openHelp();
    return;
  }

  if (e.key === "?") return openHelp();
  if (e.key === "g") {
    chord = true;
    setTimeout(() => (chord = null), 1200);
    return;
  }
  VIEWS[current]?.onKey?.(e);
}

// ---------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------

// Shown in whichever view the page was opened on until GET /offers answers.
// Views that build their own chrome at mount (offres, trier) get it layered
// on top and removed once data arrives.
function loadingSkeleton(route) {
  const view = $(`.view[data-view="${route}"]`);
  const el = document.createElement("section");
  el.className = "boot-skeleton";
  el.innerHTML = `
    <p class="kicker">Chargement…</p>
    <div class="skeleton skeleton--hero"><i></i><i></i></div>
    <p class="muted small">Sur la démo Render, une instance endormie met jusqu'à une minute à se réveiller.</p>`;
  view.prepend(el);
  view.classList.add("is-booting");
}

async function boot() {
  for (const [name, view] of Object.entries(VIEWS)) view.mount($(`.view[data-view="${name}"]`), ctx);
  initDrawer({ onNavigate: (id, opts) => navigateDrawer(id, opts) });
  wirePalette();
  $("#toggle-theme").onclick = toggleTheme;
  $("#open-help").onclick = openHelp;
  $("#help").addEventListener("click", (e) => {
    if (e.target.id === "help" || e.target.closest("[data-close-help]")) closeHelp();
  });
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("hashchange", onRoute);
  window.addEventListener("resize", moveInk);
  document.fonts?.ready.then(moveInk);

  subscribe((change) => {
    updateBadge();
    if (change.type === "verdict") refreshDrawerVerdict();
    for (const [name, view] of Object.entries(VIEWS)) {
      // Hidden views refresh lazily when entered; only the visible one
      // (and the deck, which tracks removals) reacts immediately.
      if (name === current || name === "trier") view.onStoreChange?.(change);
    }
  });

  onRoute();
  loadingSkeleton(current);

  try {
    await loadOffers();
  } catch (err) {
    showError(`Impossible de charger les offres depuis l'API (${err.message}). Le serveur FastAPI est-il démarré ?`);
    return;
  }
  $$(".boot-skeleton").forEach((n) => n.remove());
  $$(".is-booting").forEach((n) => n.classList.remove("is-booting"));
  document.body.classList.add("is-loaded");
  dateline();
  updateBadge();
  const { route, params } = parseHash();
  const { offre, ...rest } = params;
  VIEWS[route].enter ? VIEWS[route].enter(rest) : VIEWS[route].render();
  if (offre) onRoute();
  setInterval(dateline, 60000);
  showTipOnce();
}

// One-time hint about the keyboard layer, which is otherwise invisible.
function showTipOnce() {
  if (prefs.get("tip-seen")) return;
  const tip = document.createElement("aside");
  tip.className = "tip";
  tip.setAttribute("role", "note");
  tip.innerHTML = `
    <h4>${icon("i-keyboard")}Tout se fait au clavier</h4>
    <p><kbd>Ctrl</kbd> <kbd>K</kbd> pour chercher une offre, <kbd>g</kbd> puis <kbd>t</kbd> pour trier, <kbd>←</kbd> <kbd>↑</kbd> <kbd>→</kbd> pour décider, <kbd>?</kbd> pour tout le reste.</p>
    <button type="button" class="btn btn--ghost">Compris</button>`;
  document.body.appendChild(tip);
  tip.querySelector("button").onclick = () => {
    prefs.set("tip-seen", true);
    tip.remove();
  };
}

boot();

