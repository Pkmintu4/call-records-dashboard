const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== "undefined" && window.location.port === "5173" ? "http://localhost:8000" : "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }

  return response.json();
}

export function ingestNow({ folder, limit, forceReprocess, audioOnly } = {}) {
  const params = new URLSearchParams();
  if (folder && folder.trim()) {
    params.set("folder", folder.trim());
  }
  if (limit) {
    params.set("limit", String(limit));
  }
  if (forceReprocess) {
    params.set("force_reprocess", "true");
  }
  if (audioOnly) {
    params.set("audio_only", "true");
  }

  const query = params.toString();
  const path = query ? `/api/ingest/run?${query}` : "/api/ingest/run";
  return request(path, { method: "POST" });
}

export function getIngestStatus() {
  return request("/api/ingest/status");
}

export function getTrend() {
  return request("/api/dashboard/trend");
}

export function getDistribution() {
  return request("/api/dashboard/distribution");
}

export function getIntentDistribution() {
  return request("/api/dashboard/intent-distribution");
}

export function getCalls(limit = 10) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  return request(`/api/dashboard/calls?${params.toString()}`);
}

export function getCallDetail(id) {
  return request(`/api/dashboard/calls/${id}`);
}

export function getCallAudioUrl(id) {
  return `${API_BASE}/api/dashboard/calls/${id}/audio`;
}

export function getTranscriptSummaries(limit = 200, offset = 0) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return request(`/api/dashboard/transcript-summaries?${params.toString()}`);
}

export function getCallsByNumber(limitNumbers = 100, perNumberCalls = 25) {
  const params = new URLSearchParams();
  params.set("limit_numbers", String(limitNumbers));
  params.set("per_number_calls", String(perNumberCalls));
  return request(`/api/dashboard/calls-by-number?${params.toString()}`);
}

export function getOverallKpis() {
  return request("/api/dashboard/overall-kpis");
}

export function getOverallKpiTrend() {
  return request("/api/dashboard/overall-kpis-trend");
}

export function getSegmentSentimentBreakdown() {
  return request("/api/dashboard/segment-sentiment-breakdown");
}

export function getGoogleAuthUrl() {
  return request("/api/google/auth-url");
}

export function getDbTables() {
  return request("/api/dashboard/db/tables");
}

export function getDbTableRows(tableName, limit = 25, offset = 0) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return request(`/api/dashboard/db/table/${encodeURIComponent(tableName)}?${params.toString()}`);
}

export function getDbTableExportUrl(tableName) {
  // returns a direct URL to download the CSV for the given table
  return `${API_BASE}/api/dashboard/db/table/${encodeURIComponent(tableName)}/export`;
}

export function searchGlobal(q, limit = 50, offset = 0) {
  const params = new URLSearchParams();
  params.set("q", String(q || ""));
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return request(`/api/dashboard/search?${params.toString()}`);
}
