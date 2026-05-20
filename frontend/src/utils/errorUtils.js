const DEFAULT_ERROR_MESSAGE = "Something went wrong. Please try again.";
const NETWORK_ERROR_MESSAGE =
  "We could not reach the server. Please check your connection and try again.";

const isReadableString = (value) =>
  typeof value === "string" && value.trim().length > 0;

const uniqueMessages = (messages) =>
  Array.from(new Set(messages.map((message) => message.trim()).filter(Boolean)));

function readMessage(value, depth = 0) {
  if (depth > 4 || value == null) {
    return "";
  }

  if (isReadableString(value)) {
    return value.trim();
  }

  if (Array.isArray(value)) {
    return uniqueMessages(
      value.map((item) => readMessage(item, depth + 1)).filter(Boolean)
    ).join(" ");
  }

  if (typeof value === "object") {
    const prioritizedKeys = ["msg", "message", "detail", "error", "title"];

    for (const key of prioritizedKeys) {
      const message = readMessage(value[key], depth + 1);
      if (message) {
        return message;
      }
    }
  }

  return "";
}

export function getApiErrorMessage(error, fallbackMessage = DEFAULT_ERROR_MESSAGE) {
  const fallback = isReadableString(fallbackMessage)
    ? fallbackMessage.trim()
    : DEFAULT_ERROR_MESSAGE;

  if (!error) {
    return fallback;
  }

  const responseData = error?.response?.data;
  const responseMessage =
    readMessage(responseData?.detail) ||
    readMessage(responseData?.message) ||
    readMessage(responseData?.error) ||
    readMessage(responseData);

  if (responseMessage) {
    return responseMessage;
  }

  if (!error.response && (error.request || error.message === "Network Error")) {
    return NETWORK_ERROR_MESSAGE;
  }

  return readMessage(error.message) || fallback;
}

export function getApiSuccessMessage(data, fallbackMessage = "") {
  const message = readMessage(data?.message) || readMessage(data?.detail);
  if (message) {
    return message;
  }

  return isReadableString(fallbackMessage) ? fallbackMessage.trim() : "";
}
