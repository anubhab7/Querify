import api from "./api";

export async function createChat(payload) {
  const { data } = await api.post("/chats", payload);
  return data;
}

export async function getChats() {
  const { data } = await api.get("/chats");
  return data;
}

export async function getChatHistory(chatId) {
  const { data } = await api.get(`/chats/${chatId}/history`);
  return data;
}

export async function getChatStatus(chatId) {
  const { data } = await api.get(`/chats/${chatId}/status`);
  return data;
}

export async function deleteChat(chatId) {
  const { data } = await api.delete(`/chats/${chatId}`);
  return data;
}

export async function getSchema(sessionId) {
  const { data } = await api.get("/schema", { params: { session_id: sessionId } });
  return data;
}
