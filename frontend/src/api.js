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
  updateCar: (id, body) => req(`/cars/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  getSetting: (key) => req(`/settings/${key}`),
  saveSetting: (key, value) => req(`/settings/${key}`, { method: "PUT", body: JSON.stringify(value) }),
  sync: () => req("/sync", { method: "POST" }),
  syncStatus: () => req("/sync/status"),
  syncAuto: () => req("/sync/auto", { method: "POST" }),
};
