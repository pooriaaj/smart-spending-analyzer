import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { IconSparkles } from "@tabler/icons-react";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import PageHeader from "../components/PageHeader";
import { useLanguage } from "../i18n/LanguageContext";
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
} from "../services/accountStorage";
import { getApiErrorMessage } from "../utils/errorUtils";

function buildInitialAssistantMessage(t) {
  return {
    role: "assistant",
    content: t("assistant.welcomeMessage"),
    supportingPoints: [],
    suggestedFollowups: [],
    suggestedActions: [],
    scopeLabel: "",
  };
}

function buildMessagesFromHistory(history, t) {
  if (!Array.isArray(history) || history.length === 0) {
    return [buildInitialAssistantMessage(t)];
  }

  const messages = history
    .filter((message) => message?.role === "user" || message?.role === "assistant")
    .map((message) => ({
      role: message.role,
      content: String(message.content || ""),
      supportingPoints: [],
      suggestedFollowups: [],
      suggestedActions: [],
      scopeLabel: message.scope_label || "",
    }))
    .filter((message) => message.content.trim().length > 0);

  return messages.length > 0 ? messages : [buildInitialAssistantMessage(t)];
}

function AssistantMessageContent({ text }) {
  const urlPattern = /(https?:\/\/[^\s]+)/g;
  const lines = String(text || "").split("\n");

  return (
    <>
      {lines.map((line, lineIndex) => {
        const parts = line.split(urlPattern);

        return (
          <span key={`line-${lineIndex}`}>
            {parts.map((part, partIndex) => {
              if (urlPattern.test(part)) {
                urlPattern.lastIndex = 0;
                return (
                  <a
                    key={`link-${lineIndex}-${partIndex}`}
                    href={part}
                    target="_blank"
                    rel="noreferrer"
                    className="assistant-message-link"
                  >
                    {part}
                  </a>
                );
              }
              urlPattern.lastIndex = 0;
              return part;
            })}
            {lineIndex < lines.length - 1 && <br />}
          </span>
        );
      })}
    </>
  );
}

function formatAssistantChatContent(data, t) {
  const answer = String(data?.answer || t("assistant.responseFailed")).trim();
  return answer;
}

function buildAssistantMessageFromResponse(data, t) {
  return {
    role: "assistant",
    content: formatAssistantChatContent(data, t),
    supportingPoints: Array.isArray(data?.supporting_points) ? data.supporting_points : [],
    suggestedFollowups: Array.isArray(data?.suggested_followups) ? data.suggested_followups : [],
    suggestedActions: Array.isArray(data?.suggested_actions) ? data.suggested_actions : [],
    scopeLabel: data?.scope_label || "",
  };
}

function compactHistoryContent(content) {
  const text = String(content || "")
    .replace(/\nDetails I used:[\s\S]*$/i, "")
    .replace(/\nDétails utilisés :[\s\S]*$/i, "")
    .trim();

  return text.length > 700 ? `${text.slice(0, 700).trim()}...` : text;
}

function buildAssistantActionUrl(action) {
  const params = new URLSearchParams();

  if (action?.account_id != null) params.set("account_id", action.account_id);
  if (action?.category) params.set("category", action.category);
  if (action?.transaction_type) params.set("type", action.transaction_type);
  if (action?.month) params.set("month", action.month);
  if (action?.section) params.set("section", action.section);
  if (action?.scenario_name) params.set("scenario", action.scenario_name);
  if (action?.saved_scenario_id != null) params.set("saved_scenario_id", action.saved_scenario_id);
  if (action?.compare_saved_scenario_id != null) {
    params.set("compare_saved_scenario_id", action.compare_saved_scenario_id);
  }
  if (action?.amount != null) params.set("amount", action.amount);
  if (action?.target_balance != null) params.set("target_balance", action.target_balance);
  if (action?.months_ahead != null) params.set("months_ahead", action.months_ahead);

  const routeMap = {
    analytics: "/analytics",
    assistant: "/assistant",
    budgets: "/budgets",
    dashboard: "/analytics",
    simulator: "/budgets",
    "money-map": "/analytics",
    accounts: "/profile",
    transactions: "/transactions",
  };
  const query = params.toString();

  return `${routeMap[action?.page] || "/analytics"}${query ? `?${query}` : ""}`;
}

function AssistantMessageDetails({ message, onFollowup, onAction, t }) {
  const supportingPoints = message.supportingPoints || [];
  const suggestedFollowups = message.suggestedFollowups || [];
  const suggestedActions = message.suggestedActions || [];
  const hasDetails =
    supportingPoints.length > 0 ||
    suggestedFollowups.length > 0 ||
    suggestedActions.length > 0 ||
    message.scopeLabel;

  if (message.role !== "assistant" || !hasDetails) {
    return null;
  }

  return (
    <div className="assistant-message-details">
      {message.scopeLabel && (
        <div className="assistant-message-scope">{message.scopeLabel}</div>
      )}

      {supportingPoints.length > 0 && (
        <div className="assistant-message-section">
          <div className="assistant-message-section-title">{t("assistant.supportingPoints")}</div>
          <ul className="assistant-message-list">
            {supportingPoints.map((point, index) => (
              <li key={`point-${index}`}>{point}</li>
            ))}
          </ul>
        </div>
      )}

      {suggestedActions.length > 0 && (
        <div className="assistant-message-section">
          <div className="assistant-message-section-title">{t("assistant.suggestedActions")}</div>
          <div className="assistant-message-chip-row">
            {suggestedActions.map((action, index) => (
              <button
                key={`action-${index}-${action.label}`}
                type="button"
                className="assistant-action-chip"
                onClick={() => onAction(action)}
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {suggestedFollowups.length > 0 && (
        <div className="assistant-message-section">
          <div className="assistant-message-section-title">{t("assistant.suggestedFollowups")}</div>
          <div className="assistant-message-chip-row">
            {suggestedFollowups.map((followup, index) => (
              <button
                key={`followup-${index}-${followup}`}
                type="button"
                className="assistant-followup-chip"
                onClick={() => onFollowup(followup)}
              >
                {followup}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AssistantPage() {
  const { language, t } = useLanguage();
  const [question, setQuestion] = useState("");
  const [assistantMode, setAssistantMode] = useState("balanced");
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [messages, setMessages] = useState(() => [buildInitialAssistantMessage(t)]);
  const [providerStatus, setProviderStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const submittingRef = useRef(false);

  const navigate = useNavigate();
  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);

  useEffect(() => {
    const savedMode = localStorage.getItem("assistantMode");
    if (savedMode) {
      setAssistantMode(savedMode);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("assistantMode", assistantMode);
  }, [assistantMode]);

  useEffect(() => {
    const loadAssistantStatus = async () => {
      try {
        setStatusLoading(true);
        const response = await api.get("/assistant/status");
        setProviderStatus(response.data);
      } catch (error) {
        console.error("Failed to load assistant status:", error);

        if (!handleApiAuthError(error, navigate)) {
          setProviderStatus(null);
        }
      } finally {
        setStatusLoading(false);
      }
    };

    loadAssistantStatus();
  }, [navigate]);

  useEffect(() => {
    const loadAssistantHistory = async () => {
      try {
        setHistoryLoading(true);
        const response = await api.get("/assistant/history", {
          params: {
            account_id: normalizedAccountId,
          },
        });
        setMessages(buildMessagesFromHistory(response.data.messages, t));
      } catch (error) {
        console.error("Failed to load assistant history:", error);

        if (!handleApiAuthError(error, navigate)) {
          setMessages([buildInitialAssistantMessage(t)]);
        }
      } finally {
        setQuestion("");
        setError("");
        setHistoryLoading(false);
      }
    };

    loadAssistantHistory();
  }, [language, navigate, normalizedAccountId, t]);

  const buildHistoryPayload = (existingMessages, newQuestion) => {
    return [
      ...existingMessages
        .filter(
          (message) => message.role === "user" || message.role === "assistant"
        )
        .map((message) => ({
          role: message.role,
          content: compactHistoryContent(message.content),
        }))
        .filter((message) => message.content.length > 0),
      {
        role: "user",
        content: newQuestion,
      },
    ].slice(-6);
  };

  const handleAsk = async () => {
    if (loading || submittingRef.current) {
      return;
    }

    const finalQuestion = question.trim();

    if (!finalQuestion) {
      setError(t("assistant.questionRequired"));
      return;
    }

    const userMessage = {
      role: "user",
      content: finalQuestion,
    };

    submittingRef.current = true;
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);

    try {
      setLoading(true);
      setError("");
      setQuestion("");

      const response = await api.post("/assistant/response", {
        question: finalQuestion,
        history: buildHistoryPayload(messages, finalQuestion),
        mode: assistantMode,
        account_id: normalizedAccountId,
      });

      const assistantMessage = buildAssistantMessageFromResponse(response.data, t);

      setMessages([...updatedMessages, assistantMessage]);
    } catch (error) {
      console.error("Failed to get assistant response:", error);

      if (!handleApiAuthError(error, navigate)) {
        setError(getApiErrorMessage(error, t("assistant.responseFailed")));
        setQuestion(finalQuestion);
        setMessages(messages);
      }
    } finally {
      submittingRef.current = false;
      setLoading(false);
    }
  };

  const handleClearConversation = async () => {
    try {
      setClearingHistory(true);
      setError("");
      await api.delete("/assistant/history", {
        params: {
          account_id: normalizedAccountId,
        },
      });
      setMessages([buildInitialAssistantMessage(t)]);
      setQuestion("");
    } catch (error) {
      console.error("Failed to clear assistant history:", error);

      if (!handleApiAuthError(error, navigate)) {
        setError(getApiErrorMessage(error, t("assistant.clearConversationFailed")));
      }
    } finally {
      setClearingHistory(false);
    }
  };

  const handleAssistantAction = (action) => {
    const externalUrl =
      action?.page === "external_resource" &&
      (String(action?.description || "").startsWith("http")
        ? action.description
        : String(action?.section || "").startsWith("http")
        ? action.section
        : "");

    if (externalUrl) {
      window.open(externalUrl, "_blank", "noopener,noreferrer");
      return;
    }

    navigate(buildAssistantActionUrl(action));
  };

  const handleFollowup = (followup) => {
    setQuestion(String(followup || ""));
  };

  const activeProvider = providerStatus?.providers?.find((provider) => provider.active);
  const providerLabel =
    activeProvider?.label ||
    (providerStatus?.active_provider === "openai"
      ? t("assistant.providerOpenAI")
      : providerStatus?.active_provider === "local"
      ? t("assistant.providerLocal")
      : t("assistant.providerRuleBased"));
  const providerMessage = statusLoading
    ? t("assistant.engineChecking")
    : providerStatus?.message || t("assistant.engineUnavailable");
  const providerUsageMessage =
    !statusLoading &&
    providerStatus?.active_provider !== "rule_based" &&
    providerStatus?.daily_limit != null
      ? t("assistant.engineUsage", {
          remaining: providerStatus.daily_remaining,
          limit: providerStatus.daily_limit,
        })
      : "";
  const providerCharUsageMessage =
    !statusLoading &&
    providerStatus?.active_provider !== "rule_based" &&
    providerStatus?.daily_char_limit != null
      ? t("assistant.engineCharUsage", {
          remaining: providerStatus.daily_chars_remaining,
          limit: providerStatus.daily_char_limit,
        })
      : "";

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <PageHeader
          icon={IconSparkles}
          titleKey="assistant.title"
          subtitleKey="headers.assistantSubtitle"
        />

        <div className="dashboard-card assistant-chat-shell">
          <div className="assistant-chat-topbar">
            <div className="assistant-control-grid">
              <div className="assistant-mode-field">
                <label htmlFor="assistant-mode">{t("assistant.modeLabel")}</label>
                <select
                  id="assistant-mode"
                  value={assistantMode}
                  onChange={(event) => setAssistantMode(event.target.value)}
                >
                  <option value="balanced">{t("assistant.balanced")}</option>
                  <option value="strict">{t("assistant.strict")}</option>
                  <option value="coach">{t("assistant.coach")}</option>
                </select>
              </div>

              <AccountSelector
                value={selectedAccountId}
                label={t("assistant.scopeLabel")}
                onChange={setSelectedAccountId}
              />
            </div>

            <div className="assistant-status-row">
              <span
                className={`assistant-provider-pill assistant-provider-${
                  providerStatus?.active_provider || "unknown"
                }`}
              >
                {providerLabel}
              </span>
              <span>{providerMessage}</span>
              {providerUsageMessage && <span>{providerUsageMessage}</span>}
              {providerCharUsageMessage && <span>{providerCharUsageMessage}</span>}
            </div>
          </div>

          <div className="assistant-thread" aria-live="polite">
            {historyLoading ? (
              <div className="assistant-loading-message">
                {t("assistant.historyLoading")}
              </div>
            ) : (
              messages.map((message, index) => (
                <div
                  key={`message-${index}`}
                  className={`assistant-message-row assistant-message-row-${message.role}`}
                >
                  <div className={`assistant-message-bubble assistant-message-${message.role}`}>
                    <div className="assistant-message-role">
                      {message.role === "assistant" ? t("common.assistant") : t("assistant.you")}
                    </div>
                    <p className="assistant-message-text">
                      <AssistantMessageContent text={message.content} />
                    </p>
                    <AssistantMessageDetails
                      message={message}
                      onAction={handleAssistantAction}
                      onFollowup={handleFollowup}
                      t={t}
                    />
                  </div>
                </div>
              ))
            )}

            {loading && (
              <div className="assistant-message-row assistant-message-row-assistant">
                <div className="assistant-message-bubble assistant-message-assistant assistant-thinking-bubble">
                  <div className="assistant-message-role">{t("common.assistant")}</div>
                  <p className="assistant-message-text">{t("assistant.thinking")}</p>
                </div>
              </div>
            )}
          </div>

          <form
            className="assistant-composer"
            onSubmit={(event) => {
              event.preventDefault();
              handleAsk();
            }}
          >
            <textarea
              rows={3}
              maxLength={1200}
              placeholder={t("assistant.questionPlaceholder")}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              className="assistant-input assistant-textarea assistant-chat-input"
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleAsk();
                }
              }}
            />
            <button
              type="submit"
              className="assistant-ask-button assistant-send-button"
              disabled={loading}
            >
              {loading ? t("assistant.thinking") : t("assistant.ask")}
            </button>
          </form>

          <div className="assistant-chat-footer">
            <p className="assistant-compose-hint">{t("assistant.composeHint")}</p>
            <button
              type="button"
              className="secondary-button assistant-clear-button"
              onClick={handleClearConversation}
              disabled={clearingHistory || historyLoading || messages.length <= 1}
            >
              {clearingHistory
                ? t("assistant.clearingConversation")
                : t("assistant.clearConversation")}
            </button>
          </div>

          {error && <p className="error-text">{error}</p>}
        </div>
      </div>
    </div>
  );
}

export default AssistantPage;
