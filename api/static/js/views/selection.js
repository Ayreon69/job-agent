// "Sélection" — a board of everything already judged, one column per
// verdict. Cards can be dragged between columns to change one's mind.

import { esc, icon, VERDICTS, VERDICT_META, ZONE_LABELS, companyOf, locationOf, cleanSalary, cleanContract, parsePublished, fmtDate, titleOf } from "../format.js";
import { store, triageable, staleDays, STALE_AFTER } from "../store.js";
import { $, $$, decide, dateLabel, scorePill, zoneChip, toast, staleChip } from "../ui.js";

let root;
let ctx;
let dragId = null;
let collapsed = true; // "pas pour moi" column starts folded: it's the archive

const BLURB = {
  interessante: "À creuser, puis à candidater — toi-même.",
  peut_etre: "À relire à tête reposée.",
  pas_interessante: "Écartées. Glisse une carte ailleurs pour changer d'avis.",
};

export function mount(el, context) {
  root = el;
  ctx = context;
  root.addEventListener("click", (e) => {
    const ex = e.target.closest("[data-export]");
    if (ex) return exportSelection(ex.dataset.export);
    if (e.target.closest(".kcard__link")) return; // plain link to the source site
    const t = e.target.closest("[data-toggle-archive]");
    if (t) {
      collapsed = !collapsed;
      render();
      return;
    }
    const c = e.target.closest(".kcard");
    if (c) ctx.openOffer(Number(c.dataset.id), idsIn(c.closest(".kcol")));
  });
  root.addEventListener("keydown", (e) => {
    const c = e.target.closest(".kcard");
    if (c && e.key === "Enter") ctx.openOffer(Number(c.dataset.id), idsIn(c.closest(".kcol")));
  });

  root.addEventListener("dragstart", (e) => {
    const c = e.target.closest(".kcard");
    if (!c) return;
    dragId = Number(c.dataset.id);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(dragId));
    requestAnimationFrame(() => c.classList.add("is-dragging"));
  });
  root.addEventListener("dragend", () => {
    dragId = null;
    $$(".is-dragging, .is-over", root).forEach((n) => n.classList.remove("is-dragging", "is-over"));
  });
  root.addEventListener("dragover", (e) => {
    const col = e.target.closest(".kcol");
    if (!col || dragId === null) return;
    e.preventDefault();
    $$(".kcol.is-over", root).forEach((n) => n !== col && n.classList.remove("is-over"));
    col.classList.add("is-over");
  });
  root.addEventListener("drop", async (e) => {
    const col = e.target.closest(".kcol");
    if (!col || dragId === null) return;
    e.preventDefault();
    const o = store.byId.get(dragId);
    col.classList.remove("is-over");
    if (o && o.user_verdict !== col.dataset.verdict) await decide(o, col.dataset.verdict);
  });
}

const idsIn = (col) => $$(".kcard", col).map((c) => Number(c.dataset.id));

function kcard(o, i) {
  const d = dateLabel(o);
  const sal = cleanSalary(o.salary);
  return `
    <li class="kcard" data-id="${o.id}" draggable="true" tabindex="0" style="--i:${Math.min(i, 12)}">
      <div class="kcard__top">${scorePill(o.score)}<span class="kcard__date" title="${esc(d.title)}">${d.text}</span></div>
      <h3 class="kcard__title">${esc(titleOf(o))}</h3>
      <p class="kcard__company">${esc(companyOf(o))}${locationOf(o) ? ` · ${esc(locationOf(o))}` : ""}</p>
      <div class="chips">${staleChip(o)}${zoneChip(o.geography_zone)}${sal ? `<span class="chip chip--ghost">${icon("i-coins")}${esc(sal)}</span>` : ""}</div>
      ${o.url && o.user_verdict !== "pas_interessante" ? `<a class="kcard__link" href="${esc(o.url)}" target="_blank" rel="noopener" draggable="false">Ouvrir l'offre ${icon("i-external")}</a>` : ""}
    </li>`;
}

function staleNotice(judged) {
  const stale = judged.filter((o) => o.user_verdict !== "pas_interessante" && staleDays(o) >= STALE_AFTER);
  if (!stale.length) return "";
  return `<p class="alert-strip reveal">${icon("i-alert")}<span><b>${stale.length} offre${stale.length > 1 ? "s" : ""} de ta sélection ${stale.length > 1 ? "n'apparaissent" : "n'apparaît"} plus</b> dans les dernières collectes — possiblement pourvue${stale.length > 1 ? "s" : ""}. Si elle${stale.length > 1 ? "s t'intéressent" : " t'intéresse"}, vérifie vite sur le site source : sans nouvelle apparition, une offre est supprimée après 30 jours.</span></p>`;
}

export function render() {
  if (!store.loaded) return;
  const judged = triageable().filter((o) => o.user_verdict);
  const cols = VERDICTS.map((v) => ({ v, items: judged.filter((o) => o.user_verdict === v).sort((a, b) => (b.score ?? -1) - (a.score ?? -1)) }));

  root.innerHTML = `
    <header class="page-head reveal">
      <div>
        <p class="kicker">Tes décisions</p>
        <h1 class="page-title">Sélection <span class="page-title__count">${judged.length}</span></h1>
      </div>
      <div class="page-head__side">
        <p class="page-lede">Glisse une carte d'une colonne à l'autre pour changer d'avis. Rien ne part d'ici : postuler reste une démarche manuelle.</p>
        ${judged.length ? `<div class="export">
          <button type="button" class="btn btn--ghost" data-export="csv">${icon("i-list")}Exporter en CSV</button>
          <button type="button" class="btn btn--ghost" data-export="md">${icon("i-brief")}Copier en Markdown</button>
        </div>` : ""}
      </div>
    </header>
    ${judged.length === 0 ? `
      <div class="empty-state empty-state--big reveal" style="--d:1">
        <svg viewBox="0 0 160 100" class="empty-state__art" aria-hidden="true"><rect x="10" y="16" width="40" height="70" rx="6"/><rect x="60" y="16" width="40" height="48" rx="6"/><rect x="110" y="16" width="40" height="30" rx="6"/></svg>
        <h3>Ta sélection est vide.</h3>
        <p>Chaque avis donné dans « Trier » ou dans la liste arrive ici.</p>
        <a class="btn btn--primary" href="#/trier">${icon("i-cards")}Commencer le tri</a>
      </div>` : `
    ${staleNotice(judged)}
    <div class="board ${collapsed ? "board--folded" : ""} ${calm ? "no-anim" : "reveal"}" style="--d:1">
      ${cols.map(({ v, items }) => {
        const m = VERDICT_META[v];
        const folded = v === "pas_interessante" && collapsed;
        return `
        <section class="kcol kcol--${v} ${folded ? "is-folded" : ""}" data-verdict="${v}" aria-label="${m.label}">
          <header class="kcol__head">
            <span class="kcol__icon">${icon(m.icon)}</span>
            <h2>${m.label}</h2>
            <span class="kcol__n">${items.length}</span>
            ${v === "pas_interessante" ? `<button type="button" class="btn btn--text kcol__fold" data-toggle-archive>${folded ? "Déplier" : "Replier"}</button>` : ""}
          </header>
          <p class="kcol__blurb">${BLURB[v]}</p>
          <ol class="kcol__list">
            ${folded ? "" : items.map(kcard).join("") || `<li class="kcol__empty">Dépose une carte ici</li>`}
          </ol>
          ${folded ? `<div class="kcol__drop">Dépose ici pour écarter</div>` : ""}
        </section>`;
      }).join("")}
    </div>`}
  `;
}

// Export: a CSV to track applications in a spreadsheet, or a Markdown list
// to paste into notes. Built client-side from data already on the page.
function exportSelection(kind) {
  const rows = triageable()
    .filter((o) => o.user_verdict && o.user_verdict !== "pas_interessante")
    .sort((a, b) => VERDICTS.indexOf(a.user_verdict) - VERDICTS.indexOf(b.user_verdict) || (b.score ?? -1) - (a.score ?? -1));
  if (!rows.length) return toast("Rien à exporter : aucune offre intéressante ou peut-être.");
  const stamp = new Date().toISOString().slice(0, 10);

  if (kind === "csv") {
    const cols = [
      ["Avis", (o) => VERDICT_META[o.user_verdict].label],
      ["Score", (o) => o.score ?? ""],
      ["Poste", (o) => titleOf(o)],
      ["Entreprise", (o) => companyOf(o)],
      ["Lieu", (o) => locationOf(o) || ""],
      ["Zone", (o) => ZONE_LABELS[o.geography_zone] || ""],
      ["Secteur", (o) => o.sector || ""],
      ["Contrat", (o) => cleanContract(o.contract_type) || ""],
      ["Salaire", (o) => cleanSalary(o.salary) || ""],
      ["Publiée le", (o) => { const d = parsePublished(o.published_at); return d ? d.toISOString().slice(0, 10) : ""; }],
      ["Lien", (o) => o.url || ""],
      ["Candidature envoyée le", () => ""],
      ["Notes", () => ""],
    ];
    const cell = (v) => `"${String(v).replace(/"/g, '""')}"`;
    const csv = [cols.map(([h]) => cell(h)).join(";"), ...rows.map((o) => cols.map(([, f]) => cell(f(o))).join(";"))].join("\r\n");
    // BOM + ";" so Excel (fr) opens accents and columns correctly.
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `selection-job-agent-${stamp}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast(`${icon("i-list")} ${rows.length} offre(s) exportée(s) en CSV`);
    return;
  }

  const md = [`# Sélection job·agent — ${fmtDate(new Date(), { day: "numeric", month: "long", year: "numeric" })}`, ""];
  for (const v of ["interessante", "peut_etre"]) {
    const list = rows.filter((o) => o.user_verdict === v);
    if (!list.length) continue;
    md.push(`## ${VERDICT_META[v].label} (${list.length})`, "");
    for (const o of list) {
      const bits = [`score ${o.score ?? "–"}`, locationOf(o), cleanContract(o.contract_type), cleanSalary(o.salary)].filter(Boolean).join(" · ");
      md.push(`- [ ] **${titleOf(o)}** — ${companyOf(o)} (${bits})${o.url ? `\n  ${o.url}` : ""}`);
    }
    md.push("");
  }
  const text = md.join("\n");
  navigator.clipboard?.writeText(text).then(
    () => toast(`${icon("i-brief")} Sélection copiée en Markdown (${rows.length} offres)`),
    () => toast("Copie impossible dans ce navigateur.", { tone: "error" }),
  );
}

let calm = false; // after the first paint, re-renders (drops) skip the entrance animation
export function enter() {
  calm = false;
  render();
  calm = true;
}
export function onStoreChange() {
  render();
}
