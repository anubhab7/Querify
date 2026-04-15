import api from "./api";

export async function getLlmProviders() {
  const { data } = await api.get("/llm/providers");
  return data;
}

export async function getKpis(payload) {
  const { data } = await api.post("/kpis", payload);
  return data;
}

export async function runQuery(payload) {
  const { data } = await api.post("/query", payload);
  return data;
}
