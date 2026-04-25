import { createScan } from "../services/api.js";
import { state } from "../state/store.js";
import { objectiveCards } from "../ui/components.js";
import { escapeAttr, escapeHtml, quoteYaml } from "../utils/format.js";
import { track } from "../utils/metrics.js";

const MAX_STEP = 3;

export function renderNewScan(app) {
  const selectedProfile = currentProfile();
  if (!state.form.yaml && selectedProfile) {
    state.form.yaml = profileToYaml(selectedProfile);
  }

  const step = Number(new URLSearchParams(window.location.hash.split("?")[1] || "").get("step") || "1");
  const currentStep = Math.min(Math.max(step, 1), MAX_STEP);
  track("view_new_scan", { step: currentStep });

  app.innerHTML = `
    <div class="page-header">
      <div>
        <span class="eyebrow">Initialize</span>
        <h2>Scan Wizard</h2>
        <p class="muted">YAML yerine adım adım hedef seçimiyle tarama başlat.</p>
      </div>
    </div>
    <div class="wizard-shell">
      <section class="panel stack">
        <div class="wizard-steps">
          ${[1, 2, 3]
            .map((n) => `<button class="wizard-step ${n === currentStep ? "active" : ""}" data-step="${n}" type="button">${n}</button>`)
            .join("")}
        </div>
        <form id="scan-form" class="stack">
          ${renderStep(currentStep)}
          <div class="actions wizard-actions">
            ${currentStep > 1 ? `<button type="button" class="button secondary" data-action="prev">Back</button>` : ""}
            ${currentStep < MAX_STEP ? `<button type="button" class="button" data-action="next">Continue</button>` : `<button class="button" type="submit">Start Scan</button>`}
          </div>
          <div id="form-error"></div>
        </form>
      </section>
      <aside class="panel stack">
        <h3>What you'll get</h3>
        <ul class="value-list">
          <li>Frustrations grouped by signal strength</li>
          <li>Verbatim quotes from community members</li>
          <li>Opportunity score for prioritization</li>
          <li>Content-angle suggestions and quick saves</li>
        </ul>
        <button type="button" id="toggle-advanced" class="button secondary">Advanced YAML</button>
        <div id="advanced-panel" class="stack ${state.form.useYaml ? "" : "hidden"}">
          <textarea id="yaml">${escapeHtml(state.form.yaml)}</textarea>
        </div>
      </aside>
    </div>
  `;

  bindWizard(currentStep);
}

function renderStep(step) {
  if (step === 1) {
    return `
      <div class="field">
        <label class="label">What do you want to find?</label>
        <div class="objective-grid">${objectiveCards(state.form.objective)}</div>
      </div>
    `;
  }
  if (step === 2) {
    return `
      <div class="field">
        <label class="label" for="profile">Community Profile</label>
        <select id="profile">
          ${state.profiles
            .map(
              (profile) =>
                `<option value="${escapeAttr(profile.name)}" ${profile.name === state.form.profile ? "selected" : ""}>${escapeHtml(profile.name)} - ${escapeHtml(profile.title)}</option>`,
            )
            .join("")}
        </select>
      </div>
      <p class="muted">Önce hedef topluluğu seç, sistem uygun kaynakları otomatik çeker.</p>
    `;
  }
  return `
    <div class="field">
      <label class="label" for="language">Language</label>
      <select id="language">
        <option value="tr" ${state.form.language === "tr" ? "selected" : ""}>TR</option>
        <option value="en" ${state.form.language === "en" ? "selected" : ""}>EN</option>
      </select>
    </div>
    <div class="field two-col">
      <div>
        <label class="label" for="limit-per-source">Limit per source</label>
        <input id="limit-per-source" type="text" value="${escapeAttr(state.form.limitPerSource)}" />
      </div>
      <div>
        <label class="label" for="top-n">Top insights</label>
        <input id="top-n" type="text" value="${escapeAttr(state.form.topN)}" />
      </div>
    </div>
    <p class="muted">Bu tercihleri daha sonra sonuç ekranında da değiştirebilirsin.</p>
  `;
}

function bindWizard(currentStep) {
  document.querySelectorAll("[data-step]").forEach((btn) => {
    btn.addEventListener("click", () => navigateStep(Number(btn.dataset.step)));
  });

  document.querySelectorAll(".objective-card").forEach((card) => {
    card.addEventListener("click", () => {
      if (card.disabled) return;
      state.form.objective = card.dataset.objective;
      state.form.scanType = state.form.objective === "content_ideas" ? "content_ideas" : "pain_points";
      track("select_objective", { objective: state.form.objective });
      renderNewScan(document.querySelector("#app"));
    });
  });

  document.querySelector("#profile")?.addEventListener("change", (event) => {
    const profile = event.target.value;
    state.form.profile = profile;
    state.form.language = currentProfile()?.language || state.form.language;
    state.form.yaml = profileToYaml(currentProfile());
  });

  document.querySelector("#language")?.addEventListener("change", (event) => {
    state.form.language = event.target.value;
  });

  document.querySelector("#limit-per-source")?.addEventListener("input", (event) => {
    state.form.limitPerSource = sanitizeNumber(event.target.value, 200);
  });

  document.querySelector("#top-n")?.addEventListener("input", (event) => {
    state.form.topN = sanitizeNumber(event.target.value, 20);
  });

  document.querySelector("#toggle-advanced").addEventListener("click", () => {
    state.form.useYaml = !state.form.useYaml;
    track("toggle_yaml", { enabled: state.form.useYaml });
    renderNewScan(document.querySelector("#app"));
  });

  document.querySelector("#yaml")?.addEventListener("input", (event) => {
    state.form.yaml = event.target.value;
  });

  document.querySelector("[data-action='next']")?.addEventListener("click", () => navigateStep(currentStep + 1));
  document.querySelector("[data-action='prev']")?.addEventListener("click", () => navigateStep(currentStep - 1));
  document.querySelector("#scan-form").addEventListener("submit", startScan);
}

async function startScan(event) {
  event.preventDefault();
  const error = document.querySelector("#form-error");
  const submit = document.querySelector("#scan-form button[type='submit']");
  error.innerHTML = "";
  submit.disabled = true;
  track("start_scan_click", {
    objective: state.form.objective,
    yamlMode: state.form.useYaml,
  });

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
    const response = await createScan(payload);
    window.location.hash = `#/jobs/${response.job_id}`;
  } catch (err) {
    error.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
    submit.disabled = false;
  }
}

function navigateStep(nextStep) {
  const clamped = Math.min(Math.max(nextStep, 1), MAX_STEP);
  window.location.hash = `#/new?step=${clamped}`;
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
    `limit_per_source: ${state.form.limitPerSource || profile.limit_per_source || 200}`,
    `top_n: ${state.form.topN || profile.top_n || 20}`,
    `scan_type: ${state.form.scanType}`,
    "sources:",
    ...profile.sources.map((source) =>
      [`  - type: ${source.type}`, `    target: ${quoteYaml(source.target)}`, `    label: ${quoteYaml(source.label)}`, source.language ? `    language: ${source.language}` : null]
        .filter(Boolean)
        .join("\n"),
    ),
  ].filter(Boolean);
  return `${lines.join("\n")}\n`;
}

function sanitizeNumber(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}
