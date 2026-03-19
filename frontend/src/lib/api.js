const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

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

export function getCalls() {
  return request("/api/dashboard/calls");
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
