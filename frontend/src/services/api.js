import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("querify_access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function getErrorMessage(error) {
  const payload = error?.response?.data;

  if (typeof payload?.error === "string" && typeof payload?.detail === "string") {
    return `${payload.error}: ${payload.detail}`;
  }

  if (typeof payload?.error === "string") {
    return payload.error;
  }

  if (typeof payload?.detail === "string") {
    return payload.detail;
  }

  return error?.message || "Something went wrong";
}

export default api;
