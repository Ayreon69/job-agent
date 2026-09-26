// Display helpers: labels, dates, text cleanup. Pure functions, no DOM state.

export const ZONE_LABELS = {
  suisse_romande: "Suisse romande",
  rhone_alpes: "Rhône-Alpes",
  uae_gcc: "UAE / GCC",
  suisse_autre: "Suisse (autre)",
  autre_france: "Autre France",
  inconnu: "Zone inconnue",
};

// Order used wherever zones are listed — mirrors the targeting priorities of
// scoring/geography.py rather than an alphabetical order.
export const ZONE_ORDER = ["suisse_romande", "rhone_alpes", "uae_gcc", "suisse_autre", "autre_france", "inconnu"];

export const SOURCE_LABELS = { hellowork: "Hellowork", jobup: "jobup.ch" };

export const STATUS_LABELS = {
  nouveau: "En attente d'analyse",
  analyse: "Analysée",
  a_valider_geographie: "Géographie à valider",
  echec: "Échec du pipeline",
};

export const VERDICTS = ["interessante", "peut_etre", "pas_interessante"];
export const VERDICT_META = {
  interessante: { label: "Intéressante", short: "Oui", icon: "i-heart", key: "1" },
  peut_etre: { label: "Peut-être", short: "Peut-être", icon: "i-star", key: "2" },
  pas_interessante: { label: "Pas pour moi", short: "Non", icon: "i-x", key: "3" },
};

// Only offers with an actual analysis can be judged; 'nouveau' and 'echec'
// have nothing to decide on yet.
const TRIAGEABLE = new Set(["analyse", "a_valider_geographie"]);
export const isTriageable = (o) => TRIAGEABLE.has(o.status);

export function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export const icon = (id, cls = "") => `<svg class="icon ${cls}" aria-hidden="true"><use href="#${id}"/></svg>`;

// ---------------------------------------------------------------------
// Score
// ---------------------------------------------------------------------

// Bands are only a reading aid on top of the pipeline's own 0-100 score —
// nothing is re-weighted here, the number shown is always the raw score.
export function scoreTier(score) {
  if (score === null || score === undefined) return "none";
  if (score >= 80) return "hot";
  if (score >= 65) return "warm";
  if (score >= 50) return "mild";
  return "cold";
}

export const TIER_LABELS = { hot: "Très pertinente", warm: "Pertinente", mild: "Partielle", cold: "Faible", none: "Non scorée" };

export function scoreRing(score, size = 56, stroke = 5) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score ?? 0)) / 100;
  const tier = scoreTier(score);
  return `
    <svg class="ring ring--${tier}" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="Score ${score ?? "non disponible"} sur 100">
      <circle class="ring__track" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}"/>
      <circle class="ring__value" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}"
        stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - pct)}" style="--c:${c}"
        transform="rotate(-90 ${size / 2} ${size / 2})"/>
      <text class="ring__num" x="50%" y="52%" dominant-baseline="central" text-anchor="middle" font-size="${Math.round(size * 0.36)}">${score ?? "–"}</text>
    </svg>`;
}

// ---------------------------------------------------------------------
// Dates
// ---------------------------------------------------------------------

const MOIS_FR = {
  janvier: 1, "février": 2, fevrier: 2, mars: 3, avril: 4, mai: 5, juin: 6, juillet: 7,
  "août": 8, aout: 8, septembre: 9, octobre: 10, novembre: 11, "décembre": 12, decembre: 12,
};

// jobs.published_at is stored as each source words it (Hellowork
// "DD/MM/YYYY", jobup "DD mois AAAA") — same parsing as storage/db.py's
// parse_published_at, so the UI can show one consistent format.
export function parsePublished(raw) {
  if (!raw) return null;
  const s = raw.trim();
  let m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) return new Date(Date.UTC(+m[3], +m[2] - 1, +m[1]));
  m = s.match(/^(\d{1,2})\s+([a-zéû]+)\s+(\d{4})$/i);
  if (m && MOIS_FR[m[2].toLowerCase()]) return new Date(Date.UTC(+m[3], MOIS_FR[m[2].toLowerCase()] - 1, +m[1]));
  return null;
}

// SQLite datetime('now') strings are UTC without a zone marker.
export function parseSqlUtc(raw) {
  if (!raw) return null;
  const d = new Date(raw.replace(" ", "T") + "Z");
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDate(date, opts = { day: "numeric", month: "short", year: "numeric" }) {
  return date ? date.toLocaleDateString("fr-FR", opts) : "—";
}

export function fmtTime(date) {
  return date ? date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : "—";
}

const DAY = 86400000;

export function startOfDay(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

// "aujourd'hui", "hier", "il y a 4 j", "il y a 3 sem." — calendar-day based,
// so an offer seen at 23:50 yesterday still reads "hier" at 00:10.
export function relDay(date, now = new Date()) {
  if (!date) return "—";
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY);
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return "hier";
  if (days < 14) return `il y a ${days} j`;
  if (days < 60) return `il y a ${Math.round(days / 7)} sem.`;
  return `il y a ${Math.round(days / 30)} mois`;
}

export function relTime(date, now = new Date()) {
  if (!date) return "—";
  const mins = Math.round((now - date) / 60000);
  if (mins < 1) return "à l'instant";
  if (mins < 60) return `il y a ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `il y a ${hours} h`;
  return relDay(date, now);
}

export function offerAgeDays(o, now = new Date()) {
  const d = parsePublished(o.published_at) || parseSqlUtc(o.first_seen_at);
  return d ? Math.max(0, Math.round((startOfDay(now) - startOfDay(d)) / DAY)) : null;
}

// ---------------------------------------------------------------------
// Offer fields
// ---------------------------------------------------------------------

export function cleanSalary(raw) {
  if (!raw) return null;
  const s = raw.replace(/ | /g, " ").replace(/\s+/g, " ").trim();
  if (/pas de salaire|non (communiqué|renseigné)/i.test(s)) return null;
  return s;
}

// Annual amount in the stated currency, for charts only (never shown as a
// fact): "57 500 € / an" -> {value: 57500, cur: "EUR"}; CHF monthly ranges
// are annualised x12 on their midpoint. Anything else -> null.
export function salaryAnnual(raw) {
  const s = cleanSalary(raw);
  if (!s) return null;
  const nums = [...s.matchAll(/(\d[\d ]*\d|\d)/g)].map((m) => Number(m[1].replace(/ /g, ""))).filter((n) => n > 100);
  if (!nums.length) return null;
  const mid = nums.length > 1 ? (nums[0] + nums[1]) / 2 : nums[0];
  const cur = /CHF/i.test(s) ? "CHF" : /€|EUR/i.test(s) ? "EUR" : null;
  if (!cur) return null;
  const monthly = /mois/i.test(s);
  const value = monthly ? mid * 12 : mid;
  if (value < 15000 || value > 400000) return null;
  return { value, cur };
}

export function cleanContract(raw) {
  if (!raw) return null;
  if (raw === "Durée indéterminée") return "CDI";
  if (raw === "Temporaire") return "CDD / temporaire";
  return raw;
}

export function cleanExperience(raw) {
  if (!raw) return null;
  return raw.replace(/^Exp\.\s*/i, "").replace(/\bmin\.$/, "minimum");
}

// Some legacy jobup rows carry a UI widget label instead of the company
// (fixed in scraper/jobup.py; rows heal on their next re-scrape).
const COMPANY_ARTIFACTS = new Set(["Offre pertinente ?"]);
export function cleanCompany(raw) {
  if (!raw || COMPANY_ARTIFACTS.has(raw.trim())) return null;
  return raw.trim();
}

export const companyOf = (o) => cleanCompany(o.company) || "Entreprise non précisée";

// "Data Analyst H/F", "Data Scientist (F/H)", "Ingénieur - H/F/X": the
// gender marker is legally required on French listings but carries no
// information for triage — dropped for display only (search still sees
// the raw title).
const GENDER_MARK = /\s*[-–—,]?\s*\(?\b(?:h\s*\/\s*f|f\s*\/\s*h|m\s*\/\s*f|f\s*\/\s*m|w\s*\/\s*m|m\s*\/\s*w)(?:\s*\/\s*[xd])?\b\)?(?=\s|$|[-–—,.)])/gi;
export function titleOf(o) {
  const t = (o.title || "").replace(GENDER_MARK, "").replace(/\s{2,}/g, " ").replace(/[\s\-–—,]+$/, "").trim();
  return t || o.title || "";
}

// Probable duplicates: same cleaned title + same place (+ same company when
// known). Sources re-publish the same position under new ids; flagged, not
// hidden — they might genuinely be two openings.
export function duplicateKey(o) {
  return [fold(titleOf(o)), fold(locationOf(o) || ""), fold(cleanCompany(o.company) || "")].join("|");
}

export function locationOf(o) {
  return o.location ? o.location.replace(/\s*-\s*\d{2,3}$/, "") : null;
}

// ---------------------------------------------------------------------
// Description: strip source UI noise, then give it light structure
// ---------------------------------------------------------------------

// jobup's description block includes its own AI-summary widget chrome and
// personalised "match" teasers — none of it is offer content.
const NOISE_LINES = [
  /^afficher$/i, /^est-ce utile ?\?$/i, /^voir mon match$/i, /^voir l[’']original$/i,
  /^l[’']aperçu a été créé à l[’']aide de l[’']ia$/i, /^vous correspondez/i,
  /^ce poste est-il fait pour vous/i, /^cette offre d[’']emploi a été traduite/i,
  /\.\.\.$/, /^résumé de l[’']emploi$/i, /^à propos de cette offre$/i, /^postuler$/i, /^voir plus$/i,
];

export function cleanDescription(text) {
  if (!text) return "";
  const lines = text.replace(/\r/g, "").split("\n").map((l) => l.trim());
  const kept = lines.filter((l) => !NOISE_LINES.some((re) => re.test(l)));
  // collapse duplicate consecutive lines and runs of blank lines
  const out = [];
  for (const l of kept) {
    if (l === "" && (out.length === 0 || out[out.length - 1] === "")) continue;
    if (l !== "" && out[out.length - 1] === l) continue;
    out.push(l);
  }
  return out.join("\n").trim();
}

const looksLikeHeading = (l) =>
  l.length <= 48 && !/[.;,]$/.test(l) && !/^[-•·*]/.test(l) && /^[A-ZÀ-Ý]/.test(l) && l.split(" ").length <= 7;

// Turns the cleaned plain text into headings / paragraphs / lists. Heuristic
// but conservative: when unsure, a line stays a plain paragraph.
export function descriptionHtml(text) {
  const clean = cleanDescription(text);
  if (!clean) return '<p class="muted">Pas de description récupérée pour cette offre.</p>';
  // Every line becomes one item; blank lines only matter as separators.
  const lines = clean.split("\n").map((l) => l.replace(/^[-•·*▪]\s*/, "").trim());
  const html = [];
  let list = [];
  let listMode = false; // true right after a heading ending with ":" (or a
  // block of consecutive short lines) — its short lines read as bullets.
  const flush = () => {
    if (list.length) html.push(`<ul>${list.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`);
    list = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (!l) continue;
    const bare = l.replace(/\s*:$/, "");
    const hasNext = lines.slice(i + 1).some(Boolean);
    if (looksLikeHeading(bare) && hasNext) {
      flush();
      html.push(`<h4>${esc(bare)}</h4>`);
      listMode = /:$/.test(l) || lines[i + 1] !== ""; // "Tâches\nConcevoir…" packs items right under it
      continue;
    }
    if (listMode && l.length < 240) {
      list.push(l);
      continue;
    }
    flush();
    listMode = false;
    html.push(`<p>${esc(l)}</p>`);
  }
  flush();
  return html.join("");
}

export function excerpt(text, max = 320) {
  const clean = cleanDescription(text)
    .split("\n")
    .filter((l) => l && !looksLikeHeading(l.replace(/\s*:$/, "")))
    .join(" ");
  if (clean.length <= max) return clean;
  return clean.slice(0, clean.lastIndexOf(" ", max)).replace(/[\s,;:.…]+$/, "") + "…";
}

// Accent/case-insensitive haystack for search.
export const fold = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export function searchText(o) {
  return fold([o.title, cleanCompany(o.company), o.location, o.sector, ZONE_LABELS[o.geography_zone], SOURCE_LABELS[o.source], o.contract_type].join(" "));
}

export const plural = (n, one, many) => `${n} ${n > 1 ? many : one}`;
