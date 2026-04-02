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

export function ingestNow({ folder, limit } = {}) {
  const params = new URLSearchParams();
  if (folder && folder.trim()) {
    params.set("folder", folder.trim());
  }
  if (limit) {
    params.set("limit", String(limit));
  }

  const query = params.toString();
  const path = query ? `/api/ingest/run?${query}` : "/api/ingest/run";
  return request(path, { method: "POST" });
}

export function getTrend() {
  return request("/api/dashboard/trend");
}

export function getDistribution() {
  return request("/api/dashboard/distribution");
}

export function getCalls(limit = 10) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  return request(`/api/dashboard/calls?${params.toString()}`);
}

export function getCallDetail(id) {
  return request(`/api/dashboard/calls/${id}`);
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
