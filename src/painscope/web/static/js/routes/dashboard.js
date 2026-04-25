import { getScans } from "../services/api.js";
import { state } from "../state/store.js";
import { empty, loading, onboardingList, scanRows } from "../ui/components.js";
import { escapeHtml } from "../utils/format.js";
import { track } from "../utils/metrics.js";

export async function renderDashboard(app) {
  track("view_dashboard");
  app.innerHTML = `
    <div class="page-header">
      <div>
        <span class="eyebrow">Overview</span>
        <h2>Welcome back</h2>
        <p class="muted">Discover pain points and turn them into actionable content opportunities.</p>
      </div>
      <a class="button" href="#/new">Configure Scan</a>
    </div>
    <section class="grid dashboard-top">
      <article class="card highlight">
        <span class="label">Main Feature</span>
        <h3>Scan</h3>
        <p>Community sinyallerini topla, en yüksek fırsat skorunu çıkar.</p>
        <a class="button" href="#/new">Start Scan</a>
      </article>
      <article class="card">
        <span class="label">Results</span>
        <h3>${state.scans.length}</h3>
        <p>Kaydedilmiş tarama</p>
      </article>
      <article class="card">
        <span class="label">Saved</span>
        <h3>${state.savedOpportunities.length}</h3>
        <p>Kaydedilen fırsat</p>
      </article>
      <article class="card">
        <span class="label">Daily Scans</span>
        <h3>0 / 5</h3>
        <p>Kota takibi</p>
      </article>
    </section>
    <section class="grid dashboard">
      <section class="panel">
        <div class="row">
          <h3>Recent Scans</h3>
          <a class="topbar-link" href="#/history">View all</a>
        </div>
        <div id="recent-scans" class="stack" style="margin-top: 14px">${loading()}</div>
      </section>
      <aside class="stack">
        <section class="card">
          <h3>Getting Started</h3>
          ${onboardingList(state.onboarding)}
        </section>
        <section class="card">
          <h3>Primary profile</h3>
          <p class="muted">${escapeHtml(state.form.profile.toUpperCase())}</p>
          <a class="button secondary" href="#/new">Discover Communities</a>
        </section>
      </aside>
    </section>
  `;

  const data = await getScans(30);
  state.scans = data.scans || [];
  const target = document.querySelector("#recent-scans");
  target.innerHTML = state.scans.length ? scanRows(state.scans.slice(0, 5)) : empty("Henüz scan yok. İlk taramayı başlat.");
}
