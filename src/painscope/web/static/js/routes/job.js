import { getJob } from "../services/api.js";
import { state } from "../state/store.js";
import { loading } from "../ui/components.js";
import { escapeHtml, formatDate } from "../utils/format.js";

export function renderJob(app, jobId) {
  app.innerHTML = `
    <section class="panel progress-shell">
      <div class="progress-ring"><span>RUN</span></div>
      <h2>Scan in Progress</h2>
      <p class="muted">Pipeline çalışıyor. Bu sayfa birkaç saniyede bir güncellenir.</p>
      <div id="job-body" style="margin-top: 22px">${loading()}</div>
    </section>
  `;
  void loadJob(jobId);
  clearPoll();
  state.activePoll = setInterval(() => void loadJob(jobId), 3000);
}

async function loadJob(jobId) {
  const target = document.querySelector("#job-body");
  if (!target) return;

  try {
    const job = await getJob(jobId);
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

    if (job.status === "completed" || job.status === "failed") {
      clearPoll();
    }
  } catch (err) {
    target.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
    clearPoll();
  }
}

export function clearPoll() {
  if (state.activePoll) {
    clearInterval(state.activePoll);
    state.activePoll = null;
  }
}
