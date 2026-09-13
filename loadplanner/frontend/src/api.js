const BASE = "/api";

async function req(path, options = {}) {
  const r = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const j = await r.json();
      detail = typeof j.detail === "string" ? j.detail : (j.detail?.detail || JSON.stringify(j.detail));
    } catch (e) { /* ignore */ }
    throw new Error(detail);
  }
  return r.json();
}

export const api = {
  plans: () => req("/plans"),
  plan: (id) => req(`/plans/${id}`),
  createPlan: (body) => req("/plans", { method: "POST", body: JSON.stringify(body) }),
  items: () => req("/items"),
  patchItem: (id, body) => req(`/items/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  solve: (planId) => req(`/plans/${planId}/solve`, { method: "POST" }),
  clearUnlocked: (planId) => req(`/plans/${planId}/clear-unlocked`, { method: "POST" }),
  upsertPlacement: (planId, body) =>
    req(`/plans/${planId}/placements`, { method: "POST", body: JSON.stringify(body) }),
  deletePlacement: (placementId) => req(`/placements/${placementId}`, { method: "DELETE" }),
  exportCsvUrl: (planId) => `${BASE}/plans/${planId}/export.csv`,
  exportJsonUrl: (planId) => `${BASE}/plans/${planId}/export.json`,
};
