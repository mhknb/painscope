export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

export function safeUrl(value) {
  return typeof value === "string" && /^https?:\/\//i.test(value);
}

export function shortId(scanId) {
  if (!scanId) return "-";
  return scanId.length > 18 ? `${scanId.slice(0, 18)}...` : scanId;
}

export function number(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(numeric);
}

export function duration(seconds) {
  const numeric = Number(seconds);
  if (!Number.isFinite(numeric)) return "-";
  return `${numeric.toFixed(1)}s`;
}

export function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function quoteYaml(value) {
  return JSON.stringify(String(value || ""));
}
