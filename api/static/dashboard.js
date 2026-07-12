// job-agent dashboard (session 9): thin display layer over GET /offers and
// GET /offers/{id}. No scoring/business logic here — every value shown is
// exactly what the API already returns (see api/main.py, api/schemas.py).

const ZONE_LABELS = {
  suisse_romande: "Suisse romande",
  rhone_alpes: "Rhône-Alpes",
  uae_gcc: "UAE / GCC",
  suisse_autre: "Suisse (autre)",
  autre_france: "Autre France",
  inconnu: "Inconnu",
};

// Priority zones (suisse_romande, uae_gcc — see CLAUDE.md priority order)
// and the pragmatic fallback (rhone_alpes, suisse_autre, autre_france) all
// read as a confidently-classified zone: green. Only "inconnu" is amber —
// it's the one case flagged a_valider_geographie by the orchestrator
// (session 5), i.e. genuinely needing a human look, not just "lower
// priority".
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

let allOffers = [];
let currentSort = { key: "score", dir: "desc" };
let expandedOfferId = null; // accordion: at most one offer's detail row open at a time

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

function showError(message) {
  const banner = document.getElementById("error-banner");
  banner.textContent = message;
  banner.hidden = false;
}

function populateFilterOptions(offers) {
  const zoneSelect = document.getElementById("filter-zone");
  const statusSelect = document.getElementById("filter-status");

  const zones = [...new Set(offers.map((o) => o.geography_zone).filter(Boolean))];
  for (const zone of zones) {
    const opt = document.createElement("option");
    opt.value = zone;
    opt.textContent = ZONE_LABELS[zone] || zone;
    zoneSelect.appendChild(opt);
  }

  const statuses = [...new Set(offers.map((o) => o.status).filter(Boolean))];
  for (const status of statuses) {
    const opt = document.createElement("option");
    opt.value = status;
    opt.textContent = STATUS_LABELS[status] || status;
    statusSelect.appendChild(opt);
  }
}

function applyFilters(offers) {
  const zone = document.getElementById("filter-zone").value;
  const status = document.getElementById("filter-status").value;
  return offers.filter(
    (o) => (!zone || o.geography_zone === zone) && (!status || o.status === status)
  );
}

function sortOffers(offers) {
  const { key, dir } = currentSort;
  const sorted = [...offers].sort((a, b) => {
    let av = a[key];
    let bv = b[key];
    // Null score/zone sort last regardless of direction — an unscored
    // offer isn't "worse", it's simply not comparable yet.
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    if (typeof av === "string") av = av.toLowerCase();
    if (typeof bv === "string") bv = bv.toLowerCase();
    if (av < bv) return dir === "asc" ? -1 : 1;
    if (av > bv) return dir === "asc" ? 1 : -1;
    return 0;
  });
  return sorted;
}

function zoneBadgeHtml(zone) {
  if (!zone) return '<span class="badge badge-gray">—</span>';
  const cls = ZONE_BADGE_CLASS[zone] || "badge-gray";
  const label = ZONE_LABELS[zone] || zone;
  return `<span class="badge ${cls}">${escapeHtml(label)}</span>`;
}

function flagsHtml(offer) {
  if (offer.gaps_count === null || offer.gaps_count === undefined) return "—";
  const parts = [];
  if (offer.gaps_count > 0) parts.push(`<span class="gap-count">✕ ${offer.gaps_count}</span>`);
  if (offer.uncertain_count > 0) parts.push(`<span class="uncertain-count">? ${offer.uncertain_count}</span>`);
  if (parts.length === 0) parts.push("aucun");
  return parts.join(" · ");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Renders **bold** markdown spans as <strong> — the analysis_markdown link
// target still contains LLM-generated **label** emphasis (see
// generation/analysis.py's prompt). Not a full markdown renderer, just
// enough so raw "**" characters don't leak into the UI where used.
function escapeAndBold(str) {
  const escaped = escapeHtml(str);
  return escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderTable() {
  const filtered = applyFilters(allOffers);
  const sorted = sortOffers(filtered);
  const tbody = document.getElementById("offers-body");
  document.getElementById("offer-count").textContent = `${sorted.length} offre(s)`;

  // A filter/sort change can remove the currently-expanded offer from view
  // (or reorder it) — the accordion row is rebuilt fresh below in its new
  // position if the offer is still visible, so there's nothing stale to
  // clean up here; just don't error if it's gone.
  if (sorted.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">Aucune offre ne correspond aux filtres.</td></tr>';
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
      <td>${offer.score === null || offer.score === undefined ? "—" : offer.score}</td>
      <td>${STATUS_LABELS[offer.status] || offer.status}</td>
      <td class="flags">${flagsHtml(offer)}</td>
    `;
    tr.addEventListener("click", () => selectOffer(offer.id));
    tbody.appendChild(tr);

    // Accordion (session 9 follow-up): the detail row is inserted directly
    // after the offer's own row, in-place, rather than in a fixed panel at
    // the bottom of the page — with 67 offers, a bottom panel meant
    // scrolling all the way down after every click to see the result.
    if (offer.id === expandedOfferId) {
      const detailTr = document.createElement("tr");
      detailTr.className = "detail-row";
      detailTr.dataset.detailFor = offer.id;
      const td = document.createElement("td");
      td.colSpan = 6;
      td.innerHTML = '<div class="detail-panel"><p class="loading">Chargement du détail…</p></div>';
      detailTr.appendChild(td);
      tbody.appendChild(detailTr);
    }
  }
}

function updateSortHeaders() {
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.sort === currentSort.key) {
      th.classList.add(currentSort.dir === "asc" ? "sorted-asc" : "sorted-desc");
    }
  });
}

async function selectOffer(offerId) {
  // Accordion toggle: clicking the already-open row closes it; clicking any
  // other row closes whatever was open (if anything) and opens the new one
  // at ITS position — never two detail rows open at once.
  expandedOfferId = expandedOfferId === offerId ? null : offerId;
  renderTable();

  if (expandedOfferId === null) return;

  const detailTr = document.querySelector(`tr.detail-row[data-detail-for="${expandedOfferId}"]`);
  if (!detailTr) return; // offer scrolled out of the current filter/sort view
  const panel = detailTr.querySelector(".detail-panel");

  try {
    const detail = await fetchOfferDetail(expandedOfferId);
    // The user may have toggled again (or re-filtered) while the fetch was
    // in flight — only render into the row if it's still the open one.
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

function renderDetail(panel, detail) {
  if (detail.status === "nouveau") {
    panel.innerHTML = `
      <h2>${escapeHtml(detail.title)}</h2>
      ${originalOfferLinkHtml(detail)}
      <p class="detail-meta">${escapeHtml(detail.company || "—")} · ${zoneBadgeHtml(detail.geography_zone)} · ${STATUS_LABELS[detail.status]}</p>
      <p>Cette offre n'a pas encore été traitée par l'orchestrateur — aucune analyse disponible pour le moment.</p>
    `;
    return;
  }

  // matches/gaps/uncertain_flags now come structured from the API (session 9
  // follow-up: generation/analysis.py's StructuredAnalysis, a faithful
  // Python-side mirror of ScoringResult — not re-parsed from the markdown
  // anymore). Each match/gap item carries its own short justification, so
  // the dashboard can show a real matching summary instead of the old
  // single "first bullet of prose" hack.
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
    <p class="detail-meta">${escapeHtml(detail.company || "—")} · ${zoneBadgeHtml(detail.geography_zone)} · ${STATUS_LABELS[detail.status] || detail.status}</p>
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
    ${
      detail.analysis_markdown
        ? `<a class="full-link" href="/offers/${detail.id}" target="_blank" rel="noopener">Voir l'analyse complète (JSON, inclut le markdown brut) →</a>`
        : ""
    }
  `;
}

function wireSortHeaders() {
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.classList.add("sortable");
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (currentSort.key === key) {
        currentSort.dir = currentSort.dir === "asc" ? "desc" : "asc";
      } else {
        currentSort = { key, dir: "desc" };
      }
      updateSortHeaders();
      renderTable();
    });
  });
}

async function init() {
  wireSortHeaders();
  document.getElementById("filter-zone").addEventListener("change", renderTable);
  document.getElementById("filter-status").addEventListener("change", renderTable);

  try {
    allOffers = await fetchOffers();
  } catch (err) {
    showError(`Impossible de charger les offres depuis l'API (${err.message}). Vérifiez que le serveur FastAPI est démarré.`);
    document.getElementById("offers-body").innerHTML = '<tr><td colspan="6" class="empty">—</td></tr>';
    return;
  }

  populateFilterOptions(allOffers);
  updateSortHeaders();
  renderTable();
}

init();
