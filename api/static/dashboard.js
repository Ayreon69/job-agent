// job-agent dashboard: thin display layer over GET /offers, GET /offers/{id}
// and POST /offers/{id}/verdict. No scoring/business logic here — every
// value shown is exactly what the API already returns (see api/main.py,
// api/schemas.py). user_verdict is the one piece of state this UI writes
// back: a pure human triage decision, never read or influenced by the
// scoring pipeline (storage/db.py's user_verdict column).

const ZONE_LABELS = {
  suisse_romande: "Suisse romande",
  rhone_alpes: "Rhône-Alpes",
  uae_gcc: "UAE / GCC",
  suisse_autre: "Suisse (autre)",
  autre_france: "Autre France",
  inconnu: "Inconnu",
};

const ZONE_BADGE_CLASS = {
  suisse_romande: "badge-green",
  rhone_alpes: "badge-green",
  uae_gcc: "badge-green",
  suisse_autre: "badge-green",
  autre_france: "badge-green",
  inconnu: "badge-amber",
};

const STATUS_LABELS = {
  nouveau: "🆕 Nouveau",
  analyse: "✅ Analysé",
  a_valider_geographie: "⚠️ À valider (géographie)",
  echec: "❌ Échec",
};

// Offers eligible for triage/stats: only ones with a real analysis to judge.
// 'nouveau' (not processed yet) and 'echec' (pipeline error) have nothing to
// swipe on — excluded from the stat strip's "Toutes" count and the swipe queue.
const TRIAGEABLE_STATUSES = new Set(["analyse", "a_valider_geographie"]);

const VERDICTS = ["interessante", "peut_etre", "pas_interessante"];
const VERDICT_META = {
  interessante: { label: "Intéressante", emoji: "♥", cls: "yes" },
  peut_etre: { label: "Peut-être", emoji: "★", cls: "maybe" },
  pas_interessante: { label: "Pas pour moi", emoji: "✕", cls: "no" },
};

// Drag distance (px) at which a swipe commits — buttons fake this same
// distance so the fly-out animation looks identical either way.
const COMMIT_THRESHOLD_X = 120;
const COMMIT_THRESHOLD_Y = 100;
const STACK_DEPTH = 3; // top card + 2 peeking behind it

let allOffers = [];
let currentSort = { key: "score", dir: "desc" };
let currentVerdictFilter = ""; // "" | "__pending__" | one of VERDICTS
let expandedOfferId = null; // table accordion: at most one detail row open
let activeView = localStorage.getItem("job-agent-view") || "table";

// ---------------------------------------------------------------------
// API
// ---------------------------------------------------------------------

async function fetchOffers() {
  const res = await fetch("/offers");
  if (!res.ok) throw new Error(`GET /offers -> ${res.status}`);
  return res.json();
}

async function fetchOfferDetail(offerId) {
  const res = await fetch(`/offers/${offerId}`);
  if (!res.ok) throw new Error(`GET /offers/${offerId} -> ${res.status}`);
  return res.json();
}

async function postVerdict(offerId, verdict) {
  const res = await fetch(`/offers/${offerId}/verdict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ verdict }),
  });
  if (!res.ok) throw new Error(`POST /offers/${offerId}/verdict -> ${res.status}`);
  return res.json();
}

// Applies a verdict everywhere it matters: persists it, updates the local
// cache so the table/stat strip/swipe queue all stay in sync without a
// full refetch, and reports failure without leaving the UI in a state that
// silently disagrees with the server.
async function applyVerdict(offerId, verdict) {
  const offer = allOffers.find((o) => o.id === offerId);
  const previous = offer ? offer.user_verdict : undefined;
  if (offer) offer.user_verdict = verdict; // optimistic
  try {
    await postVerdict(offerId, verdict);
  } catch (err) {
    if (offer) offer.user_verdict = previous;
    showError(`Impossible d'enregistrer l'avis pour l'offre ${offerId} (${err.message}).`);
    throw err;
  }
  return previous;
}

// ---------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------

function showError(message) {
  const banner = document.getElementById("error-banner");
  banner.textContent = message;
  banner.hidden = false;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function escapeAndBold(str) {
  return escapeHtml(str).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function zoneBadgeHtml(zone) {
  if (!zone) return '<span class="badge badge-gray">—</span>';
  const cls = ZONE_BADGE_CLASS[zone] || "badge-gray";
  return `<span class="badge ${cls}">${escapeHtml(ZONE_LABELS[zone] || zone)}</span>`;
}

// sector is a free-ish LLM-classified label (scoring/agent.py's
// SECTOR_SUGGESTIONS) — neutral badge styling, not a green/amber signal
// like the zone badge, since it's descriptive rather than a verdict.
function sectorBadgeHtml(sector) {
  return sector ? `<span class="badge badge-sector">${escapeHtml(sector)}</span>` : '<span class="badge badge-gray">—</span>';
}

function formatPublishedAt(publishedAt) {
  return publishedAt ? escapeHtml(publishedAt) : "—";
}

function formatFirstSeenAt(firstSeenAt) {
  if (!firstSeenAt) return "—";
  const date = new Date(firstSeenAt.replace(" ", "T") + "Z");
  if (Number.isNaN(date.getTime())) return escapeHtml(firstSeenAt);
  return date.toLocaleDateString("fr-FR", { year: "numeric", month: "short", day: "numeric" });
}

function isTriageable(offer) {
  return TRIAGEABLE_STATUSES.has(offer.status);
}

// ---------------------------------------------------------------------
// View switching (Tableau / Trier)
// ---------------------------------------------------------------------

function setView(view) {
  activeView = view;
  localStorage.setItem("job-agent-view", view);
  document.getElementById("view-table").hidden = view !== "table";
  document.getElementById("view-swipe").hidden = view !== "swipe";
  document.querySelectorAll(".view-tab").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab.dataset.view === view));
  });
  if (view === "swipe") buildSwipeQueue();
  else renderTable(); // re-render on every switch INTO table, not just at page load — a
                       // switch from a persisted "swipe" view (localStorage) otherwise left
                       // the table stuck on its initial "Chargement…" placeholder forever.
}

function wireViewSwitch() {
  document.querySelectorAll(".view-tab").forEach((tab) => {
    tab.addEventListener("click", () => setView(tab.dataset.view));
  });
}

// ---------------------------------------------------------------------
// Stat strip
// ---------------------------------------------------------------------

function renderStatStrip() {
  const triageable = allOffers.filter(isTriageable);
  const counts = { "": triageable.length, __pending__: 0, interessante: 0, peut_etre: 0, pas_interessante: 0 };
  for (const o of triageable) {
    if (o.user_verdict) counts[o.user_verdict] += 1;
    else counts.__pending__ += 1;
  }

  document.getElementById("stat-all").textContent = counts[""];
  document.getElementById("stat-pending").textContent = counts.__pending__;
  document.getElementById("stat-interessante").textContent = counts.interessante;
  document.getElementById("stat-peut_etre").textContent = counts.peut_etre;
  document.getElementById("stat-pas_interessante").textContent = counts.pas_interessante;

  document.querySelectorAll(".stat-chip").forEach((chip) => {
    chip.classList.toggle("is-active", chip.dataset.verdictFilter === currentVerdictFilter);
  });
}

function wireStatStrip() {
  document.querySelectorAll(".stat-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      currentVerdictFilter = chip.dataset.verdictFilter;
      renderStatStrip();
      setView("table"); // drilling into a bucket reads most naturally as a filtered list; renders the table itself
    });
  });
}

// ---------------------------------------------------------------------
// Table view
// ---------------------------------------------------------------------

function populateFilterOptions(offers) {
  const zoneSelect = document.getElementById("filter-zone");
  const statusSelect = document.getElementById("filter-status");
  const sectorSelect = document.getElementById("filter-sector");

  for (const zone of new Set(offers.map((o) => o.geography_zone).filter(Boolean))) {
    const opt = document.createElement("option");
    opt.value = zone;
    opt.textContent = ZONE_LABELS[zone] || zone;
    zoneSelect.appendChild(opt);
  }
  for (const status of new Set(offers.map((o) => o.status).filter(Boolean))) {
    const opt = document.createElement("option");
    opt.value = status;
    opt.textContent = STATUS_LABELS[status] || status;
    statusSelect.appendChild(opt);
  }
  // Sorted alphabetically (unlike zone/status, sector isn't a small fixed
  // set — a stable order makes a growing list scannable as it fills in).
  for (const sector of [...new Set(offers.map((o) => o.sector).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr"))) {
    const opt = document.createElement("option");
    opt.value = sector;
    opt.textContent = sector;
    sectorSelect.appendChild(opt);
  }
}

function applyFilters(offers) {
  const zone = document.getElementById("filter-zone").value;
  const status = document.getElementById("filter-status").value;
  const sector = document.getElementById("filter-sector").value;
  return offers.filter((o) => {
    if (zone && o.geography_zone !== zone) return false;
    if (status && o.status !== status) return false;
    if (sector && o.sector !== sector) return false;
    if (currentVerdictFilter === "__pending__") return isTriageable(o) && !o.user_verdict;
    if (currentVerdictFilter) return o.user_verdict === currentVerdictFilter;
    return true;
  });
}

function sortOffers(offers) {
  const { key, dir } = currentSort;
  return [...offers].sort((a, b) => {
    let av = a[key];
    let bv = b[key];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    if (typeof av === "string") av = av.toLowerCase();
    if (typeof bv === "string") bv = bv.toLowerCase();
    if (av < bv) return dir === "asc" ? -1 : 1;
    if (av > bv) return dir === "asc" ? 1 : -1;
    return 0;
  });
}

function flagsHtml(offer) {
  if (offer.gaps_count === null || offer.gaps_count === undefined) return "—";
  const parts = [];
  if (offer.gaps_count > 0) parts.push(`<span class="gap-count">✕ ${offer.gaps_count}</span>`);
  if (offer.uncertain_count > 0) parts.push(`<span class="uncertain-count">? ${offer.uncertain_count}</span>`);
  if (parts.length === 0) parts.push("aucun");
  return parts.join(" · ");
}

function verdictPillHtml(offer) {
  if (!isTriageable(offer)) return '<span class="badge badge-gray">—</span>';
  if (!offer.user_verdict) return `<button type="button" class="verdict-pill" data-offer-id="${offer.id}">Trier</button>`;
  const meta = VERDICT_META[offer.user_verdict];
  return `<button type="button" class="verdict-pill" data-verdict="${offer.user_verdict}" data-offer-id="${offer.id}">${meta.emoji} ${meta.label}</button>`;
}

function closeVerdictMenu() {
  document.querySelector(".verdict-menu")?.remove();
}

// A small floating menu anchored to whichever verdict pill was clicked —
// used from both the table cell and the detail panel, so verdict changes
// are always one click away without leaving the table for the swipe view.
function openVerdictMenu(anchorEl, offerId, onDone) {
  closeVerdictMenu();
  const menu = document.createElement("div");
  menu.className = "verdict-menu";
  const offer = allOffers.find((o) => o.id === offerId);

  const options = [...VERDICTS];
  const items = options.map(
    (v) => `<button type="button" data-set-verdict="${v}">${VERDICT_META[v].emoji} ${VERDICT_META[v].label}</button>`
  );
  if (offer?.user_verdict) items.push('<button type="button" data-set-verdict="">✳ Effacer l\'avis</button>');
  menu.innerHTML = items.join("");

  document.body.appendChild(menu);
  const rect = anchorEl.getBoundingClientRect();
  menu.style.top = `${window.scrollY + rect.bottom + 4}px`;
  menu.style.left = `${window.scrollX + rect.left}px`;

  menu.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-set-verdict]");
    if (!btn) return;
    const verdict = btn.dataset.setVerdict || null;
    closeVerdictMenu();
    try {
      await applyVerdict(offerId, verdict);
      onDone?.();
    } catch {
      /* applyVerdict already surfaced the error banner */
    }
  });

  setTimeout(() => {
    document.addEventListener("click", closeVerdictMenu, { once: true });
  }, 0);
}

function renderTable() {
  const filtered = applyFilters(allOffers);
  const sorted = sortOffers(filtered);
  const tbody = document.getElementById("offers-body");
  document.getElementById("offer-count").textContent = `${sorted.length} offre(s)`;

  if (sorted.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="empty">Aucune offre ne correspond aux filtres.</td></tr>';
    return;
  }

  tbody.innerHTML = "";
  for (const offer of sorted) {
    const tr = document.createElement("tr");
    tr.dataset.offerId = offer.id;
    if (offer.id === expandedOfferId) tr.classList.add("selected");
    tr.innerHTML = `
      <td>${escapeHtml(offer.title)}</td>
      <td>${escapeHtml(offer.company || "—")}</td>
      <td>${zoneBadgeHtml(offer.geography_zone)}</td>
      <td>${sectorBadgeHtml(offer.sector)}</td>
      <td>${offer.score === null || offer.score === undefined ? "—" : offer.score}</td>
      <td>${STATUS_LABELS[offer.status] || offer.status}</td>
      <td class="verdict-cell">${verdictPillHtml(offer)}</td>
      <td class="flags">${flagsHtml(offer)}</td>
      <td>${formatPublishedAt(offer.published_at)}</td>
      <td>${formatFirstSeenAt(offer.first_seen_at)}</td>
    `;
    tr.querySelector(".verdict-pill")?.addEventListener("click", (e) => {
      e.stopPropagation();
      openVerdictMenu(e.currentTarget, offer.id, () => {
        renderStatStrip();
        renderTable();
      });
    });
    tr.addEventListener("click", () => selectOffer(offer.id));
    tbody.appendChild(tr);

    if (offer.id === expandedOfferId) {
      const detailTr = document.createElement("tr");
      detailTr.className = "detail-row";
      detailTr.dataset.detailFor = offer.id;
      const td = document.createElement("td");
      td.colSpan = 10;
      td.innerHTML = '<div class="detail-panel"><p class="loading">Chargement du détail…</p></div>';
      detailTr.appendChild(td);
      tbody.appendChild(detailTr);
    }
  }
}

function updateSortHeaders() {
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.sort === currentSort.key) th.classList.add(currentSort.dir === "asc" ? "sorted-asc" : "sorted-desc");
  });
}

async function selectOffer(offerId) {
  expandedOfferId = expandedOfferId === offerId ? null : offerId;
  renderTable();
  if (expandedOfferId === null) return;

  const detailTr = document.querySelector(`tr.detail-row[data-detail-for="${expandedOfferId}"]`);
  if (!detailTr) return;
  const panel = detailTr.querySelector(".detail-panel");

  try {
    const detail = await fetchOfferDetail(expandedOfferId);
    if (expandedOfferId !== detail.id) return;
    renderDetail(panel, detail);
  } catch (err) {
    panel.innerHTML = `<p class="error-banner">Impossible de charger le détail de l'offre ${offerId} (${err.message}).</p>`;
  }
}

function originalOfferLinkHtml(detail) {
  if (!detail.url) return "";
  return `<a class="original-offer-link" href="${escapeHtml(detail.url)}" target="_blank" rel="noopener">Voir l'offre originale ↗</a>`;
}

function verdictButtonsHtml(offerId, currentVerdict) {
  const buttons = VERDICTS.map((v) => {
    const meta = VERDICT_META[v];
    const active = v === currentVerdict ? "is-active" : "";
    return `<button type="button" class="detail-verdict-btn ${active}" data-verdict="${v}" data-offer-id="${offerId}">${meta.emoji} ${meta.label}</button>`;
  }).join("");
  return `<div class="detail-verdict-row"><span>Mon avis :</span>${buttons}</div>`;
}

function wireDetailVerdictButtons(panel, offerId) {
  panel.querySelectorAll(".detail-verdict-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const offer = allOffers.find((o) => o.id === offerId);
      const next = offer?.user_verdict === btn.dataset.verdict ? null : btn.dataset.verdict; // click active = clear
      try {
        await applyVerdict(offerId, next);
        renderStatStrip();
        panel.querySelectorAll(".detail-verdict-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.verdict === next));
        renderTable();
      } catch {
        /* error already surfaced */
      }
    });
  });
}

function renderDetail(panel, detail) {
  if (detail.status === "nouveau") {
    panel.innerHTML = `
      <h2>${escapeHtml(detail.title)}</h2>
      ${originalOfferLinkHtml(detail)}
      <p class="detail-meta">${escapeHtml(detail.company || "—")} · ${zoneBadgeHtml(detail.geography_zone)} · ${STATUS_LABELS[detail.status]} · Publiée le ${formatPublishedAt(detail.published_at)} · Vue pour la première fois le ${formatFirstSeenAt(detail.first_seen_at)}</p>
      <p>Cette offre n'a pas encore été traitée par l'orchestrateur — aucune analyse disponible pour le moment.</p>
    `;
    return;
  }

  const matchesHtml = detail.matches.length
    ? `<ul>${detail.matches.map((m) => `<li><strong>${escapeHtml(m.skill)}</strong> — ${escapeHtml(m.matched_chunk_summary)}</li>`).join("")}</ul>`
    : "<p>Aucun match identifié.</p>";
  const gapsHtml = detail.gaps.length
    ? `<ul>${detail.gaps.map((g) => `<li><strong>${escapeHtml(g.skill)}</strong> — ${escapeHtml(g.note)}</li>`).join("")}</ul>`
    : "<p>Aucun gap confirmé.</p>";
  const uncertainHtml = detail.uncertain_flags.length
    ? `<ul>${detail.uncertain_flags.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>`
    : "<p>Aucun flag incertain.</p>";

  panel.innerHTML = `
    <h2>${escapeHtml(detail.title)}</h2>
    ${originalOfferLinkHtml(detail)}
    <p class="detail-meta">${escapeHtml(detail.company || "—")} · ${zoneBadgeHtml(detail.geography_zone)} · ${sectorBadgeHtml(detail.sector)} · ${STATUS_LABELS[detail.status] || detail.status} · Publiée le ${formatPublishedAt(detail.published_at)} · Vue pour la première fois le ${formatFirstSeenAt(detail.first_seen_at)}</p>
    ${verdictButtonsHtml(detail.id, detail.user_verdict)}
    <dl>
      <dt>Score</dt>
      <dd>${detail.score === null || detail.score === undefined ? "—" : detail.score + " / 100"}</dd>
      <dt>Points forts (✓ ${detail.matches.length})</dt>
      <dd>${matchesHtml}</dd>
      <dt>Gaps confirmés (✕ ${detail.gaps.length})</dt>
      <dd>${gapsHtml}</dd>
      <dt>Flags incertains (? ${detail.uncertain_flags.length})</dt>
      <dd>${uncertainHtml}</dd>
    </dl>
    ${detail.analysis_markdown ? `<a class="full-link" href="/offers/${detail.id}" target="_blank" rel="noopener">Voir l'analyse complète (JSON, inclut le markdown brut) →</a>` : ""}
  `;
  wireDetailVerdictButtons(panel, detail.id);
}

function wireSortHeaders() {
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.classList.add("sortable");
    th.addEventListener("click", () => {
      if (currentSort.key === th.dataset.sort) currentSort.dir = currentSort.dir === "asc" ? "desc" : "asc";
      else currentSort = { key: th.dataset.sort, dir: "desc" };
      updateSortHeaders();
      renderTable();
    });
  });
}

// ---------------------------------------------------------------------
// Swipe view
// ---------------------------------------------------------------------

const detailCache = new Map(); // offer id -> full /offers/{id} payload
let swipeQueue = []; // remaining, untriaged, triageable offer summaries (score desc)
let swipeSessionTotal = 0;
let swipeSessionDone = 0;
let undoStack = []; // [{offer, previousVerdict}]
let dragState = null;

async function getDetail(offerId) {
  if (detailCache.has(offerId)) return detailCache.get(offerId);
  const detail = await fetchOfferDetail(offerId);
  detailCache.set(offerId, detail);
  return detail;
}

function buildSwipeQueue() {
  const remaining = allOffers.filter((o) => isTriageable(o) && !o.user_verdict);
  remaining.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  swipeQueue = remaining;
  swipeSessionTotal = remaining.length + swipeSessionDone; // preserves progress across a mid-session rebuild
  renderSwipeStack();
}

function swipeCardSkeleton(offer, depth) {
  return `
    <article class="swipe-card" data-offer-id="${offer.id}" data-depth="${depth}">
      <div class="swipe-card__stamp swipe-card__stamp--yes">OUI</div>
      <div class="swipe-card__stamp swipe-card__stamp--no">NON</div>
      <div class="swipe-card__stamp swipe-card__stamp--maybe">PEUT-ÊTRE</div>
      <div class="swipe-card__score" style="--score:${offer.score ?? 0}">
        <span class="swipe-card__score-num">${offer.score ?? "—"}</span>
      </div>
      <header class="swipe-card__head">
        <h2>${escapeHtml(offer.title)}</h2>
        <p class="swipe-card__company">${escapeHtml(offer.company || "—")}</p>
        <div class="swipe-card__badges">${zoneBadgeHtml(offer.geography_zone)}${sectorBadgeHtml(offer.sector)}${offer.status === "a_valider_geographie" ? '<span class="badge badge-amber">⚠️ Géo à valider</span>' : ""}</div>
      </header>
      <div class="swipe-card__body"><p class="loading">Chargement…</p></div>
    </article>
  `;
}

function fillSwipeCardBody(cardEl, detail) {
  const body = cardEl.querySelector(".swipe-card__body");
  const matches = detail.matches.slice(0, 4);
  const gaps = detail.gaps.slice(0, 4);
  const matchesHtml = matches.length
    ? `<ul>${matches.map((m) => `<li><strong>${escapeHtml(m.skill)}</strong><span>${escapeHtml(m.matched_chunk_summary)}</span></li>`).join("")}</ul>`
    : '<p class="swipe-card__empty-note">Aucun match identifié.</p>';
  const gapsHtml = gaps.length
    ? `<ul>${gaps.map((g) => `<li><strong>${escapeHtml(g.skill)}</strong><span>${escapeHtml(g.note)}</span></li>`).join("")}</ul>`
    : '<p class="swipe-card__empty-note">Aucun gap confirmé.</p>';
  body.innerHTML = `
    <div class="swipe-card__col"><h3>✓ Points forts (${detail.matches.length})</h3>${matchesHtml}</div>
    <div class="swipe-card__col"><h3>✕ Gaps (${detail.gaps.length})</h3>${gapsHtml}</div>
  `;
  const link = originalOfferLinkHtml(detail);
  if (link) cardEl.insertAdjacentHTML("beforeend", `<div class="swipe-card__link-wrap">${link.replace('class="original-offer-link"', 'class="swipe-card__link"')}</div>`);
}

function updateSwipeProgress() {
  const label = swipeQueue.length
    ? `${swipeSessionDone} triée(s) · ${swipeQueue.length} restante(s)`
    : `${swipeSessionDone} triée(s)`;
  document.getElementById("swipe-count").textContent = label;
  const pct = swipeSessionTotal > 0 ? Math.round((swipeSessionDone / swipeSessionTotal) * 100) : 0;
  document.getElementById("swipe-progress-bar").style.width = `${pct}%`;
  document.getElementById("btn-undo").disabled = undoStack.length === 0;
  const disableDecision = swipeQueue.length === 0;
  document.getElementById("btn-no").disabled = disableDecision;
  document.getElementById("btn-maybe").disabled = disableDecision;
  document.getElementById("btn-yes").disabled = disableDecision;
}

function renderSwipeStack() {
  const stage = document.getElementById("swipe-stage");
  stage.innerHTML = "";
  updateSwipeProgress();

  if (swipeQueue.length === 0) {
    stage.innerHTML = `
      <div class="swipe-empty">
        <div class="swipe-empty__emoji">🎉</div>
        <h2>Tout est trié !</h2>
        <p>Retrouve tes offres classées dans le tableau, filtrable par avis via les compteurs en haut de page.</p>
        <button type="button" class="verdict-pill" id="swipe-empty-to-table">Voir le tableau →</button>
      </div>
    `;
    document.getElementById("swipe-empty-to-table")?.addEventListener("click", () => setView("table"));
    return;
  }

  const visible = swipeQueue.slice(0, STACK_DEPTH);
  // Painted back-to-front so the top card (depth 0) is the last element in
  // the DOM and naturally receives pointer events first without an
  // explicit z-index dance beyond what the CSS already sets per depth.
  for (let i = visible.length - 1; i >= 0; i--) {
    stage.insertAdjacentHTML("afterbegin", swipeCardSkeleton(visible[i], i));
  }

  visible.forEach((offer) => {
    getDetail(offer.id).then((detail) => {
      const cardEl = stage.querySelector(`.swipe-card[data-offer-id="${offer.id}"]`);
      if (cardEl) fillSwipeCardBody(cardEl, detail);
    }).catch(() => {
      const cardEl = stage.querySelector(`.swipe-card[data-offer-id="${offer.id}"]`);
      if (cardEl) cardEl.querySelector(".swipe-card__body").innerHTML = '<p class="swipe-card__empty-note">Détail indisponible.</p>';
    });
  });

  wireTopCardDrag();
}

function topCardEl() {
  return document.querySelector('.swipe-card[data-depth="0"]');
}

// Sets stamp opacity + card tilt/translate from a raw (dx, dy) drag offset.
// Horizontal and vertical intents are mutually exclusive per frame (whichever
// axis currently dominates) so a diagonal drag doesn't flash two stamps at
// once — the user always sees exactly one clear verdict forming.
function applyDragVisuals(cardEl, dx, dy) {
  const rot = Math.max(-18, Math.min(18, dx / 12));
  cardEl.style.transform = `translate(${dx}px, ${dy * 0.4}px) rotate(${rot}deg)`;

  const horizontalWins = Math.abs(dx) >= Math.abs(dy);
  const yesStamp = cardEl.querySelector(".swipe-card__stamp--yes");
  const noStamp = cardEl.querySelector(".swipe-card__stamp--no");
  const maybeStamp = cardEl.querySelector(".swipe-card__stamp--maybe");

  yesStamp.style.opacity = horizontalWins && dx > 0 ? Math.min(1, dx / COMMIT_THRESHOLD_X) : 0;
  noStamp.style.opacity = horizontalWins && dx < 0 ? Math.min(1, -dx / COMMIT_THRESHOLD_X) : 0;
  maybeStamp.style.opacity = !horizontalWins && dy < 0 ? Math.min(1, -dy / COMMIT_THRESHOLD_Y) : 0;
}

function resolveDragVerdict(dx, dy) {
  const horizontalWins = Math.abs(dx) >= Math.abs(dy);
  if (horizontalWins && dx > COMMIT_THRESHOLD_X) return "interessante";
  if (horizontalWins && dx < -COMMIT_THRESHOLD_X) return "pas_interessante";
  if (!horizontalWins && dy < -COMMIT_THRESHOLD_Y) return "peut_etre";
  return null;
}

function flyOutTransform(verdict) {
  const far = window.innerWidth;
  if (verdict === "interessante") return `translate(${far}px, -40px) rotate(24deg)`;
  if (verdict === "pas_interessante") return `translate(-${far}px, -40px) rotate(-24deg)`;
  return "translate(0, -140vh) rotate(-4deg)"; // peut_etre
}

function wireTopCardDrag() {
  const card = topCardEl();
  if (!card) return;

  card.addEventListener("pointerdown", (e) => {
    card.setPointerCapture(e.pointerId);
    dragState = { startX: e.clientX, startY: e.clientY, dx: 0, dy: 0 };
  });

  card.addEventListener("pointermove", (e) => {
    if (!dragState) return;
    dragState.dx = e.clientX - dragState.startX;
    dragState.dy = e.clientY - dragState.startY;
    applyDragVisuals(card, dragState.dx, dragState.dy);
  });

  const release = () => {
    if (!dragState) return;
    const { dx, dy } = dragState;
    dragState = null;
    const verdict = resolveDragVerdict(dx, dy);
    if (verdict) commitTopCard(verdict);
    else snapBack(card);
  };

  card.addEventListener("pointerup", release);
  card.addEventListener("pointercancel", release);
}

function snapBack(card) {
  card.classList.add("is-settling");
  card.style.transform = "translate(0, 0) rotate(0deg)";
  card.querySelectorAll(".swipe-card__stamp").forEach((s) => (s.style.opacity = 0));
  card.addEventListener("transitionend", () => card.classList.remove("is-settling"), { once: true });
}

// Programmatic swipe (buttons + keyboard) — same commit path as a drag, so
// the deck always advances identically regardless of input method.
function swipeTop(verdict) {
  if (swipeQueue.length === 0) return;
  const card = topCardEl();
  if (card) {
    applyDragVisuals(card, verdict === "interessante" ? COMMIT_THRESHOLD_X : verdict === "pas_interessante" ? -COMMIT_THRESHOLD_X : 0, verdict === "peut_etre" ? -COMMIT_THRESHOLD_Y : 0);
  }
  commitTopCard(verdict);
}

async function commitTopCard(verdict) {
  const offer = swipeQueue[0];
  if (!offer) return;
  const card = topCardEl();

  if (card) {
    card.classList.add("is-flying");
    card.style.transform = flyOutTransform(verdict);
  }

  swipeQueue = swipeQueue.slice(1);
  swipeSessionDone += 1;
  undoStack.push({ offer, previousVerdict: null });
  updateSwipeProgress();

  // Let the fly-out animation play before the stack repaints — the peeking
  // cards behind should visibly slide into place, not just teleport.
  setTimeout(() => renderSwipeStack(), card ? 260 : 0);

  try {
    await applyVerdict(offer.id, verdict);
    renderStatStrip();
  } catch {
    // applyVerdict already rolled back allOffers and surfaced an error;
    // the card has already left the deck, so put it back at the front.
    swipeQueue = [offer, ...swipeQueue];
    swipeSessionDone -= 1;
    undoStack.pop();
    renderSwipeStack();
  }
}

async function undoLastSwipe() {
  const entry = undoStack.pop();
  if (!entry) return;
  try {
    await applyVerdict(entry.offer.id, entry.previousVerdict);
    renderStatStrip();
  } catch {
    undoStack.push(entry);
    return;
  }
  swipeQueue = [entry.offer, ...swipeQueue];
  swipeSessionDone = Math.max(0, swipeSessionDone - 1);
  renderSwipeStack();
}

function wireSwipeControls() {
  document.getElementById("btn-yes").addEventListener("click", () => swipeTop("interessante"));
  document.getElementById("btn-no").addEventListener("click", () => swipeTop("pas_interessante"));
  document.getElementById("btn-maybe").addEventListener("click", () => swipeTop("peut_etre"));
  document.getElementById("btn-undo").addEventListener("click", undoLastSwipe);

  document.addEventListener("keydown", (e) => {
    if (activeView !== "swipe") return;
    if (e.key === "ArrowRight") swipeTop("interessante");
    else if (e.key === "ArrowLeft") swipeTop("pas_interessante");
    else if (e.key === "ArrowUp") { e.preventDefault(); swipeTop("peut_etre"); }
    else if (e.key === "z" || e.key === "Z") undoLastSwipe();
  });
}

// ---------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------

async function init() {
  wireSortHeaders();
  wireViewSwitch();
  wireStatStrip();
  wireSwipeControls();
  document.getElementById("filter-zone").addEventListener("change", renderTable);
  document.getElementById("filter-status").addEventListener("change", renderTable);
  document.getElementById("filter-sector").addEventListener("change", renderTable);

  try {
    allOffers = await fetchOffers();
  } catch (err) {
    showError(`Impossible de charger les offres depuis l'API (${err.message}). Vérifiez que le serveur FastAPI est démarré.`);
    document.getElementById("offers-body").innerHTML = '<tr><td colspan="10" class="empty">—</td></tr>';
    return;
  }

  populateFilterOptions(allOffers);
  updateSortHeaders();
  renderStatStrip();
  setView(activeView); // renders the table itself when activeView === "table"
}

init();
