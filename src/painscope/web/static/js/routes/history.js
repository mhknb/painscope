import { getScans } from "../services/api.js";
import { state } from "../state/store.js";
import { empty, historyTable, loading } from "../ui/components.js";
import { track } from "../utils/metrics.js";

export async function renderHistory(app) {
  track("view_results");
  app.innerHTML = `
    <div class="page-header">
      <div>
        <span class="eyebrow">Results</span>
        <h2>Scan Results</h2>
        <p class="muted">Filtrele, karşılaştır, en iyi fırsatları aç.</p>
      </div>
      <a class="button" href="#/new">New Scan</a>
    </div>
    <section class="panel filter-row">
      <div class="field">
        <label class="label" for="filter-type">Type</label>
        <select id="filter-type">
          <option value="all">All</option>
          <option value="pain_points">Pain Points</option>
          <option value="content_ideas">Content Ideas</option>
        </select>
      </div>
      <div class="field">
        <label class="label" for="filter-language">Language</label>
        <select id="filter-language">
          <option value="all">All</option>
          <option value="tr">TR</option>
          <option value="en">EN</option>
        </select>
      </div>
      <div class="field">
        <label class="label" for="filter-score">Min posts</label>
        <input id="filter-score" type="text" value="0" />
      </div>
    </section>
    <section class="table-wrap" id="history-table">${loading()}</section>
  `;

  const data = await getScans(50);
  state.scans = data.scans || [];
  renderFilteredTable();
  bindFilters();
}

function bindFilters() {
  ["#filter-type", "#filter-language", "#filter-score"].forEach((selector) => {
    document.querySelector(selector).addEventListener("input", renderFilteredTable);
  });
}

function renderFilteredTable() {
  const type = document.querySelector("#filter-type")?.value || "all";
  const language = document.querySelector("#filter-language")?.value || "all";
  const minPosts = Number.parseInt(document.querySelector("#filter-score")?.value || "0", 10) || 0;

  const filtered = state.scans.filter((scan) => {
    const typeOk = type === "all" || scan.scan_type === type;
    const languageOk = language === "all" || (scan.language || "").toLowerCase() === language;
    const postsOk = Number(scan.total_posts_used || 0) >= minPosts;
    return typeOk && languageOk && postsOk;
  });

  const target = document.querySelector("#history-table");
  target.innerHTML = filtered.length ? historyTable(filtered) : empty("Filtreye uygun sonuç bulunamadı.");
}
