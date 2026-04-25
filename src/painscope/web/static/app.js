import { getHealth, getProfiles } from "./js/services/api.js";
import { renderDashboard } from "./js/routes/dashboard.js";
import { clearPoll, renderJob } from "./js/routes/job.js";
import { renderHistory } from "./js/routes/history.js";
import { renderNewScan } from "./js/routes/new-scan.js";
import { renderSaved } from "./js/routes/saved.js";
import { renderScanDetail } from "./js/routes/scan-detail.js";
import { loadSavedState, persistOnboarding, state } from "./js/state/store.js";
import { track } from "./js/utils/metrics.js";

const app = document.querySelector("#app");
const navLinks = [...document.querySelectorAll(".nav a")];
const healthStatus = document.querySelector("#health-status");
const healthDot = document.querySelector(".status-dot");

boot();

async function boot() {
  loadSavedState();
  await checkHealth();
  await loadProfiles();
  window.addEventListener("hashchange", renderRoute);
  renderRoute();
}

async function checkHealth() {
  try {
    const health = await getHealth();
    healthDot.classList.add("ok");
    healthStatus.textContent = health.web_auth_enabled ? "API ready, auth on" : "API ready";
  } catch {
    healthDot.classList.add("error");
    healthStatus.textContent = "API unavailable";
  }
}

async function loadProfiles() {
  try {
    const data = await getProfiles();
    state.profiles = data.profiles || [];
    if (!state.profiles.some((profile) => profile.name === state.form.profile) && state.profiles[0]) {
      state.form.profile = state.profiles[0].name;
      state.form.language = state.profiles[0].language || "tr";
    }
    state.onboarding.discover = state.profiles.length > 0;
    persistOnboarding();
  } catch {
    state.profiles = [];
  }
}

function renderRoute() {
  clearPoll();
  const hash = window.location.hash || "#/";
  const path = hash.split("?")[0];
  const [, route, id] = path.match(/^#\/?([^/]*)(?:\/(.+))?/) || [];
  setActive(route || "dashboard");

  if (route === "new") {
    state.onboarding.configure = true;
    persistOnboarding();
    renderNewScan(app);
  } else if (route === "history") {
    renderHistory(app);
  } else if (route === "saved") {
    renderSaved(app);
  } else if (route === "jobs" && id) {
    renderJob(app, id);
  } else if (route === "scans" && id) {
    renderScanDetail(app, id);
  } else {
    renderDashboard(app);
  }
  track("route_change", { route: route || "dashboard" });
}

function setActive(route) {
  const key = route === "" ? "dashboard" : route;
  navLinks.forEach((link) => {
    link.classList.toggle("active", link.dataset.route === key);
  });
}

