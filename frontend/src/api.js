async function req(path, opts) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = `${res.status}`;
    try {
      const { detail } = await res.json();
      msg = Array.isArray(detail) ? detail.map((d) => d.msg.replace(/^Value error, /, "")).join(" · ") : detail;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  cars: (filters = {}) => {
    const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "" && v != null));
    return req(`/cars?${qs}`);
  },
  analyzeTop: (filters = {}, n = 20) => {
    const qs = new URLSearchParams(Object.entries({ ...filters, n }).filter(([, v]) => v !== "" && v != null));
    return req(`/cars/analizar-top?${qs}`, { method: "POST" });
  },
  topStatus: () => req("/cars/analizar-top/status"),
  car: (id) => req(`/cars/${id}`),
  analyzeProfitability: (id) => req(`/cars/${id}/rentabilidad`, { method: "POST" }),
  eliminar: (ids) => req("/cars/eliminar", { method: "POST", body: JSON.stringify({ ids }) }),
  favoritos: (ids, favorito) => req("/cars/favoritos", { method: "POST", body: JSON.stringify({ ids, favorito }) }),
  updateCar: (id, body) => req(`/cars/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  inspections: () => req("/inspections"),
  inspection: (id) => req(`/inspections/${id}`),
  startInspection: (car_id) => req("/inspections", { method: "POST", body: JSON.stringify({ car_id }) }),
  updateInspection: (id, body) => req(`/inspections/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteInspection: (id) => req(`/inspections/${id}`, { method: "DELETE" }),
  saveItem: (id, codigo, body) => req(`/inspections/${id}/items/${codigo}`, { method: "PATCH", body: JSON.stringify(body) }),
  uploadPhotos: (id, codigo, files) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return fetch(`/api/inspections/${id}/items/${codigo}/media`, { method: "POST", body: fd }).then(async (res) => {
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `${res.status}`);
      return res.json();
    });
  },
  generateInspectionAI: (id) => req(`/inspections/${id}/informe-ia`, { method: "POST" }),
  deletePhoto: (mediaId) => req(`/inspections/media/${mediaId}`, { method: "DELETE" }),
  getSetting: (key) => req(`/settings/${key}`),
  saveSetting: (key, value) => req(`/settings/${key}`, { method: "PUT", body: JSON.stringify(value) }),
  sync: () => req("/sync", { method: "POST" }),
  syncStatus: () => req("/sync/status"),
  syncAuto: () => req("/sync/auto", { method: "POST" }),
};
