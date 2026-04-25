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
    const progress = Number.isFinite(Number(job.progress_percent)) ? Number(job.progress_percent) : 0;
    const logs = Array.isArray(job.recent_logs) ? job.recent_logs : [];
    target.innerHTML = `
      <div class="metrics" style="grid-template-columns: repeat(3, 1fr)">
        <div class="metric"><span class="metric-label">Status</span><strong>${escapeHtml(job.status)}</strong></div>
        <div class="metric"><span class="metric-label">Topic</span><strong>${escapeHtml(job.topic_name || "-")}</strong></div>
        <div class="metric"><span class="metric-label">Started</span><strong style="font-size: 14px">${escapeHtml(started)}</strong></div>
      </div>
      <div style="margin-top: 12px">
        <div class="row"><span class="label">Stage</span><strong>${escapeHtml(job.stage || "running")}</strong></div>
        <div style="height: 10px; border: 1px solid var(--line); background: var(--surface-low); border-radius: 4px; overflow: hidden; margin-top: 8px">
          <div style="height: 100%; width: ${Math.max(0, Math.min(progress, 100))}%; background: var(--primary)"></div>
        </div>
        <p class="muted mono" style="margin: 8px 0 0">${progress}%</p>
      </div>
      ${job.error ? `<div class="error-box" style="margin-top: 12px">${escapeHtml(job.error)}</div>` : ""}
      ${logs.length ? `<section class="panel stack" style="margin-top: 12px; text-align: left"><h3 style="font-size: 14px">Live Logs</h3><ul class="quote-list">${logs
        .slice(-10)
        .map((line) => `<li class="quote"><p>${escapeHtml(line)}</p></li>`)
        .join("")}</ul></section>` : ""}
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
