// Offer detail drawer. Opened via the URL (#/<view>?offre=<id>) so the
// browser's back button closes it and any offer can be linked directly.

import { esc, icon, scoreRing, scoreTier, TIER_LABELS, ZONE_LABELS, SOURCE_LABELS, STATUS_LABELS, companyOf, locationOf, cleanContract, cleanSalary, cleanExperience, parsePublished, parseSqlUtc, fmtDate, relDay, descriptionHtml, plural, titleOf } from "./format.js";
import { store, getDetail, isNew } from "./store.js";
import { $, decide, verdictControl, zoneChip, sectorChip, reducedMotion } from "./ui.js";

let context = []; // ordered offer ids the opening view was showing (prev/next)
let currentId = null;
let navigate = () => {};
let lastFocus = null;

export function initDrawer({ onNavigate }) {
  navigate = onNavigate;
  $("#drawer-scrim").addEventListener("click", () => navigate(null));
  $("#drawer").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-drawer-action]");
    if (!btn) return;
    const action = btn.dataset.drawerAction;
    if (action === "close") navigate(null);
    if (action === "prev") step(-1);
    if (action === "next") step(1);
  });
  $("#drawer").addEventListener("click", (e) => {
    const twin = e.target.closest("[data-twin]");
    if (!twin) return;
    e.preventDefault();
    navigate(Number(twin.dataset.twin), { replace: true });
  });
  $("#drawer").addEventListener("click", async (e) => {
    const vb = e.target.closest(".verdict-control [data-verdict]");
    if (!vb || currentId === null) return;
    const o = store.byId.get(currentId);
    const next = o.user_verdict === vb.dataset.verdict ? null : vb.dataset.verdict;
    await decide(o, next);
  });
}

export function setDrawerContext(ids) {
  context = ids;
}

export const drawerOpenId = () => currentId;

export function step(delta) {
  if (currentId === null) return;
  const idx = context.indexOf(currentId);
  if (idx === -1) return;
  const next = context[idx + delta];
  if (next !== undefined) navigate(next, { replace: true });
}

export function refreshDrawerVerdict() {
  if (currentId === null) return;
  const o = store.byId.get(currentId);
  const host = $("#drawer .drawer__verdict");
  if (o && host) host.innerHTML = verdictControl(o);
}

export async function openDrawer(id) {
  const drawer = $("#drawer");
  const scrim = $("#drawer-scrim");
  const wasOpen = currentId !== null;
  currentId = id;
  // Opened from a shared link (no list behind it): browse by score.
  if (!context.includes(id)) context = [...store.offers].sort((a, b) => (b.score ?? -1) - (a.score ?? -1)).map((o) => o.id);
  if (!wasOpen) lastFocus = document.activeElement;

  const summary = store.byId.get(id);
  const body = $("#drawer-body");
  body.innerHTML = summary ? shell(summary, null) : '<p class="loading">Chargement…</p>';
  drawer.hidden = false;
  scrim.hidden = false;
  document.body.classList.add("has-drawer");
  void drawer.offsetWidth; // commit the off-screen position so the slide-in transitions
  drawer.classList.add("is-open");
  scrim.classList.add("is-open");
  body.scrollTop = 0;
  if (!wasOpen) setTimeout(() => $(".drawer__close", drawer)?.focus({ preventScroll: true }), reducedMotion() ? 0 : 220);

  try {
    const detail = await getDetail(id);
    if (currentId !== id) return;
    body.innerHTML = shell(store.byId.get(id) || detail, detail);
  } catch (err) {
    if (currentId !== id) return;
    $(".drawer__desc", body).innerHTML = `<p class="muted">Détail indisponible (${esc(err.message)}).</p>`;
  }
}

export function closeDrawer() {
  if (currentId === null) return;
  currentId = null;
  const drawer = $("#drawer");
  const scrim = $("#drawer-scrim");
  drawer.classList.remove("is-open");
  scrim.classList.remove("is-open");
  document.body.classList.remove("has-drawer");
  setTimeout(() => {
    if (currentId === null) {
      drawer.hidden = true;
      scrim.hidden = true;
    }
  }, reducedMotion() ? 0 : 320);
  lastFocus?.focus?.({ preventScroll: true });
}

function fact(iconId, label, value) {
  if (!value) return "";
  return `<div class="fact">${icon(iconId)}<dt>${label}</dt><dd>${value}</dd></div>`;
}

function analysisBlock(o, d) {
  const gaps = d?.gaps ?? [];
  const matches = d?.matches ?? [];
  const uncertain = d?.uncertain_flags ?? [];
  const gapsCount = d?.gaps_count ?? o.gaps_count;
  const uncertainCount = d?.uncertain_count ?? o.uncertain_count;
  const hasLists = matches.length || gaps.length || uncertain.length;

  if (o.status === "nouveau") return `<p class="muted">Pas encore analysée par l'orchestrateur — elle le sera au prochain passage du pipeline.</p>`;
  if (o.status === "echec") return `<p class="muted">Le pipeline a échoué sur cette offre ; elle sera retentée au prochain passage.</p>`;

  const counters = `
    <div class="counters">
      <div class="counter counter--gap"><b>${gapsCount ?? "–"}</b><span>${gapsCount === 1 ? "écart confirmé" : "écarts confirmés"}</span></div>
      <div class="counter counter--unc"><b>${uncertainCount ?? "–"}</b><span>${uncertainCount === 1 ? "point incertain" : "points incertains"}</span></div>
      ${matches.length ? `<div class="counter counter--match"><b>${matches.length}</b><span>points forts</span></div>` : ""}
    </div>`;

  if (!hasLists) {
    return `${counters}
      <p class="note">${icon("i-lock")}<span>Le détail de l'analyse (points forts, écarts, passages du profil utilisés) reste privé : il est produit par le pipeline mais n'est pas publié. Seuls les compteurs le sont.</span></p>`;
  }
  const list = (items, render) => (items.length ? `<ul>${items.map(render).join("")}</ul>` : '<p class="muted">Aucun.</p>');
  return `${counters}
    <div class="analysis-cols">
      <section><h4 class="tone-yes">Points forts</h4>${list(matches, (m) => `<li><b>${esc(m.skill)}</b><span>${esc(m.matched_chunk_summary)}</span></li>`)}</section>
      <section><h4 class="tone-no">Écarts confirmés</h4>${list(gaps, (g) => `<li><b>${esc(g.skill)}</b><span>${esc(g.note)}</span></li>`)}</section>
      ${uncertain.length ? `<section><h4 class="tone-maybe">Incertains</h4>${list(uncertain, (f) => `<li>${esc(f)}</li>`)}</section>` : ""}
    </div>`;
}

function shell(o, d) {
  const idx = context.indexOf(o.id);
  const pub = parsePublished(o.published_at);
  const first = parseSqlUtc(o.first_seen_at);
  const last = parseSqlUtc(d?.last_seen_at ?? o.last_seen_at);
  const tier = scoreTier(o.score);
  const url = d?.url || o.url;

  return `
    <header class="drawer__top">
      <div class="drawer__nav">
        <button type="button" class="icon-btn" data-drawer-action="prev" ${idx > 0 ? "" : "disabled"} aria-label="Offre précédente (k)">${icon("i-left")}</button>
        <span class="drawer__pos">${idx >= 0 ? `${idx + 1} / ${context.length}` : ""}</span>
        <button type="button" class="icon-btn" data-drawer-action="next" ${idx >= 0 && idx < context.length - 1 ? "" : "disabled"} aria-label="Offre suivante (j)">${icon("i-right")}</button>
      </div>
      <button type="button" class="icon-btn drawer__close" data-drawer-action="close" aria-label="Fermer (Échap)">${icon("i-x")}</button>
    </header>

    <div class="drawer__hero drawer__hero--${tier}">
      <div class="drawer__ring">${scoreRing(o.score, 92, 7)}<span class="drawer__tier">${TIER_LABELS[tier]}</span></div>
      <div class="drawer__titles">
        <p class="drawer__company">${esc(companyOf(o))}${isNew(o) ? ' <span class="new-dot">Nouveau</span>' : ""}</p>
        <h2 id="drawer-title">${esc(titleOf(o))}</h2>
        <div class="chips">${zoneChip(o.geography_zone)}${sectorChip(o.sector)}${o.status === "a_valider_geographie" ? `<span class="chip chip--warn">${icon("i-alert")}Géographie à valider</span>` : ""}</div>
      </div>
    </div>

    <div class="drawer__actions">
      <div class="drawer__verdict">${verdictControl(o)}</div>
      ${url ? `<a class="btn btn--primary" href="${esc(url)}" target="_blank" rel="noopener">Voir l'offre sur ${esc(SOURCE_LABELS[o.source] || "le site source")} ${icon("i-external")}</a>` : ""}
    </div>

    <dl class="facts">
      ${fact("i-pin", "Lieu", esc(locationOf(o) || "—"))}
      ${fact("i-case", "Contrat", esc(cleanContract(o.contract_type) || ""))}
      ${fact("i-coins", "Salaire", esc(cleanSalary(o.salary) || ""))}
      ${fact("i-ladder", "Expérience", esc(cleanExperience(o.experience) || ""))}
      ${fact("i-clock", "Publiée", pub ? `${fmtDate(pub)} <small>(${relDay(pub)})</small>` : "")}
      ${fact("i-sparkle", "Repérée", first ? `${fmtDate(first)} <small>(${relDay(first)})</small>` : "")}
      ${fact("i-search", "Revue en ligne", last ? `${fmtDate(last)} <small>(${relDay(last)})</small>` : "")}
      ${fact("i-source", "Source", esc(SOURCE_LABELS[o.source] || o.source || ""))}
    </dl>

    ${o._twins?.length ? `
    <p class="note note--twin">${icon("i-cards")}<span>Probable doublon : même intitulé et même lieu que ${o._twins.map((t) => `<a href="#" data-twin="${t}">#${t}</a>`).join(", ")}. Un seul avis suffit sans doute.</span></p>` : ""}

    <section class="drawer__section">
      <h3>Analyse du pipeline <small>${esc(STATUS_LABELS[o.status] || o.status)}</small></h3>
      ${analysisBlock(o, d)}
    </section>

    <section class="drawer__section">
      <h3>L'offre</h3>
      <div class="drawer__desc prose">${d ? descriptionHtml(d.description) : '<div class="skeleton"><i></i><i></i><i></i><i></i></div>'}</div>
    </section>
  `;
}
