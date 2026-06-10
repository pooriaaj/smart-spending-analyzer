import axios from "axios";

const LOCAL_BACKEND_URL = "http://localhost:8000";
const FIRST_PARTY_API_PROXY_URL = "/api";

function isLocalFrontendHost(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function isRenderBackendURL(value, location) {
  if (!value) return false;

  try {
    const url = new URL(value, location?.origin || "http://localhost");
    return url.hostname === "smart-spending-analyzer.onrender.com" || url.hostname.endsWith(".onrender.com");
  } catch {
    return false;
  }
}

export function resolveApiBaseURL(
  configuredBaseURL = import.meta.env.VITE_API_BASE_URL,
  location = typeof window !== "undefined" ? window.location : undefined,
) {
  const isDeployedHttpsFrontend =
    location?.protocol === "https:" && !isLocalFrontendHost(location.hostname);

  if (
    isDeployedHttpsFrontend &&
    (!configuredBaseURL || isRenderBackendURL(configuredBaseURL, location))
  ) {
    return FIRST_PARTY_API_PROXY_URL;
  }

  return configuredBaseURL || LOCAL_BACKEND_URL;
}

const baseURL = resolveApiBaseURL();

const api = axios.create({
  baseURL,
  withCredentials: true,
  timeout: 30000,
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
