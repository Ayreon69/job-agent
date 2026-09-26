// "Le brief" — the landing page: what changed since the last visit, the best
// offers still waiting for a decision, and the shape of the market.

import { esc, icon, plural, scoreRing, companyOf, excerpt, fmtTime, relTime, VERDICT_META, titleOf } from "../format.js";
import { store, pending, triageable, isNew, getDetail } from "../store.js";
import { $, $$, metaLine, zoneChip, sectorChip, newDot, dateLabel, countUp, wireTooltips, scorePill } from "../ui.js";
import { arrivalsChart, scoreHistogram, zoneBars, sectorBars, salaryStrips, tierLegend, radar } from "../charts.js";

let root;
let ctx;

export function mount(el, context) {
  root = el;
  ctx = context;
  wireTooltips(root);
  root.addEventListener("click", (e) => {
    const card = e.target.closest("[data-open]");
    if (card) return ctx.openOffer(Number(card.dataset.open), idsOf(root, "[data-open]"));
    const f = e.target.closest("[data-filter-kind]");
    if (f) return ctx.go("offres", { [f.dataset.filterKind]: f.dataset.filterValue });
    const dot = e.target.closest("[data-offer-id]");
    if (dot) return ctx.openOffer(Number(dot.dataset.offerId), []);
  });
}

const idsOf = (el, sel) => [...new Set($$(sel, el).map((n) => Number(n.dataset.open)))];

function greeting(now = new Date()) {
  const h = now.getHours();
  if (h < 5) return "Bonne nuit";
  if (h < 12) return "Bonjour";
  if (h < 18) return "Bon après-midi";
  return "Bonsoir";
}

function headline(fresh, freshHot) {
  if (fresh.length === 0) return `Rien de neuf depuis ta dernière visite. <em>Le tri, lui, peut avancer.</em>`;
  const lead = `${plural(fresh.length, "nouvelle offre", "nouvelles offres")} depuis ta dernière visite.`;
  if (freshHot.length === 0) return `${lead} <em>Aucune ne dépasse 80 — journée calme.</em>`;
  if (freshHot.length === 1) return `${lead} <em>Une seule dépasse 80.</em>`;
  return `${lead} <em>${freshHot.length} dépassent 80.</em>`;
}

// Picks: best untriaged offers, new ones first when they're competitive —
// ranked by the pipeline's raw score, nothing re-weighted.
function picks() {
  const waiting = pending().filter((o) => o.score !== null && o.score !== undefined);
  const fresh = waiting.filter(isNew).sort((a, b) => b.score - a.score);
  const rest = waiting.filter((o) => !isNew(o)).sort((a, b) => b.score - a.score);
  const out = [...fresh.filter((o) => o.score >= 75).slice(0, 3)];
  for (const o of rest) {
    if (out.length >= 5) break;
    out.push(o);
  }
  for (const o of fresh) {
    if (out.length >= 5) break;
    if (!out.includes(o)) out.push(o);
  }
  return out.sort((a, b) => b.score - a.score).slice(0, 5);
}

function pickCard(o, i) {
  const d = dateLabel(o);
  return `
    <article class="pick ${i === 0 ? "pick--lead" : ""}" data-open="${o.id}" tabindex="0" style="--i:${i}">
      <div class="pick__score">${scoreRing(o.score, i === 0 ? 84 : 56, i === 0 ? 7 : 5)}</div>
      <div class="pick__body">
        <p class="pick__company">${esc(companyOf(o))} ${newDot(o)}</p>
        <h3 class="pick__title">${esc(titleOf(o))}</h3>
        <p class="meta">${metaLine(o)}</p>
        ${i === 0 ? `<p class="pick__excerpt" data-excerpt-for="${o.id}"><span class="skeleton-line"></span><span class="skeleton-line"></span></p>` : ""}
        <div class="chips">${zoneChip(o.geography_zone)}${sectorChip(o.sector)}<span class="chip chip--ghost" title="${esc(d.title)}">${icon("i-clock")}${d.text}</span></div>
      </div>
      <span class="pick__go">${icon("i-arrow")}</span>
    </article>`;
}

export function render() {
  if (!store.loaded) return;
  const now = new Date();
  const all = store.offers;
  const tri = triageable();
  const waiting = pending();
  const fresh = all.filter(isNew);
  const freshHot = fresh.filter((o) => (o.score ?? 0) >= 80);
  const yes = tri.filter((o) => o.user_verdict === "interessante");
  const maybe = tri.filter((o) => o.user_verdict === "peut_etre");
  const scores = all.map((o) => o.score).filter((s) => s !== null && s !== undefined).sort((a, b) => a - b);
  const med = scores.length ? scores[Math.floor(scores.length / 2)] : null;
  const top = picks();
  const sources = new Set(all.map((o) => o.source).filter(Boolean)).size;

  root.innerHTML = `
    <section class="hero-wrap">
    <div class="hero reveal">
      <p class="kicker">${greeting(now)} · le brief</p>
      <h1 class="hero__title">${headline(fresh, freshHot)}</h1>
      <p class="hero__lede">
        ${store.lastRun ? `Dernier passage du pipeline <b>${relTime(store.lastRun, now)}</b> (${fmtTime(store.lastRun)}), sur ${plural(sources, "source", "sources")}.` : ""}
        ${waiting.length ? `<b>${waiting.length}</b> ${waiting.length > 1 ? "offres attendent" : "offre attend"} ton avis.` : "Tout est trié."}
      </p>
      <div class="hero__cta">
        ${waiting.length ? `<a class="btn btn--primary btn--lg" href="#/trier">${icon("i-cards")}Trier ${fresh.filter((o) => !o.user_verdict).length ? "les nouveautés" : "les offres en attente"}<span class="btn__count">${fresh.filter((o) => !o.user_verdict).length || waiting.length}</span></a>` : ""}
        <a class="btn btn--ghost btn--lg" href="#/offres">Parcourir les ${all.length} offres ${icon("i-arrow")}</a>
      </div>
    </div>
    <figure class="radar-wrap reveal" style="--d:2">
      ${radar(waiting, isNew)}
      <figcaption>Le radar · ${waiting.length} offres en attente.<br>Au centre, les meilleurs scores ; <span class="tone-accent">en surbrillance</span>, les nouvelles.</figcaption>
    </figure>
    </section>

    <section class="ribbon reveal" style="--d:1">
      <div class="ribbon__cell"><b data-count="${all.length}">0</b><span>offres suivies</span></div>
      <div class="ribbon__cell"><b data-count="${fresh.length}">0</b><span>nouvelles</span></div>
      <div class="ribbon__cell"><b data-count="${waiting.length}">0</b><span>à trier</span></div>
      <div class="ribbon__cell ribbon__cell--yes"><b data-count="${yes.length}">0</b><span>intéressantes</span></div>
      <div class="ribbon__cell ribbon__cell--maybe"><b data-count="${maybe.length}">0</b><span>peut-être</span></div>
      <div class="ribbon__cell"><b data-count="${med ?? 0}">0</b><span>score médian</span></div>
    </section>

    ${top.length ? `
    <section class="block reveal" style="--d:2">
      <header class="block__head"><span class="block__num">01</span><h2>À la une</h2><p>Les meilleures offres qui attendent encore ta décision, classées par score du pipeline.</p></header>
      <div class="picks">${top.map(pickCard).join("")}</div>
    </section>` : ""}

    <section class="block reveal" style="--d:3">
      <header class="block__head"><span class="block__num">02</span><h2>Le marché en chiffres</h2><p>Survole les graphiques pour le détail ; clique une zone ou un secteur pour filtrer les offres.</p></header>
      <div class="panels">
        <figure class="panel panel--wide">
          <figcaption><h3>Offres repérées par jour</h3><span class="legend"><span class="legend__item"><i class="legend__sw ch-total-sw"></i>toutes</span><span class="legend__item"><i class="legend__sw ch-tier--hot"></i>score 80+</span></span></figcaption>
          ${arrivalsChart(all, 30, now)}
        </figure>
        <figure class="panel panel--wide">
          <figcaption><h3>Distribution des scores</h3><span class="legend">${tierLegend()}<span class="legend__item"><i class="legend__dot"></i>tes « intéressantes »</span><span class="legend__item"><i class="legend__med"></i>médiane ${med ?? "–"}</span></span></figcaption>
          ${scoreHistogram(all)}
        </figure>
        <figure class="panel">
          <figcaption><h3>Par zone</h3><span class="legend">nb · score moyen</span></figcaption>
          ${zoneBars(all)}
        </figure>
        <figure class="panel">
          <figcaption><h3>Par secteur</h3><span class="legend">7 premiers · score moyen</span></figcaption>
          ${sectorBars(all)}
        </figure>
        <figure class="panel panel--full">
          <figcaption><h3>Salaires annoncés</h3><span class="legend">une pastille par offre qui affiche un salaire · couleur = score</span></figcaption>
          <div class="salaries">${salaryStrips(all)}</div>
        </figure>
      </div>
    </section>

    ${yes.length || maybe.length ? `
    <section class="block reveal" style="--d:4">
      <header class="block__head"><span class="block__num">03</span><h2>Ta sélection</h2><p>Ce que tu as gardé. Rien n'est envoyé : la candidature reste ton geste.</p></header>
      <ul class="shortlist">
        ${[...yes, ...maybe].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 8).map((o) => `
          <li data-open="${o.id}" tabindex="0">
            ${scorePill(o.score)}
            <span class="shortlist__title">${esc(titleOf(o))}</span>
            <span class="shortlist__company">${esc(companyOf(o))}</span>
            <span class="verdict-badge verdict-badge--${o.user_verdict}">${icon(VERDICT_META[o.user_verdict].icon)}${VERDICT_META[o.user_verdict].label}</span>
          </li>`).join("")}
      </ul>
      <a class="link-more" href="#/selection">Ouvrir le tableau de sélection ${icon("i-arrow")}</a>
    </section>` : ""}
  `;

  $$("[data-count]", root).forEach((el) => countUp(el, Number(el.dataset.count)));

  const lead = top[0];
  if (lead) {
    getDetail(lead.id)
      .then((d) => {
        const p = $(`[data-excerpt-for="${lead.id}"]`, root);
        if (p) p.textContent = excerpt(d.description, 260) || "";
      })
      .catch(() => {});
  }
}

export function onKey(e) {
  if (e.key === "Enter" && document.activeElement?.dataset?.open) {
    ctx.openOffer(Number(document.activeElement.dataset.open), idsOf(root, "[data-open]"));
    return true;
  }
  return false;
}

export function onStoreChange() {
  render();
}
