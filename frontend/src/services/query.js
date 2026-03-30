import api from "./api";

export async function getKpis(payload) {
  const { data } = await api.post("/kpis", payload);
  return data;
}

export async function runQuery(payload) {
  const { data } = await api.post("/query", payload);
  return data;
}
