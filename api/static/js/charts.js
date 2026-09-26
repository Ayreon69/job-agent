// Hand-rolled SVG/HTML charts — no charting library, every mark is a plain
// element with a data-tip tooltip (see ui.js wireTooltips).

import { esc, fmtDate, scoreTier, startOfDay, ZONE_LABELS, ZONE_ORDER, salaryAnnual, TIER_LABELS, titleOf } from "./format.js";

const DAY = 86400000;

const median = (arr) => {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const mean = (arr) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null);

// ---------------------------------------------------------------------
// Arrivals per day (first_seen_at), stacked: strong matches on top
// ---------------------------------------------------------------------
export function arrivalsChart(offers, days = 30, now = new Date()) {
  const end = startOfDay(now);
  const buckets = Array.from({ length: days }, (_, i) => ({ date: new Date(end.getTime() - (days - 1 - i) * DAY), total: 0, hot: 0 }));
  for (const o of offers) {
    if (!o._firstSeen) continue;
    const idx = days - 1 - Math.round((end - startOfDay(o._firstSeen)) / DAY);
    if (idx < 0 || idx >= days) continue;
    buckets[idx].total += 1;
    if ((o.score ?? 0) >= 80) buckets[idx].hot += 1;
  }

  // A one-off backlog day (e.g. the 2026-09-17 catch-up after the pipeline
  // outage) would flatten every other bar — cap the scale at 1.4x the
  // second-highest day and draw the outlier with a break mark + its real
  // value, rather than hiding or rescaling it silently.
  const sorted = buckets.map((b) => b.total).sort((a, b) => b - a);
  const cap = sorted[1] > 0 && sorted[0] > sorted[1] * 2 ? Math.ceil(sorted[1] * 1.4) : sorted[0] || 1;

  const W = 640, H = 190, padL = 28, padR = 8, padT = 16, padB = 26;
  const iw = W - padL - padR, ih = H - padT - padB;
  const bw = iw / days;
  const y = (v) => padT + ih - (Math.min(v, cap) / cap) * ih;

  const gridVals = niceTicks(cap, 3);
  const grid = gridVals
    .map((v) => `<line class="ch-grid" x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}"/><text class="ch-axis" x="${padL - 6}" y="${y(v)}" text-anchor="end" dominant-baseline="central">${v}</text>`)
    .join("");

  const bars = buckets
    .map((b, i) => {
      const x = padL + i * bw + bw * 0.16;
      const w = bw * 0.68;
      const overflow = b.total > cap;
      const hTot = padT + ih - y(b.total);
      const hHot = Math.min(hTot, (b.hot / cap) * ih);
      const tip = `<b>${fmtDate(b.date, { weekday: "short", day: "numeric", month: "short" })}</b><br>${b.total} offre(s) vue(s)<br><span class='tip-hot'>${b.hot} à 80+</span>`;
      const isToday = i === days - 1;
      return `
        <g class="ch-bar ${isToday ? "is-today" : ""}" data-tip="${esc(tip)}" style="--i:${i}">
          <rect class="ch-hit" x="${padL + i * bw}" y="${padT}" width="${bw}" height="${ih}"/>
          ${b.total ? `<rect class="ch-total" x="${x}" y="${y(b.total)}" width="${w}" height="${hTot}" rx="2"/>` : ""}
          ${b.hot ? `<rect class="ch-hot" x="${x}" y="${padT + ih - hHot}" width="${w}" height="${hHot}" rx="2"/>` : ""}
          ${overflow ? `<path class="ch-break" d="M${x - 2} ${padT + 9} l${w + 4} -5 M${x - 2} ${padT + 14} l${w + 4} -5"/><text class="ch-over" x="${x + w / 2}" y="${padT - 4}" text-anchor="middle">${b.total}</text>` : ""}
        </g>`;
    })
    .join("");

  const labels = buckets
    .map((b, i) => (i % 7 === (days - 1) % 7 ? `<text class="ch-axis" x="${padL + i * bw + bw / 2}" y="${H - 8}" text-anchor="middle">${i === days - 1 ? "auj." : fmtDate(b.date, { day: "numeric", month: "short" })}</text>` : ""))
    .join("");

  return `<svg class="chart chart--arrivals" viewBox="0 0 ${W} ${H}" role="img" aria-label="Offres découvertes par jour sur ${days} jours">${grid}${bars}${labels}</svg>`;
}

function niceTicks(max, count) {
  const raw = max / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
  const out = [];
  for (let v = step; v <= max; v += step) out.push(Math.round(v));
  return out;
}

// ---------------------------------------------------------------------
// Score distribution + where the user's own "interessante" picks fall
// ---------------------------------------------------------------------
export function scoreHistogram(offers) {
  const scored = offers.filter((o) => o.score !== null && o.score !== undefined);
  const bins = Array.from({ length: 10 }, (_, i) => ({ lo: i * 10, hi: i === 9 ? 100 : i * 10 + 9, n: 0, yes: 0, no: 0 }));
  for (const o of scored) {
    const b = bins[Math.min(9, Math.floor(o.score / 10))];
    b.n += 1;
    if (o.user_verdict === "interessante") b.yes += 1;
    if (o.user_verdict === "pas_interessante") b.no += 1;
  }
  const max = Math.max(1, ...bins.map((b) => b.n));
  const W = 640, H = 190, padL = 8, padR = 8, padT = 18, padB = 26;
  const iw = W - padL - padR, ih = H - padT - padB;
  const bw = iw / bins.length;
  const med = median(scored.map((o) => o.score));

  const bars = bins
    .map((b, i) => {
      const h = (b.n / max) * ih;
      const x = padL + i * bw + 4;
      const w = bw - 8;
      const tier = scoreTier(b.lo + 5);
      const tip = `<b>Score ${b.lo}–${b.hi}</b><br>${b.n} offre(s)${b.yes ? `<br><span class='tip-yes'>${b.yes} jugée(s) intéressante(s)</span>` : ""}${b.no ? `<br><span class='tip-no'>${b.no} écartée(s)</span>` : ""}`;
      return `
        <g class="ch-bar" data-tip="${esc(tip)}" style="--i:${i}">
          <rect class="ch-hit" x="${padL + i * bw}" y="${padT}" width="${bw}" height="${ih}"/>
          <rect class="ch-tier ch-tier--${tier}" x="${x}" y="${padT + ih - h}" width="${w}" height="${Math.max(h, b.n ? 2 : 0)}" rx="3"/>
          ${b.n ? `<text class="ch-val" x="${x + w / 2}" y="${padT + ih - h - 5}" text-anchor="middle">${b.n}</text>` : ""}
          ${b.yes ? `<circle class="ch-pick" cx="${x + w / 2}" cy="${padT + ih - 8}" r="4.2"/>` : ""}
          <text class="ch-axis" x="${padL + i * bw + bw / 2}" y="${H - 8}" text-anchor="middle">${b.lo}</text>
        </g>`;
    })
    .join("");

  const medX = med === null ? null : padL + (med / 100) * iw;
  const medLine = medX === null ? "" : `<line class="ch-median" x1="${medX}" x2="${medX}" y1="${padT - 6}" y2="${padT + ih}"/>`;
  return `<svg class="chart chart--hist" viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribution des scores, médiane ${Math.round(med ?? 0)}">${medLine}${bars}</svg>`;
}

// ---------------------------------------------------------------------
// Horizontal bar lists (zones, sectors): count + average score
// ---------------------------------------------------------------------
function barList(rows, { onClick } = {}) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  return `<ul class="barlist">${rows
    .map(
      (r, i) => `
      <li style="--i:${i}">
        <button type="button" class="barlist__row" ${onClick ? `data-filter-kind="${esc(r.kind)}" data-filter-value="${esc(r.value)}"` : ""} data-tip="${esc(`<b>${esc(r.label)}</b><br>${r.n} offre(s) · score moyen ${r.avg === null ? "–" : Math.round(r.avg)}${r.hot ? `<br><span class='tip-hot'>${r.hot} à 80+</span>` : ""}`)}">
          <span class="barlist__label">${esc(r.label)}</span>
          <span class="barlist__track"><span class="barlist__fill" style="--w:${(r.n / max) * 100}%"></span><span class="barlist__hot" style="--w:${(r.hot / max) * 100}%"></span></span>
          <span class="barlist__n">${r.n}</span>
          <span class="barlist__avg score-pill score-pill--${scoreTier(r.avg)}">${r.avg === null ? "–" : Math.round(r.avg)}</span>
        </button>
      </li>`
    )
    .join("")}</ul>`;
}

function groupStats(offers, keyFn) {
  const map = new Map();
  for (const o of offers) {
    const k = keyFn(o);
    if (!k) continue;
    if (!map.has(k)) map.set(k, { n: 0, scores: [], hot: 0 });
    const g = map.get(k);
    g.n += 1;
    if (o.score !== null && o.score !== undefined) g.scores.push(o.score);
    if ((o.score ?? 0) >= 80) g.hot += 1;
  }
  return map;
}

export function zoneBars(offers) {
  const g = groupStats(offers, (o) => o.geography_zone);
  const rows = ZONE_ORDER.filter((z) => g.has(z)).map((z) => ({
    kind: "zone", value: z, label: ZONE_LABELS[z], n: g.get(z).n, hot: g.get(z).hot, avg: mean(g.get(z).scores),
  }));
  return barList(rows, { onClick: true });
}

export function sectorBars(offers, top = 7) {
  const g = groupStats(offers, (o) => o.sector);
  const rows = [...g.entries()]
    .map(([k, v]) => ({ kind: "sector", value: k, label: k, n: v.n, hot: v.hot, avg: mean(v.scores) }))
    .sort((a, b) => b.n - a.n || (b.avg ?? 0) - (a.avg ?? 0));
  return barList(rows.slice(0, top), { onClick: true });
}

// ---------------------------------------------------------------------
// Salary strip: one dot per offer that states a salary, per currency —
// EUR (France, annual) and CHF (Suisse, monthly x12). Never mixed on one
// axis, since converting currencies would be an invented number.
// ---------------------------------------------------------------------
export function salaryStrips(offers) {
  const rows = { EUR: [], CHF: [] };
  for (const o of offers) {
    const s = salaryAnnual(o.salary);
    if (s && rows[s.cur]) rows[s.cur].push({ v: s.value, o });
  }
  const strip = (cur, items) => {
    if (items.length < 3) return "";
    const vals = items.map((i) => i.v);
    const lo = Math.floor(Math.min(...vals) / 10000) * 10000;
    const hi = Math.ceil(Math.max(...vals) / 10000) * 10000;
    const W = 1100, H = 70, pad = 18;
    const x = (v) => pad + ((v - lo) / (hi - lo || 1)) * (W - pad * 2);
    const med = median(vals);
    // light jitter so identical salaries (same employer template) stay visible
    const dots = items
      .map(({ v, o }, i) => {
        const jitter = ((i * 37) % 17) - 8;
        return `<circle class="salary-dot salary-dot--${scoreTier(o.score)}" cx="${x(v)}" cy="${30 + jitter}" r="6.5" data-offer-id="${o.id}" data-tip="${esc(`<b>${esc(titleOf(o))}</b><br>${Math.round(v / 1000)}k ${cur}/an · score ${o.score ?? "–"}`)}"/>`;
      })
      .join("");
    const ticks = [];
    for (let v = lo; v <= hi; v += (hi - lo) / 4) ticks.push(`<text class="ch-axis" x="${x(v)}" y="${H - 4}" text-anchor="middle">${Math.round(v / 1000)}k</text>`);
    return `
      <div class="salary-strip">
        <div class="salary-strip__head"><b>${cur === "EUR" ? "France · € brut/an" : "Suisse · CHF/an (mensuel ×12)"}</b><span>${items.length} offres · médiane <b>${Math.round(med / 1000)}k</b></span></div>
        <svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Salaires annoncés en ${cur}">
          <line class="ch-grid" x1="${pad}" x2="${W - pad}" y1="30" y2="30"/>
          <line class="ch-median" x1="${x(med)}" x2="${x(med)}" y1="8" y2="48"/>
          ${dots}${ticks.join("")}
        </svg>
      </div>`;
  };
  const html = strip("EUR", rows.EUR) + strip("CHF", rows.CHF);
  return html || '<p class="muted">Trop peu d\'offres affichent un salaire pour en tirer quoi que ce soit.</p>';
}

// ---------------------------------------------------------------------
// Radar: every offer still waiting for a verdict is a blip. Distance from
// the centre = 100 - score (the best offers sit in the bullseye), angle is
// a stable hash of the id — it carries no meaning, it only spreads the
// blips out. Rings mark the same 80 / 65 / 50 bands as the score pills.
// ---------------------------------------------------------------------
export function radar(offers, isNew) {
  const S = 400, C = S / 2, R = 180;
  // sqrt spreads the crowded 60-90 band instead of piling it in the bullseye
  const rOf = (score) => 16 + Math.sqrt((100 - Math.max(0, Math.min(100, score))) / 100) * (R - 16);
  const angle = (id) => {
    let h = 2166136261;
    for (const ch of String(id * 2654435761)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
    return ((h >>> 0) % 3600) / 10;
  };
  const rings = [80, 65, 50, 0]
    .map((s) => `<circle class="radar__ring ${s ? "" : "radar__ring--outer"}" cx="${C}" cy="${C}" r="${rOf(s)}"/>${s ? `<text class="radar__label" x="${C + 4}" y="${C - rOf(s) - 4}">${s}</text>` : ""}`)
    .join("");
  const blips = offers
    .filter((o) => o.score !== null && o.score !== undefined)
    .sort((a, b) => a.score - b.score)
    .map((o, i) => {
      const a = (angle(o.id) * Math.PI) / 180;
      const r = rOf(o.score);
      const x = C + Math.cos(a) * r;
      const y = C + Math.sin(a) * r;
      const fresh = isNew(o);
      const tip = `<b>${esc(titleOf(o))}</b><br>score ${o.score}${fresh ? " · <span class='tip-hot'>nouvelle</span>" : ""}`;
      return `<circle class="radar__blip radar__blip--${scoreTier(o.score)} ${fresh ? "is-new" : ""}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${fresh ? 5 : 3.2}" data-offer-id="${o.id}" data-tip="${esc(tip)}" style="--i:${i % 40}; --a:${angle(o.id)}deg"/>`;
    })
    .join("");
  return `
    <svg class="radar" viewBox="0 0 ${S} ${S}" role="img" aria-label="Radar des offres en attente : plus un point est proche du centre, meilleur est son score">
      <defs>
        <radialGradient id="radar-bg"><stop offset="0" stop-color="var(--accent)" stop-opacity="0.16"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></radialGradient>
        <linearGradient id="radar-sweep" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="var(--accent)" stop-opacity="0"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0.35"/></linearGradient>
      </defs>
      <circle cx="${C}" cy="${C}" r="${R}" fill="url(#radar-bg)"/>
      ${rings}
      <line class="radar__axis" x1="${C - R}" y1="${C}" x2="${C + R}" y2="${C}"/>
      <line class="radar__axis" x1="${C}" y1="${C - R}" x2="${C}" y2="${C + R}"/>
      <g class="radar__sweep"><path d="M${C} ${C} L${C + R} ${C} A${R} ${R} 0 0 0 ${C + R * Math.cos(-Math.PI / 5)} ${C + R * Math.sin(-Math.PI / 5)} Z" fill="url(#radar-sweep)"/><line x1="${C}" y1="${C}" x2="${C + R}" y2="${C}"/></g>
      ${blips}
      <circle class="radar__core" cx="${C}" cy="${C}" r="5"/>
    </svg>`;
}

export function tierLegend() {
  return ["hot", "warm", "mild", "cold"]
    .map((t) => `<span class="legend__item"><i class="legend__sw ch-tier--${t}"></i>${TIER_LABELS[t]}</span>`)
    .join("");
}
