// "Trier" — the swipe deck. Drag, buttons and arrow keys all go through the
// same commit path, so the deck behaves identically whatever the input.

import { esc, icon, scoreRing, companyOf, excerpt, plural, titleOf, VERDICT_META } from "../format.js";
import { store, pending, isNew, getDetail, setVerdict } from "../store.js";
import { $, metaLine, zoneChip, sectorChip, newDot, dateLabel, showError, reducedMotion, toast, twinBadge } from "../ui.js";

const COMMIT_X = 120;
const COMMIT_Y = 100;
const DEPTH = 3;

let root;
let ctx;
let scope = "all"; // "new" | "all"
let queue = [];
let done = 0;
let total = 0;
let undo = [];
let drag = null;
let tally = { interessante: 0, peut_etre: 0, pas_interessante: 0 };

export function mount(el, context) {
  root = el;
  ctx = context;
  root.innerHTML = `
    <div class="deck-head reveal">
      <div class="seg seg--small" id="tr-scope" role="radiogroup" aria-label="Quelles offres trier"></div>
      <p class="deck-count" id="tr-count"></p>
      <div class="deck-progress"><i id="tr-bar"></i></div>
    </div>
    <div class="deck" id="tr-deck">
      <div class="deck__glow deck__glow--no" aria-hidden="true"></div>
      <div class="deck__glow deck__glow--yes" aria-hidden="true"></div>
      <div class="deck__glow deck__glow--maybe" aria-hidden="true"></div>
      <div class="deck__stage" id="tr-stage"></div>
    </div>
    <div class="deck-controls">
      <button type="button" class="dbtn dbtn--no" id="tr-no" title="Pas pour moi (←)" aria-label="Pas pour moi">${icon("i-x")}</button>
      <button type="button" class="dbtn dbtn--undo" id="tr-undo" title="Annuler (Z)" aria-label="Annuler la dernière décision" disabled>${icon("i-undo")}</button>
      <button type="button" class="dbtn dbtn--maybe" id="tr-maybe" title="Peut-être (↑)" aria-label="Peut-être">${icon("i-star")}</button>
      <button type="button" class="dbtn dbtn--yes" id="tr-yes" title="Intéressante (→)" aria-label="Intéressante">${icon("i-heart")}</button>
    </div>
    <p class="deck-hint"><kbd>←</kbd> pas pour moi · <kbd>↑</kbd> peut-être · <kbd>→</kbd> intéressante · <kbd>Z</kbd> annuler · <kbd>Espace</kbd> détail</p>
  `;
  $("#tr-yes", root).onclick = () => swipe("interessante");
  $("#tr-no", root).onclick = () => swipe("pas_interessante");
  $("#tr-maybe", root).onclick = () => swipe("peut_etre");
  $("#tr-undo", root).onclick = undoLast;
  $("#tr-scope", root).addEventListener("click", (e) => {
    const b = e.target.closest("[data-scope]");
    if (!b || b.dataset.scope === scope) return;
    scope = b.dataset.scope;
    done = 0;
    undo = [];
    tally = { interessante: 0, peut_etre: 0, pas_interessante: 0 };
    build();
  });
  $("#tr-stage", root).addEventListener("click", (e) => {
    if (e.target.closest("[data-detail]") && queue[0]) ctx.openOffer(queue[0].id, queue.map((o) => o.id));
  });
}

function build() {
  const all = pending();
  const fresh = all.filter(isNew);
  if (scope === "new" && fresh.length === 0) scope = "all";
  const src = scope === "new" ? fresh : all;
  queue = [...src].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  total = queue.length + done;
  $("#tr-scope", root).innerHTML = `
    <button type="button" class="seg__btn ${scope === "new" ? "is-on" : ""}" data-scope="new" ${fresh.length ? "" : "disabled"}>Nouveautés<span>${fresh.length}</span></button>
    <button type="button" class="seg__btn ${scope === "all" ? "is-on" : ""}" data-scope="all">Toutes en attente<span>${all.length}</span></button>`;
  renderStack();
}

export function enter() {
  if (!store.loaded) return;
  if (!queue.length && !done) {
    scope = pending().some(isNew) ? "new" : "all";
  }
  build();
}

export const render = enter;

// Verdicts set elsewhere (drawer, list) remove the offer from the deck.
export function onStoreChange(change) {
  if (change.type !== "verdict" || change.fromDeck) return;
  if (queue.some((o) => o.id === change.id) && change.verdict) {
    queue = queue.filter((o) => o.id !== change.id);
    total = Math.max(total - 1, done);
    renderStack();
  }
}

function progress() {
  $("#tr-count", root).innerHTML = queue.length
    ? `<b>${done}</b> triée${done > 1 ? "s" : ""} · <b>${queue.length}</b> restante${queue.length > 1 ? "s" : ""}`
    : `<b>${done}</b> triée${done > 1 ? "s" : ""}`;
  $("#tr-bar", root).style.width = `${total ? (done / total) * 100 : 0}%`;
  $("#tr-undo", root).disabled = undo.length === 0;
  ["#tr-no", "#tr-maybe", "#tr-yes"].forEach((s) => ($(s, root).disabled = queue.length === 0));
  ctx.updateBadge();
}

function card(o, depth) {
  const d = dateLabel(o);
  return `
    <article class="card" data-id="${o.id}" data-depth="${depth}" aria-label="${esc(titleOf(o))}">
      <div class="stamp stamp--yes">OUI</div>
      <div class="stamp stamp--no">NON</div>
      <div class="stamp stamp--maybe">PEUT-ÊTRE</div>
      <header class="card__head">
        <div>
          <p class="card__company">${esc(companyOf(o))} ${twinBadge(o)}${newDot(o)}</p>
          <h2 class="card__title">${esc(titleOf(o))}</h2>
        </div>
        <div class="card__ring">${scoreRing(o.score, 68, 6)}</div>
      </header>
      <p class="meta">${metaLine(o)}</p>
      <div class="chips">${zoneChip(o.geography_zone)}${sectorChip(o.sector)}<span class="chip chip--ghost" title="${esc(d.title)}">${icon("i-clock")}${d.text}</span></div>
      <div class="card__body"><div class="skeleton"><i></i><i></i><i></i></div></div>
      <footer class="card__foot">
        <span class="card__flags">
          <span class="flag flag--gap" title="Écarts de compétences confirmés">${icon("i-x")}${o.gaps_count ?? "–"} écart${(o.gaps_count ?? 0) > 1 ? "s" : ""}</span>
          <span class="flag flag--unc" title="Exigences sans correspondance fiable">${icon("i-question")}${o.uncertain_count ?? "–"} incertain${(o.uncertain_count ?? 0) > 1 ? "s" : ""}</span>
        </span>
        <button type="button" class="btn btn--text" data-detail>Tout lire ${icon("i-arrow")}</button>
      </footer>
    </article>`;
}

function emptyState() {
  const n = tally.interessante + tally.peut_etre + tally.pas_interessante;
  return `
    <div class="deck-empty">
      <svg class="confetti" viewBox="0 0 200 120" aria-hidden="true">
        ${Array.from({ length: 18 }, (_, i) => {
          const x = 20 + ((i * 53) % 160);
          const r = (i * 47) % 360;
          const cls = ["c1", "c2", "c3", "c4"][i % 4];
          return `<rect class="${cls}" x="${x}" y="-10" width="6" height="10" rx="1.5" style="--r:${r}deg;--d:${(i % 6) * 0.12}s;--x:${((i * 29) % 40) - 20}px"/>`;
        }).join("")}
        <g class="trophy"><rect x="84" y="36" width="32" height="32" rx="7"/><rect x="93.5" y="45.5" width="13" height="13" rx="2" transform="rotate(45 100 52)"/></g>
      </svg>
      <h2>${n ? "Pile terminée." : "Rien à trier ici."}</h2>
      <p>${n ? `${plural(n, "décision", "décisions")} cette session : <b class="tone-yes">${tally.interessante} intéressante${tally.interessante > 1 ? "s" : ""}</b>, <b class="tone-maybe">${tally.peut_etre} peut-être</b>, <b class="tone-no">${tally.pas_interessante} écartée${tally.pas_interessante > 1 ? "s" : ""}</b>.` : "Toutes les offres analysées ont déjà reçu ton avis."}</p>
      <div class="deck-empty__cta">
        <a class="btn btn--primary" href="#/selection">Voir ma sélection ${icon("i-arrow")}</a>
        ${scope === "new" && pending().length ? `<button type="button" class="btn btn--ghost" data-scope-all>Trier les ${pending().length} autres</button>` : ""}
      </div>
    </div>`;
}

function renderStack() {
  const stage = $("#tr-stage", root);
  progress();
  if (!queue.length) {
    stage.innerHTML = emptyState();
    stage.querySelector("[data-scope-all]")?.addEventListener("click", () => {
      scope = "all";
      done = 0;
      build();
    });
    return;
  }
  const vis = queue.slice(0, DEPTH);
  stage.innerHTML = vis.map((o, i) => card(o, i)).reverse().join("");
  vis.forEach((o) => {
    getDetail(o.id)
      .then((d) => {
        const body = stage.querySelector(`.card[data-id="${o.id}"] .card__body`);
        if (body) body.innerHTML = `<p>${esc(excerpt(d.description, 900)) || '<span class="muted">Pas de description récupérée.</span>'}</p>`;
      })
      .catch(() => {
        const body = stage.querySelector(`.card[data-id="${o.id}"] .card__body`);
        if (body) body.innerHTML = '<p class="muted">Détail indisponible.</p>';
      });
  });
  wireDrag();
}

const top = () => $('.card[data-depth="0"]', root);

function visuals(el, dx, dy) {
  const rot = Math.max(-16, Math.min(16, dx / 14));
  el.style.transform = `translate(${dx}px, ${dy * 0.45}px) rotate(${rot}deg)`;
  const horiz = Math.abs(dx) >= Math.abs(dy);
  const yes = horiz && dx > 0 ? Math.min(1, dx / COMMIT_X) : 0;
  const no = horiz && dx < 0 ? Math.min(1, -dx / COMMIT_X) : 0;
  const maybe = !horiz && dy < 0 ? Math.min(1, -dy / COMMIT_Y) : 0;
  el.querySelector(".stamp--yes").style.opacity = yes;
  el.querySelector(".stamp--no").style.opacity = no;
  el.querySelector(".stamp--maybe").style.opacity = maybe;
  const deck = $("#tr-deck", root);
  deck.style.setProperty("--yes", yes);
  deck.style.setProperty("--no", no);
  deck.style.setProperty("--maybe", maybe);
}

function resolve(dx, dy) {
  const horiz = Math.abs(dx) >= Math.abs(dy);
  if (horiz && dx > COMMIT_X) return "interessante";
  if (horiz && dx < -COMMIT_X) return "pas_interessante";
  if (!horiz && dy < -COMMIT_Y) return "peut_etre";
  return null;
}

function wireDrag() {
  const el = top();
  if (!el) return;
  el.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button, a")) return;
    el.setPointerCapture(e.pointerId);
    el.classList.remove("is-settling");
    drag = { x: e.clientX, y: e.clientY, dx: 0, dy: 0 };
  });
  el.addEventListener("pointermove", (e) => {
    if (!drag) return;
    drag.dx = e.clientX - drag.x;
    drag.dy = e.clientY - drag.y;
    visuals(el, drag.dx, drag.dy);
  });
  const release = () => {
    if (!drag) return;
    const { dx, dy } = drag;
    drag = null;
    const v = resolve(dx, dy);
    if (v) commit(v);
    else {
      el.classList.add("is-settling");
      visuals(el, 0, 0);
      el.style.transform = "";
    }
  };
  el.addEventListener("pointerup", release);
  el.addEventListener("pointercancel", release);
}

function flyOut(v) {
  const far = window.innerWidth;
  if (v === "interessante") return `translate(${far}px, -60px) rotate(26deg)`;
  if (v === "pas_interessante") return `translate(-${far}px, -60px) rotate(-26deg)`;
  return "translate(0, -130vh) rotate(-5deg)";
}

function swipe(v) {
  if (!queue.length) return;
  const el = top();
  if (el) visuals(el, v === "interessante" ? COMMIT_X : v === "pas_interessante" ? -COMMIT_X : 0, v === "peut_etre" ? -COMMIT_Y : 0);
  commit(v);
}

async function commit(v) {
  const o = queue[0];
  if (!o) return;
  const el = top();
  if (el) {
    el.classList.add("is-flying");
    el.style.transform = flyOut(v);
  }
  queue = queue.slice(1);
  done += 1;
  tally[v] += 1;
  undo.push({ o, v });
  progress();
  setTimeout(() => {
    const deck = $("#tr-deck", root);
    ["--yes", "--no", "--maybe"].forEach((p) => deck.style.setProperty(p, 0));
    renderStack();
  }, el && !reducedMotion() ? 280 : 0);

  try {
    await setVerdict(o.id, v);
    offerTwins(o, v);
  } catch (err) {
    queue = [o, ...queue];
    done -= 1;
    tally[v] -= 1;
    undo.pop();
    showError(`Impossible d'enregistrer l'avis (${err.message}).`);
    renderStack();
  }
}

// Duplicates (same title + place) are never judged implicitly: the user is
// offered to extend the decision, and nothing happens unless they accept.
function offerTwins(o, v) {
  const twins = (o._twins || []).map((id) => store.byId.get(id)).filter((t) => t && !t.user_verdict);
  if (!twins.length) return;
  toast(`${icon(VERDICT_META[v].icon, `tone-${v}`)} ${twins.length > 1 ? `${twins.length} doublons probables` : "1 doublon probable"} de cette offre`, {
    action: "Même avis",
    timeout: 6500,
    onAction: async () => {
      // Leave the deck first (counted as decisions of this session), so the
      // store notifications below find nothing left to remove.
      const inDeck = twins.filter((t) => queue.includes(t));
      queue = queue.filter((q) => !twins.includes(q));
      done += inDeck.length;
      tally[v] += inDeck.length;
      renderStack();
      for (const t of twins) {
        try {
          await setVerdict(t.id, v);
        } catch (err) {
          showError(`Impossible d'enregistrer l'avis (${err.message}).`);
          return;
        }
      }
    },
  });
}

async function undoLast() {
  const entry = undo.pop();
  if (!entry) return;
  try {
    await setVerdict(entry.o.id, null);
  } catch (err) {
    undo.push(entry);
    showError(`Impossible d'annuler (${err.message}).`);
    return;
  }
  queue = [entry.o, ...queue];
  done = Math.max(0, done - 1);
  tally[entry.v] -= 1;
  renderStack();
  const el = top();
  if (el && !reducedMotion()) {
    el.classList.add("is-returning");
    el.addEventListener("animationend", () => el.classList.remove("is-returning"), { once: true });
  }
}

export function onKey(e) {
  if (e.key === "ArrowRight") { swipe("interessante"); return true; }
  if (e.key === "ArrowLeft") { swipe("pas_interessante"); return true; }
  if (e.key === "ArrowUp") { e.preventDefault(); swipe("peut_etre"); return true; }
  if (e.key === "z" || e.key === "Z") { undoLast(); return true; }
  if (e.key === " " && queue[0]) { e.preventDefault(); ctx.openOffer(queue[0].id, queue.map((o) => o.id)); return true; }
  return false;
}
