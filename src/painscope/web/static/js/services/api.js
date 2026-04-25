export async function api(path, options = {}) {
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
      // Keep HTTP status message.
    }
    throw new Error(message);
  }

  return response.json();
}

export async function getHealth() {
  return api("/api/health");
}

export async function getProfiles() {
  return api("/api/profiles");
}

export async function createScan(payload) {
  return api("/api/scans", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getJob(jobId) {
  return api(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export async function getScans(limit = 30) {
  return api(`/api/scans?limit=${encodeURIComponent(limit)}`);
}

export async function getScan(scanId) {
  return api(`/api/scans/${encodeURIComponent(scanId)}`);
}

export async function postTelemetry(event, payload = {}) {
  return api("/api/telemetry", {
    method: "POST",
    body: JSON.stringify({ event, payload }),
  });
}
