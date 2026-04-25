import { postTelemetry } from "../services/api.js";

const queue = [];
let flushing = false;

export function track(event, payload = {}) {
  queue.push({
    event,
    payload,
    at: new Date().toISOString(),
  });
  void flush();
}

async function flush() {
  if (flushing || queue.length === 0) return;
  flushing = true;
  try {
    while (queue.length) {
      const item = queue.shift();
      await postTelemetry(item.event, { ...item.payload, at: item.at });
    }
  } catch {
    // Telemetry should never break the UI flow.
  } finally {
    flushing = false;
  }
}
