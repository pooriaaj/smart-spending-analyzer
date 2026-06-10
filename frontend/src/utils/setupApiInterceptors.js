import { notifications } from "@mantine/notifications";
import api from "../services/api";

/**
 * Wires up global Axios response interceptors.
 *
 * Only handles errors that a page cannot meaningfully handle inline:
 *   - Network offline / no response
 *   - Request timeout (>30s)
 *   - 5xx server errors
 *
 * 401 (auth) and 4xx (validation/not-found) are intentionally left to
 * individual pages via handleApiAuthError() and their own error states.
 */
export function setupApiInterceptors() {
  api.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.code === "ECONNABORTED" || error.code === "ERR_CANCELED") {
        notifications.show({
          title: "Request timed out",
          message: "The server took too long to respond. Please try again.",
          color: "red",
          autoClose: 6000,
        });
      } else if (!error.response) {
        notifications.show({
          title: "Connection problem",
          message: "Could not reach the server. Check your network and try again.",
          color: "orange",
          autoClose: 6000,
        });
      } else if (error.response.status >= 500) {
        notifications.show({
          title: "Server error",
          message: "Something went wrong on our end. Please try again in a moment.",
          color: "red",
          autoClose: 6000,
        });
      }

      return Promise.reject(error);
    }
  );
}
