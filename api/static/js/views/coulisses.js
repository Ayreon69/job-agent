// "Coulisses" — how the pipeline works, with its real numbers, its daily
// rhythm, and the rules it never breaks.

import { esc, icon, ZONE_LABELS, ZONE_ORDER, SOURCE_LABELS, fmtDate, fmtTime, relTime, startOfDay } from "../format.js";
import { store, triageable } from "../store.js";
import { $, wireTooltips } from "../ui.js";
import { fetchHealth } from "../api.js";

let root;
let health = null;
let healthLoaded = false;

const DAY = 86400000;

export function mount(el) {
  root = el;
  wireTooltips(root);
}

function count(arr, key) {
  const m = new Map();
  for (const o of arr) {
    const k = key(o);
    if (k) m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}

function stage(n, title, iconId, figure, figLabel, lines, text) {
  return `
    <li class="stage-card" style="--i:${n}">
      <div class="stage-card__num">0${n}</div>
      <div class="stage-card__icon">${icon(iconId)}</div>
      <h3>${title}</h3>
      <p class="stage-card__fig"><b>${figure}</b><span>${figLabel}</span></p>
      <ul class="stage-card__lines">${lines.map((l) => `<li>${l}</li>`).join("")}</ul>
      <p class="stage-card__text">${text}</p>
    </li>`;
}

// GitHub-style calendar of the days offers were first spotted — the
// pipeline's actual rhythm, gaps included (outages show up as holes).
function rhythm(offers, weeks = 14, now = new Date()) {
  const counts = new Map();
  for (const o of offers) {
    if (!o._firstSeen) continue;
    const k = startOfDay(o._firstSeen).getTime();
    counts.set(k, (counts.get(k) || 0) + 1);
  }
  const today = startOfDay(now);
  const dow = (today.getDay() + 6) % 7; // monday = 0
  const start = new Date(today.getTime() - ((weeks - 1) * 7 + dow) * DAY);
  const cell = 15, gap = 3, padL = 26, padT = 18;
  const W = padL + weeks * (cell + gap), H = padT + 7 * (cell + gap);
  const vals = [...counts.values()].sort((a, b) => a - b);
  const p90 = vals[Math.floor(vals.length * 0.9)] || 1;
  let rects = "";
  let months = "";
  let lastMonth = -1;
  for (let w = 0; w < weeks; w++) {
    for (let d = 0; d < 7; d++) {
      const date = new Date(start.getTime() + (w * 7 + d) * DAY);
      if (date > today) continue;
      const n = counts.get(date.getTime()) || 0;
      const lvl = n === 0 ? 0 : Math.min(4, Math.ceil((n / p90) * 4));
      rects += `<rect class="cal cal--${lvl}" x="${padL + w * (cell + gap)}" y="${padT + d * (cell + gap)}" width="${cell}" height="${cell}" rx="3" data-tip="${esc(`<b>${fmtDate(date, { weekday: "long", day: "numeric", month: "long" })}</b><br>${n} offre(s) repérée(s)`)}"/>`;
      if (d === 0 && date.getMonth() !== lastMonth) {
        lastMonth = date.getMonth();
        months += `<text class="ch-axis" x="${padL + w * (cell + gap)}" y="10">${fmtDate(date, { month: "short" })}</text>`;
      }
    }
  }
  const days = ["lun", "", "mer", "", "ven", "", ""].map((l, d) => (l ? `<text class="ch-axis" x="0" y="${padT + d * (cell + gap) + cell - 3}">${l}</text>` : "")).join("");
  return `<svg class="chart chart--cal" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Rythme de collecte sur ${weeks} semaines">${months}${days}${rects}</svg>`;
}

function healthCard() {
  if (!healthLoaded) return '<p class="muted">Vérification…</p>';
  if (!health) return `<p class="health health--bad">${icon("i-alert")}Endpoint /health injoignable ou dégradé.</p>`;
  const c = health.checks;
  const row = (ok, label, detail) => `<li class="${ok === null ? "is-na" : ok ? "is-ok" : "is-bad"}"><i></i><span>${label}</span><small>${detail}</small></li>`;
  return `
    <ul class="health-list">
      ${row(c.database_accessible, "Base SQLite", c.database_accessible ? "accessible" : "injoignable")}
      ${row(c.mistral_key_present, "Clé Mistral", c.mistral_key_present ? "présente" : "absente")}
      ${row(c.embeddings_loaded, "Modèle d'embeddings", c.embeddings_loaded === null ? "non chargé — déploiement en lecture seule" : c.embeddings_loaded ? "chargé" : "échec du chargement")}
    </ul>
    <p class="muted small">${c.embeddings_loaded === null ? "Ce déploiement sert les résultats ; le scoring tourne chaque matin dans GitHub Actions." : "Mode complet : POST /analyze disponible."}</p>`;
}

export function render() {
  if (!store.loaded) return;
  const all = store.offers;
  const sources = count(all, (o) => o.source);
  const zones = count(all, (o) => o.geography_zone);
  const scored = all.filter((o) => o.score !== null && o.score !== undefined);
  const gaps = all.reduce((s, o) => s + (o.gaps_count || 0), 0);
  const unc = all.reduce((s, o) => s + (o.uncertain_count || 0), 0);
  const judged = triageable().filter((o) => o.user_verdict).length;
  const firstDay = all.reduce((m, o) => (o._firstSeen && (!m || o._firstSeen < m) ? o._firstSeen : m), null);

  root.innerHTML = `
    <header class="page-head page-head--center reveal">
      <p class="kicker">Coulisses</p>
      <h1 class="page-title page-title--xl">Chaque matin, un agent lit les offres <em>pour toi</em>.<br>Il s'arrête toujours avant de décider.</h1>
    </header>

    <ol class="pipeline reveal" style="--d:1">
      ${stage(1, "Collecte", "i-source", all.length, "offres suivies",
        [...sources.entries()].map(([s, n]) => `${esc(SOURCE_LABELS[s] || s)} <b>${n}</b>`),
        "Playwright parcourt Hellowork et jobup.ch, dédoublonne, et note chaque jour quelles offres sont encore en ligne.")}
      ${stage(2, "Géographie", "i-pin", zones.size, "zones reconnues",
        ZONE_ORDER.filter((z) => zones.has(z)).map((z) => `${ZONE_LABELS[z]} <b>${zones.get(z)}</b>`),
        "Des règles déterministes classent le lieu avant tout appel au LLM. Une zone inconnue ne bloque rien : l'offre est marquée « à valider ».")}
      ${stage(3, "Scoring RAG", "i-sparkle", scored.length, "offres scorées",
        [`médiane <b>${scored.length ? [...scored].sort((a, b) => a.score - b.score)[Math.floor(scored.length / 2)].score : "–"}</b>`, `≥ 80 : <b>${scored.filter((o) => o.score >= 80).length}</b>`],
        "Les exigences de l'offre sont confrontées aux passages du profil retrouvés dans ChromaDB par embeddings ; Mistral arbitre et justifie le score.")}
      ${stage(4, "Analyse", "i-brief", gaps, "écarts signalés",
        [`incertains <b>${unc}</b>`, `soit <b>${scored.length ? (gaps / scored.length).toFixed(1) : "–"}</b> écart(s) par offre`],
        "Une analyse de candidature est rédigée pour chaque offre. Les compétences manquantes sont dites, jamais maquillées.")}
      <li class="stage-card stage-card--human" style="--i:5">
        <div class="stage-card__num">05</div>
        <div class="stage-card__icon">${icon("i-lock")}</div>
        <h3>Toi</h3>
        <p class="stage-card__fig"><b>${judged}</b><span>offres jugées</span></p>
        <ul class="stage-card__lines"><li>en attente <b>${triageable().length - judged}</b></li></ul>
        <p class="stage-card__text">La seule étape que l'agent ne fait jamais : décider, puis postuler. Aucune candidature ne part automatiquement.</p>
      </li>
    </ol>

    <div class="panels reveal" style="--d:2">
      <figure class="panel panel--wide">
        <figcaption><h3>Rythme de collecte</h3><span class="legend">offres repérées par jour, 14 dernières semaines</span></figcaption>
        <div class="cal-wrap">${rhythm(all)}</div>
        <p class="muted small">Premier passage enregistré : ${fmtDate(firstDay)}. ${store.lastRun ? `Dernier : ${relTime(store.lastRun)} (${fmtDate(store.lastRun, { day: "numeric", month: "long" })} à ${fmtTime(store.lastRun)}).` : ""} Les trous correspondent aux jours sans nouvelle offre — ou sans passage.</p>
      </figure>
      <figure class="panel">
        <figcaption><h3>État du service</h3><span class="legend">GET /health</span></figcaption>
        <div id="health-host">${healthCard()}</div>
      </figure>
    </div>

    <section class="principles reveal" style="--d:3">
      <h2 class="principles__title">Trois règles non négociables</h2>
      <ol>
        <li><b>Jamais de candidature automatique.</b><span>L'agent prépare, trie et explique. L'envoi reste un geste humain, toujours.</span></li>
        <li><b>Un score honnête.</b><span>Le score aide à décider ; il n'est jamais gonflé pour rendre une offre plus séduisante qu'elle ne l'est.</span></li>
        <li><b>Rien d'inventé.</b><span>Aucune compétence n'est ajoutée au profil. Un écart est signalé comme un écart.</span></li>
      </ol>
    </section>

    <section class="stack-list reveal" style="--d:4">
      ${["Playwright", "SQLite", "ChromaDB", "sentence-transformers", "Mistral", "FastAPI", "Docker", "GitHub Actions", "Render"].map((t, i) => `<span style="--i:${i}">${t}</span>`).join("")}
    </section>
  `;

  if (!healthLoaded) {
    fetchHealth().then((h) => {
      health = h;
      healthLoaded = true;
      const host = $("#health-host", root);
      if (host) host.innerHTML = healthCard();
    });
  }
}

export const enter = render;
export const onStoreChange = (c) => { if (c.type === "load") render(); };

