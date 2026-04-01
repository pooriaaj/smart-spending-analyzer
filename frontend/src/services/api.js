import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

export function handleApiAuthError(error, navigate) {
  if (error?.response?.status === 401) {
    localStorage.removeItem("token");
    navigate("/", { replace: true });
    return true;
  }
  return false;
}

export default api;