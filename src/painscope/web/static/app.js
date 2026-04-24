const app = document.querySelector("#app");
const navLinks = [...document.querySelectorAll(".nav a")];
const healthStatus = document.querySelector("#health-status");
const healthDot = document.querySelector(".status-dot");

const state = {
  profiles: [],
  scans: [],
  activePoll: null,
  form: {
    scanType: "pain_points",
    language: "tr",
    profile: "tr",
    useYaml: false,
    yaml: "",
  },
};

boot();

async function boot() {
  await checkHealth();
  await loadProfiles();
  window.addEventListener("hashchange", renderRoute);
  renderRoute();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the HTTP status message.
    }
    throw new Error(message);
  }

  return response.json();
}

async function checkHealth() {
  try {
    const health = await api("/api/health");
    healthDot.classList.add("ok");
    healthStatus.textContent = health.web_auth_enabled ? "API ready, auth on" : "API ready";
  } catch {
    healthDot.classList.add("error");
    healthStatus.textContent = "API unavailable";
  }
}

async function loadProfiles() {
  try {
    const data = await api("/api/profiles");
    state.profiles = data.profiles || [];
    if (!state.profiles.some((profile) => profile.name === state.form.profile) && state.profiles[0]) {
      state.form.profile = state.profiles[0].name;
      state.form.language = state.profiles[0].language || "tr";
    }
  } catch {
    state.profiles = [];
  }
}

function renderRoute() {
  clearPoll();
  const hash = window.location.hash || "#/";
  const [, route, id] = hash.match(/^#\/?([^/]*)(?:\/(.+))?/) || [];
  setActive(route || "dashboard");

  if (route === "new") {
    renderNewScan();
  } else if (route === "history") {
    renderHistory();
  } else if (route === "jobs" && id) {
    renderJob(id);
  } else if (route === "scans" && id) {
    renderScanDetail(id);
  } else {
    renderDashboard();
  }
}

function setActive(route) {
  const key = route === "" ? "dashboard" : route;
  navLinks.forEach((link) => {
    link.classList.toggle("active", link.dataset.route === key);
  });
}

async function renderDashboard() {
  app.innerHTML = `
    <div class="page-header">
      <div>
        <span class="eyebrow">Workspace</span>
        <h2>Research Dashboard</h2>
        <p class="muted">Son taramalar ve hızlı başlangıç.</p>
      </div>
      <a class="button" href="#/new">New Scan</a>
    </div>
    <div class="grid dashboard">
      <section class="panel">
        <div class="row">
          <h3>Recent Scans</h3>
          <a class="topbar-link" href="#/history">View all</a>
        </div>
        <div id="recent-scans" class="stack" style="margin-top: 14px">${loading()}</div>
      </section>
      <aside class="stack">
        <section class="card">
          <span class="label">Profiles</span>
          <div class="metrics" style="margin-top: 10px; grid-template-columns: repeat(2, 1fr)">
            <div class="metric"><span class="metric-label">Available</span><strong>${state.profiles.length}</strong></div>
            <div class="metric"><span class="metric-label">Default</span><strong>${escapeHtml(state.form.profile.toUpperCase())}</strong></div>
          </div>
        </section>
        <section class="card">
          <h3>First run</h3>
          <p class="muted">Profil seç, scan type belirle ve çalıştır. Detay sayfası tamamlanınca otomatik açılır.</p>
          <a class="button secondary" href="#/new">Start from profile</a>
        </section>
      </aside>
    </div>
  `;

  const scans = await fetchScans();
  const target = document.querySelector("#recent-scans");
  target.innerHTML = scans.length ? scanRows(scans.slice(0, 5)) : empty("Henüz scan yok. İlk taramayı başlat.");
}

function renderNewScan() {
  const selectedProfile = currentProfile();
  if (!state.form.yaml && selectedProfile) {
    state.form.yaml = profileToYaml(selectedProfile);
  }

  app.innerHTML = `
    <div class="page-header">
      <div>
        <span class="eyebrow">Initialize</span>
        <h2>New Scan</h2>
        <p class="muted">Profil ile hızlı başlat veya gelişmiş kullanım için YAML yapıştır.</p>
      </div>
    </div>
    <form id="scan-form" class="grid two">
      <section class="panel stack">
        <div class="field">
          <span class="label">Scan Type</span>
          <div class="segmented" data-segment="scanType">
            <button type="button" data-value="pain_points" class="${state.form.scanType === "pain_points" ? "active" : ""}">Pain Points</button>
            <button type="button" data-value="content_ideas" class="${state.form.scanType === "content_ideas" ? "active" : ""}">Content Ideas</button>
          </div>
        </div>
        <div class="field">
          <label class="label" for="profile">Profile</label>
          <select id="profile" ${state.form.useYaml ? "disabled" : ""}>
            ${state.profiles.map((profile) => `<option value="${escapeAttr(profile.name)}" ${profile.name === state.form.profile ? "selected" : ""}>${escapeHtml(profile.name)} - ${escapeHtml(profile.title)}</option>`).join("")}
          </select>
        </div>
        <div class="field">
          <label class="label" for="language">Language</label>
          <select id="language">
            <option value="tr" ${state.form.language === "tr" ? "selected" : ""}>TR</option>
            <option value="en" ${state.form.language === "en" ? "selected" : ""}>EN</option>
          </select>
        </div>
        <label class="row" style="justify-content: flex-start">
          <input id="use-yaml" type="checkbox" ${state.form.useYaml ? "checked" : ""} />
          <span>Use custom YAML</span>
        </label>
        <div class="actions">
          <button class="button" type="submit">Start Scan</button>
          <a class="button secondary" href="#/">Cancel</a>
        </div>
        <div id="form-error"></div>
      </section>
      <section class="panel stack">
        <div class="row">
          <h3>Configuration Preview</h3>
          <span class="pill">${state.form.useYaml ? "YAML" : "PROFILE"}</span>
        </div>
        <textarea id="yaml" ${state.form.useYaml ? "" : "readonly"}>${escapeHtml(state.form.useYaml ? state.form.yaml : profileToYaml(selectedProfile))}</textarea>
      </section>
    </form>
  `;

  bindNewScan();
}

function bindNewScan() {
  document.querySelectorAll("[data-segment='scanType'] button").forEach((button) => {
    button.addEventListener("click", () => {
      state.form.scanType = button.dataset.value;
      renderNewScan();
    });
  });

  document.querySelector("#profile")?.addEventListener("change", (event) => {
    const profile = event.target.value;
    state.form.profile = profile;
    state.form.language = currentProfile()?.language || state.form.language;
    state.form.yaml = profileToYaml(currentProfile());
    renderNewScan();
  });

  document.querySelector("#language").addEventListener("change", (event) => {
    state.form.language = event.target.value;
    renderNewScan();
  });

  document.querySelector("#use-yaml").addEventListener("change", (event) => {
    state.form.useYaml = event.target.checked;
    state.form.yaml = document.querySelector("#yaml").value;
    renderNewScan();
  });

  document.querySelector("#yaml").addEventListener("input", (event) => {
    state.form.yaml = event.target.value;
  });

  document.querySelector("#scan-form").addEventListener("submit", startScan);
}

async function startScan(event) {
  event.preventDefault();
  const error = document.querySelector("#form-error");
  const submit = document.querySelector("#scan-form button[type='submit']");
  error.innerHTML = "";
  submit.disabled = true;

  const payload = {
    scan_type: state.form.scanType,
    language: state.form.language,
  };
  if (state.form.useYaml) {
    payload.config_yaml = document.querySelector("#yaml").value;
  } else {
    payload.profile = state.form.profile;
  }

  try {
    const response = await api("/api/scans", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    window.location.hash = `#/jobs/${response.job_id}`;
  } catch (err) {
    error.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
    submit.disabled = false;
  }
}

function renderJob(jobId) {
  app.innerHTML = `
    <section class="panel progress-shell">
      <div class="progress-ring"><span>RUN</span></div>
      <h2>Scan in Progress</h2>
      <p class="muted">Pipeline çalışıyor. Bu sayfa birkaç saniyede bir güncellenir.</p>
      <div id="job-body" style="margin-top: 22px">${loading()}</div>
    </section>
  `;
  loadJob(jobId);
  state.activePoll = setInterval(() => loadJob(jobId), 3000);
}

async function loadJob(jobId) {
  const target = document.querySelector("#job-body");
  if (!target) return;

  try {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    const started = job.started_at ? formatDate(job.started_at) : "-";
    const completed = job.completed_at ? formatDate(job.completed_at) : "-";
    target.innerHTML = `
      <div class="metrics" style="grid-template-columns: repeat(3, 1fr)">
        <div class="metric"><span class="metric-label">Status</span><strong>${escapeHtml(job.status)}</strong></div>
        <div class="metric"><span class="metric-label">Topic</span><strong>${escapeHtml(job.topic_name || "-")}</strong></div>
        <div class="metric"><span class="metric-label">Started</span><strong style="font-size: 14px">${escapeHtml(started)}</strong></div>
      </div>
      ${job.error ? `<div class="error-box" style="margin-top: 12px">${escapeHtml(job.error)}</div>` : ""}
      ${job.status === "completed" && job.scan_id ? `<div class="actions" style="justify-content: center; margin-top: 16px"><a class="button" href="#/scans/${encodeURIComponent(job.scan_id)}">Open scan detail</a></div>` : ""}
      ${job.status === "failed" ? `<p class="muted">Completed: ${escapeHtml(completed)}</p>` : ""}
    `;

    if (job.status === "completed" && job.scan_id) {
      clearPoll();
    }
    if (job.status === "failed") {
      clearPoll();
    }
  } catch (err) {
    target.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
    clearPoll();
  }
}

async function renderHistory() {
  app.innerHTML = `
    <div class="page-header">
      <div>
        <span class="eyebrow">Archive</span>
        <h2>Scan History</h2>
        <p class="muted">Son kaydedilmiş taramalar.</p>
      </div>
      <a class="button" href="#/new">New Scan</a>
    </div>
    <section class="table-wrap" id="history-table">${loading()}</section>
  `;

  const scans = await fetchScans();
  document.querySelector("#history-table").innerHTML = scans.length ? historyTable(scans) : empty("Henüz kayıtlı scan yok.");
}

async function renderScanDetail(scanId) {
  app.innerHTML = `<section class="panel">${loading()}</section>`;
  try {
    const scan = await api(`/api/scans/${encodeURIComponent(scanId)}`);
    app.innerHTML = `
      <div class="page-header">
        <div>
          <span class="eyebrow">Scan Detail</span>
          <h2>${escapeHtml(scan.topic_name || scan.target || scan.scan_id)}</h2>
          <p class="muted mono">${escapeHtml(scan.scan_id)}</p>
        </div>
        <a class="button secondary" href="#/history">Back to history</a>
      </div>
      <section class="panel stack">
        <div class="metrics">
          <div class="metric"><span class="metric-label">Type</span><strong>${escapeHtml(scan.scan_type)}</strong></div>
          <div class="metric"><span class="metric-label">Posts</span><strong>${number(scan.total_posts_used)}</strong></div>
          <div class="metric"><span class="metric-label">Clusters</span><strong>${number(scan.num_clusters)}</strong></div>
          <div class="metric"><span class="metric-label">Duration</span><strong>${duration(scan.duration_seconds)}</strong></div>
        </div>
        <div class="row">
          <span class="pill">${escapeHtml(scan.language || "-")}</span>
          <span class="muted mono">${escapeHtml(scan.model_used || "default model")}</span>
        </div>
      </section>
      <section class="insight-grid" style="margin-top: 12px">
        ${(scan.insights || []).map(insightCard).join("") || `<div class="empty">Bu scan için insight üretilmedi.</div>`}
      </section>
    `;
  } catch (err) {
    app.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
  }
}

async function fetchScans() {
  try {
    const data = await api("/api/scans?limit=30");
    state.scans = data.scans || [];
    return state.scans;
  } catch (err) {
    app.insertAdjacentHTML("afterbegin", `<div class="error-box">${escapeHtml(err.message)}</div>`);
    return [];
  }
}

function historyTable(scans) {
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
        ${scans.map((scan) => `
          <tr onclick="window.location.hash = '#/scans/${escapeAttr(scan.scan_id)}'">
            <td class="mono">${escapeHtml(shortId(scan.scan_id))}</td>
            <td>${escapeHtml(scan.topic_name || scan.target || "-")}</td>
            <td><span class="pill">${escapeHtml(scan.scan_type)}</span></td>
            <td class="mono">${number(scan.total_posts_used)}</td>
            <td class="mono">${escapeHtml(formatDate(scan.completed_at))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function scanRows(scans) {
  return scans.map((scan) => `
    <a class="scan-row" href="#/scans/${escapeAttr(scan.scan_id)}">
      <div>
        <strong>${escapeHtml(scan.topic_name || scan.target || "-")}</strong>
        <div class="muted mono">${escapeHtml(scan.scan_id)}</div>
      </div>
      <span class="pill">${escapeHtml(scan.scan_type)}</span>
      <span class="mono">${number(scan.total_posts_used)} posts</span>
      <span class="mono">${duration(scan.duration_seconds)}</span>
    </a>
  `).join("");
}

function insightCard(insight) {
  const severity = Number(insight.severity || 0);
  const severityClass = severity >= 4 ? "high" : severity >= 3 ? "medium" : "low";
  const title = insight.title || "Untitled insight";
  const summary = insight.summary || insight.angle || "";
  const questions = Array.isArray(insight.target_questions) ? insight.target_questions : [];
  const quotes = Array.isArray(insight.quotes) ? insight.quotes.slice(0, 3) : [];
  const distribution = insight.source_distribution || {};

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
        <div class="metrics" style="grid-template-columns: repeat(2, 1fr)">
          <div class="metric"><span class="metric-label">Score</span><strong>${number(insight._score)}</strong></div>
          <div class="metric"><span class="metric-label">Cluster</span><strong>${number(insight._cluster_size)}</strong></div>
        </div>
        ${insight.content_angle ? `<div><span class="label">Content Angle</span><p>${escapeHtml(insight.content_angle)}</p></div>` : ""}
        ${questions.length ? `<div><span class="label">Target Questions</span><ul>${questions.map((q) => `<li>${escapeHtml(q)}</li>`).join("")}</ul></div>` : ""}
        <div>
          <span class="label">Source Distribution</span>
          <div class="distribution" style="margin-top: 8px">
            ${Object.entries(distribution).map(([source, count]) => `<span class="pill">${escapeHtml(source)}: ${number(count)}</span>`).join("") || `<span class="muted">No source distribution</span>`}
          </div>
        </div>
        <ul class="quote-list">
          ${quotes.map(quoteBlock).join("")}
        </ul>
      </div>
    </article>
  `;
}

function quoteBlock(quote) {
  const text = typeof quote === "string" ? quote : quote.text || "";
  const url = typeof quote === "object" && safeUrl(quote.url) ? quote.url : "";
  return `
    <li class="quote">
      <p>“${escapeHtml(text)}”</p>
      ${url ? `<a href="${escapeAttr(url)}" target="_blank" rel="noreferrer">VIEW SOURCE</a>` : ""}
    </li>
  `;
}

function safeUrl(value) {
  return typeof value === "string" && /^https?:\/\//i.test(value);
}

function severityBars(value, severityClass) {
  return `
    <div class="severity" aria-label="Severity ${value} of 5">
      ${[1, 2, 3, 4, 5].map((step) => `<span class="${step <= value ? "on " + severityClass : ""}"></span>`).join("")}
    </div>
  `;
}

function currentProfile() {
  return state.profiles.find((profile) => profile.name === state.form.profile) || state.profiles[0] || null;
}

function profileToYaml(profile) {
  if (!profile) return "name: Custom Topic\nlanguage: tr\nscan_type: pain_points\nlimit_per_source: 100\ntop_n: 10\nsources: []\n";

  const lines = [
    `name: ${quoteYaml(profile.title)}`,
    profile.description ? `description: ${quoteYaml(profile.description)}` : null,
    `language: ${state.form.language || profile.language || "tr"}`,
    `limit_per_source: ${profile.limit_per_source || 200}`,
    `top_n: ${profile.top_n || 20}`,
    `scan_type: ${state.form.scanType}`,
    "sources:",
    ...profile.sources.map((source) => [
      `  - type: ${source.type}`,
      `    target: ${quoteYaml(source.target)}`,
      `    label: ${quoteYaml(source.label)}`,
      source.language ? `    language: ${source.language}` : null,
    ].filter(Boolean).join("\n")),
  ].filter(Boolean);
  return `${lines.join("\n")}\n`;
}

function quoteYaml(value) {
  return JSON.stringify(String(value || ""));
}

function clearPoll() {
  if (state.activePoll) {
    clearInterval(state.activePoll);
    state.activePoll = null;
  }
}

function loading() {
  return `<p class="muted">Loading...</p>`;
}

function empty(message) {
  return `<div class="empty">${escapeHtml(message)}</div>`;
}

function shortId(scanId) {
  if (!scanId) return "-";
  return scanId.length > 18 ? `${scanId.slice(0, 18)}...` : scanId;
}

function number(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(numeric);
}

function duration(seconds) {
  const numeric = Number(seconds);
  if (!Number.isFinite(numeric)) return "-";
  return `${numeric.toFixed(1)}s`;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

