import { getScan } from "../services/api.js";
import { persistOnboarding, persistSavedOpportunities, state } from "../state/store.js";
import { insightCard, loading } from "../ui/components.js";
import { duration, escapeHtml, number } from "../utils/format.js";
import { track } from "../utils/metrics.js";

export async function renderScanDetail(app, scanId) {
  track("view_scan_detail", { scanId });
  app.innerHTML = `<section class="panel">${loading()}</section>`;

  try {
    const scan = await getScan(scanId);
    state.onboarding.analyze = true;
    persistOnboarding();

    app.innerHTML = `
      <div class="page-header">
        <div>
          <span class="eyebrow">Opportunity Lens</span>
          <h2>${escapeHtml(scan.topic_name || scan.target || scan.scan_id)}</h2>
          <p class="muted mono">${escapeHtml(scan.scan_id)}</p>
        </div>
        <a class="button secondary" href="#/history">Back to results</a>
      </div>
      <section class="panel stack">
        <div class="metrics">
          <div class="metric"><span class="metric-label">Type</span><strong>${escapeHtml(scan.scan_type)}</strong></div>
          <div class="metric"><span class="metric-label">Posts</span><strong>${number(scan.total_posts_used)}</strong></div>
          <div class="metric"><span class="metric-label">Clusters</span><strong>${number(scan.num_clusters)}</strong></div>
          <div class="metric"><span class="metric-label">Duration</span><strong>${duration(scan.duration_seconds)}</strong></div>
        </div>
      </section>
      <section class="insight-grid" style="margin-top: 12px">
        ${(scan.insights || [])
          .map((insight) => {
            const exists = state.savedOpportunities.some((item) => item.title === (insight.title || "Untitled insight"));
            return insightCard(insight, exists);
          })
          .join("") || `<div class="empty">Bu scan için insight üretilmedi.</div>`}
      </section>
    `;

    bindInsightActions();
  } catch (err) {
    app.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
  }
}

function bindInsightActions() {
  document.querySelectorAll(".js-save-opportunity").forEach((btn) => {
    btn.addEventListener("click", () => {
      try {
        const payload = JSON.parse(btn.dataset.opportunity || "{}");
        if (!payload.title) return;
        const exists = state.savedOpportunities.some((item) => item.title === payload.title);
        if (!exists) {
          state.savedOpportunities.unshift(payload);
          persistSavedOpportunities();
          btn.textContent = "Saved";
          track("save_opportunity", { title: payload.title, score: payload.score });
        }
      } catch {
        // No-op for invalid data payload.
      }
    });
  });

  document.querySelectorAll(".js-content-angle").forEach((btn) => {
    btn.addEventListener("click", () => {
      track("create_content_brief_click", { title: btn.dataset.title || "unknown" });
      alert("Content brief template is queued for next release.");
    });
  });
}
