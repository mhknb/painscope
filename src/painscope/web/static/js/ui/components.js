import { duration, escapeAttr, escapeHtml, formatDate, number, safeUrl, shortId } from "../utils/format.js";

export function loading() {
  return `<p class="muted">Loading...</p>`;
}

export function empty(message) {
  return `<div class="empty">${escapeHtml(message)}</div>`;
}

export function objectiveCards(activeObjective) {
  const cards = [
    { key: "pain_points", title: "Pain Points", desc: "Hangi sorunlar tekrar ediyor?" },
    { key: "content_ideas", title: "Content Ideas", desc: "Hangi içerik açıları büyür?" },
    { key: "trending_topics", title: "Trending Topics", desc: "Yakın dönem trend sinyalleri", disabled: true },
    { key: "reply_opportunities", title: "Reply Opportunities", desc: "Nerede cevap verilmeli?", disabled: true },
  ];
  return cards
    .map(
      (card) => `
      <button
        type="button"
        class="objective-card ${activeObjective === card.key ? "active" : ""}"
        data-objective="${card.key}"
        ${card.disabled ? "disabled" : ""}
      >
        <strong>${escapeHtml(card.title)}</strong>
        <span>${escapeHtml(card.desc)}</span>
        ${card.disabled ? `<em>Soon</em>` : ""}
      </button>
    `,
    )
    .join("");
}

export function scanRows(scans) {
  return scans
    .map(
      (scan) => `
    <a class="scan-row" href="#/scans/${escapeAttr(scan.scan_id)}">
      <div>
        <strong>${escapeHtml(scan.topic_name || scan.target || "-")}</strong>
        <div class="muted mono">${escapeHtml(scan.scan_id)}</div>
      </div>
      <span class="pill">${escapeHtml(scan.scan_type)}</span>
      <span class="mono">${number(scan.total_posts_used)} posts</span>
      <span class="mono">${duration(scan.duration_seconds)}</span>
    </a>
  `,
    )
    .join("");
}

export function historyTable(scans) {
  return `
    <table>
      <thead>
        <tr>
          <th>Scan ID</th>
          <th>Topic</th>
          <th>Type</th>
          <th>Posts</th>
          <th>Completed</th>
        </tr>
      </thead>
      <tbody>
        ${scans
          .map(
            (scan) => `
          <tr onclick="window.location.hash = '#/scans/${escapeAttr(scan.scan_id)}'">
            <td class="mono">${escapeHtml(shortId(scan.scan_id))}</td>
            <td>${escapeHtml(scan.topic_name || scan.target || "-")}</td>
            <td><span class="pill">${escapeHtml(scan.scan_type)}</span></td>
            <td class="mono">${number(scan.total_posts_used)}</td>
            <td class="mono">${escapeHtml(formatDate(scan.completed_at))}</td>
          </tr>
        `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

export function insightCard(insight, isSaved = false) {
  const severity = Number(insight.severity || 0);
  const severityClass = severity >= 4 ? "high" : severity >= 3 ? "medium" : "low";
  const title = insight.title || "Untitled insight";
  const summary = insight.summary || insight.angle || "";
  const questions = Array.isArray(insight.target_questions) ? insight.target_questions : [];
  const quotes = Array.isArray(insight.quotes) ? insight.quotes.slice(0, 3) : [];
  const distribution = insight.source_distribution || {};
  const score = opportunityScore(insight);

  return `
    <article class="insight ${severityClass}">
      <div class="insight-head">
        <div class="row">
          <span class="pill ${severity >= 4 ? "danger" : severity >= 3 ? "warning" : ""}">${severity ? "Severity " + severity : "Idea"}</span>
          ${severity ? severityBars(severity, severityClass) : ""}
        </div>
        <h3 style="margin-top: 10px">${escapeHtml(title)}</h3>
        <p class="muted">${escapeHtml(summary)}</p>
      </div>
      <div class="insight-body stack">
        <div class="metrics compact">
          <div class="metric"><span class="metric-label">Opportunity</span><strong>${score}</strong></div>
          <div class="metric"><span class="metric-label">Cluster</span><strong>${number(insight._cluster_size)}</strong></div>
          <div class="metric"><span class="metric-label">Score</span><strong>${number(insight._score)}</strong></div>
        </div>
        ${insight.content_angle ? `<div><span class="label">Ne üretmeliyim?</span><p>${escapeHtml(insight.content_angle)}</p></div>` : ""}
        ${questions.length ? `<div><span class="label">İlk içerik başlıkları</span><ul>${questions.map((q) => `<li>${escapeHtml(q)}</li>`).join("")}</ul></div>` : ""}
        <div>
          <span class="label">Kaynak dağılımı</span>
          <div class="distribution" style="margin-top: 8px">
            ${
              Object.entries(distribution)
                .map(([source, count]) => `<span class="pill">${escapeHtml(source)}: ${number(count)}</span>`)
                .join("") || `<span class="muted">No source distribution</span>`
            }
          </div>
        </div>
        <ul class="quote-list">
          ${quotes.map(quoteBlock).join("")}
        </ul>
        <div class="actions">
          <button type="button" class="button secondary js-save-opportunity" data-opportunity='${escapeAttr(JSON.stringify({ title, summary, score }))}'>
            ${isSaved ? "Saved" : "Save Opportunity"}
          </button>
          <button type="button" class="button secondary js-content-angle" data-title="${escapeAttr(title)}">Create Content Brief</button>
        </div>
      </div>
    </article>
  `;
}

export function quoteBlock(quote) {
  const text = typeof quote === "string" ? quote : quote.text || "";
  const url = typeof quote === "object" && safeUrl(quote.url) ? quote.url : "";
  return `
    <li class="quote">
      <p>“${escapeHtml(text)}”</p>
      ${url ? `<a href="${escapeAttr(url)}" target="_blank" rel="noreferrer">VIEW SOURCE</a>` : ""}
    </li>
  `;
}

export function onboardingList(statuses) {
  return `
    <ol class="onboarding-list">
      ${step("discover", "Discover Communities", "Toplulukları seç ve listeye ekle.", statuses.discover)}
      ${step("configure", "Configure Scan", "Hedefine göre tarama ayarlarını yap.", statuses.configure)}
      ${step("analyze", "Analyze Results", "Fırsatları skorlayıp kaydet.", statuses.analyze)}
    </ol>
  `;
}

function step(id, title, desc, complete) {
  return `
    <li class="${complete ? "done" : ""}">
      <span>${complete ? "✓" : id === "discover" ? "1" : id === "configure" ? "2" : "3"}</span>
      <div>
        <strong>${title}</strong>
        <p>${desc}</p>
      </div>
    </li>
  `;
}

function severityBars(value, severityClass) {
  return `
    <div class="severity" aria-label="Severity ${value} of 5">
      ${[1, 2, 3, 4, 5].map((step) => `<span class="${step <= value ? `on ${severityClass}` : ""}"></span>`).join("")}
    </div>
  `;
}

function opportunityScore(insight) {
  const trend = Number(insight._score || 0);
  const severity = Number(insight.severity || 0);
  const diversity = Object.keys(insight.source_distribution || {}).length;
  const score = trend * 0.5 + severity * 15 + diversity * 10;
  return number(score);
}
