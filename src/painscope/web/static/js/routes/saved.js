import { state } from "../state/store.js";
import { escapeHtml } from "../utils/format.js";
import { track } from "../utils/metrics.js";

export function renderSaved(app) {
  track("view_saved_opportunities");
  app.innerHTML = `
    <div class="page-header">
      <div>
        <span class="eyebrow">Library</span>
        <h2>Saved Opportunities</h2>
        <p class="muted">Öncelikli içerik veya ürün fırsatlarını burada tut.</p>
      </div>
    </div>
    <section class="panel stack">
      ${
        state.savedOpportunities.length
          ? state.savedOpportunities
              .map(
                (item) => `
            <article class="saved-opportunity">
              <h3>${escapeHtml(item.title)}</h3>
              <p class="muted">${escapeHtml(item.summary || "")}</p>
              <span class="pill">Score ${escapeHtml(item.score || "-")}</span>
            </article>
          `,
              )
              .join("")
          : `<div class="empty">Henüz kaydedilmiş fırsat yok.</div>`
      }
    </section>
  `;
}
