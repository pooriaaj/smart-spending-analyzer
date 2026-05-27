import axios from "axios";

const baseURL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL,
  withCredentials: true,
});

export function handleApiAuthError(error, navigate) {
  if (error?.response?.status === 401) {
    api.post("/auth/logout").catch(() => {});
    navigate("/", { replace: true });
    return true;
  }
  return false;
}

export default api;
