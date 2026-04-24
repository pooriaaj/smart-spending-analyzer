import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
  setSelectedAccountId as persistSelectedAccountId,
} from "../services/accountStorage";

function AssistantPage() {
  const initialAssistantMessage = {
    role: "assistant",
    content:
      "Hi - I'm your financial assistant. Ask me about your balance, spending changes, alerts, recent transactions, categories, or savings.",
    data: null,
  };
  const [question, setQuestion] = useState("");
  const [assistantMode, setAssistantMode] = useState("balanced");
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hi — I’m your financial assistant. Ask me about your balance, spending changes, alerts, recent transactions, categories, or savings.",
      data: null,
    },
  ]);
  const [smartSuggestions, setSmartSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [suggestionsLoading, setSuggestionsLoading] = useState(true);
  const [error, setError] = useState("");

  const navigate = useNavigate();
  const didMountScopeRef = useRef(false);
  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);

  const fallbackQuestions = [
    "What is my balance?",
    "What is my top expense category?",
    "Did my spending increase?",
    "Show my recent transactions",
    "Give me saving advice",
    "Summarize my finances",
  ];

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
    if (!didMountScopeRef.current) {
      didMountScopeRef.current = true;
      return;
    }

    setMessages([initialAssistantMessage]);
    setQuestion("");
    setError("");
  }, [selectedAccountId]);

  useEffect(() => {
    const loadSuggestions = async () => {
      try {
        setSuggestionsLoading(true);
        const response = await api.get("/analytics/assistant-suggestions", {
          params: {
            account_id: normalizedAccountId,
          },
        });
        setSmartSuggestions(response.data.suggestions || []);
      } catch (error) {
        console.error("Failed to load assistant suggestions:", error);

        if (!handleApiAuthError(error, navigate)) {
          setSmartSuggestions(fallbackQuestions);
        }
      } finally {
        setSuggestionsLoading(false);
      }
    };

    loadSuggestions();
  }, [navigate, normalizedAccountId]);

  const buildHistoryPayload = (existingMessages, newQuestion) => {
    return [
      ...existingMessages
        .filter(
          (message) => message.role === "user" || message.role === "assistant"
        )
        .map((message) => ({
          role: message.role,
          content: message.content,
        })),
      {
        role: "user",
        content: newQuestion,
      },
    ].slice(-8);
  };

  const handleActionNavigation = (action) => {
    if (!action) return;
    const actionAccountValue =
      action.account_id == null ? ALL_ACCOUNTS_VALUE : String(action.account_id);
    persistSelectedAccountId(actionAccountValue);

    if (action.page === "analytics") {
      const params = new URLSearchParams();

      if (action.section) params.set("section", action.section);
      if (action.category) params.set("category", action.category);
      if (action.month) params.set("month", action.month);

      navigate(`/analytics${params.toString() ? `?${params.toString()}` : ""}`);
      return;
    }

    if (action.page === "budgets") {
      const params = new URLSearchParams();

      if (action.month) params.set("month", action.month);
      if (action.category) params.set("category", action.category);
      if (action.amount != null) params.set("amount", String(action.amount));

      navigate(`/budgets${params.toString() ? `?${params.toString()}` : ""}`);
      return;
    }

    if (action.page === "simulator") {
      const params = new URLSearchParams();

      if (action.saved_scenario_id != null) {
        params.set("saved_scenario_id", String(action.saved_scenario_id));
      }
      if (action.compare_saved_scenario_id != null) {
        params.set("compare_saved_scenario_id", String(action.compare_saved_scenario_id));
      }
      if (action.scenario_name) {
        params.set("scenario_name", action.scenario_name);
      }
      if (action.months_ahead != null) params.set("months", String(action.months_ahead));
      if (action.target_balance != null) params.set("target_balance", String(action.target_balance));
      if (action.income_adjustment != null) {
        params.set("income_adjustment", String(action.income_adjustment));
      }
      if (action.expense_adjustment != null) {
        params.set("expense_adjustment", String(action.expense_adjustment));
      }
      if (action.event_month_offset != null) {
        params.set("event_month_offset", String(action.event_month_offset));
      }
      if (action.event_amount != null) {
        params.set("event_amount", String(action.event_amount));
      }
      if (action.event_label) {
        params.set("event_label", action.event_label);
      }

      navigate(`/simulator${params.toString() ? `?${params.toString()}` : ""}`);
      return;
    }

    if (action.page === "transactions") {
      const params = new URLSearchParams();

      if (action.section) params.set("section", action.section);
      if (action.category) params.set("category", action.category);
      if (action.description) params.set("description", action.description);
      if (action.transaction_type) params.set("type", action.transaction_type);
      if (action.month) params.set("month", action.month);

      navigate(`/transactions${params.toString() ? `?${params.toString()}` : ""}`);
      return;
    }

    if (action.page === "dashboard") {
      navigate("/dashboard");
      return;
    }

    if (action.page === "accounts") {
      navigate("/accounts");
      return;
    }

    if (action.page === "external_resource") {
      const topic = encodeURIComponent(action.section || "budgeting basics");
      window.open(`https://www.google.com/search?q=${topic}`, "_blank");
    }
  };

  const handleAsk = async (customQuestion) => {
    const finalQuestion = (customQuestion ?? question).trim();

    if (!finalQuestion) {
      setError("Please enter a question.");
      return;
    }

    const userMessage = {
      role: "user",
      content: finalQuestion,
      data: null,
    };

    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);

    try {
      setLoading(true);
      setError("");
      setQuestion("");

      const response = await api.post("/analytics/assistant-response", {
        question: finalQuestion,
        history: buildHistoryPayload(messages, finalQuestion),
        mode: assistantMode,
        account_id: normalizedAccountId,
      });

      const assistantMessage = {
        role: "assistant",
        content: response.data.answer,
        data: response.data,
      };

      setMessages([...updatedMessages, assistantMessage]);
    } catch (error) {
      console.error("Failed to get assistant response:", error);

      if (!handleApiAuthError(error, navigate)) {
        setError("Failed to get assistant response.");
      }
    } finally {
      setLoading(false);
    }
  };

  const displayedSuggestions =
    smartSuggestions.length > 0 ? smartSuggestions : fallbackQuestions;

  const modeDescription =
    assistantMode === "strict"
      ? "Direct and accountability-focused."
      : assistantMode === "coach"
      ? "Supportive and motivating."
      : "Neutral and practical.";
  const scopeDescription =
    selectedAccountId === ALL_ACCOUNTS_VALUE
      ? "All accounts combined."
      : "Focused on the selected account only.";

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">Smart Spending Analyzer</p>
            <h1>Financial Assistant</h1>
            <p className="hero-subtitle">
              Ask questions about your balance, trends, alerts, categories, recent activity, and savings.
            </p>
          </div>

          <div className="header-actions">
            <button
              className="secondary-button"
              onClick={() => navigate("/dashboard")}
            >
              Back to Dashboard
            </button>

            <button
              className="secondary-button"
              onClick={() => navigate("/analytics")}
            >
              View Analytics
            </button>

            <button
              className="secondary-button"
              onClick={() => navigate("/budgets")}
            >
              Budgets
            </button>

            <button
              className="secondary-button"
              onClick={() => navigate("/simulator")}
            >
              Simulator
            </button>
          </div>
        </div>

        <div className="dashboard-card assistant-card">
          <div className="section-header">
            <h2>Assistant mode</h2>
            <p>Choose how you want the assistant to respond.</p>
          </div>

          <div className="assistant-mode-row">
            <div className="assistant-mode-field">
              <label htmlFor="assistant-mode">Personality mode</label>
              <select
                id="assistant-mode"
                value={assistantMode}
                onChange={(e) => setAssistantMode(e.target.value)}
              >
                <option value="balanced">Balanced</option>
                <option value="strict">Strict</option>
                <option value="coach">Coach</option>
              </select>
            </div>

            <div className="assistant-mode-note">
              <strong>Current mode:</strong> {modeDescription}
            </div>
          </div>
        </div>

        <div className="dashboard-card assistant-card">
          <div className="section-header">
            <h2>Assistant scope</h2>
            <p>Choose whether answers should use all accounts combined or one specific account.</p>
          </div>

          <div className="assistant-mode-row">
            <AccountSelector
              label="Assistant scope"
              onChange={setSelectedAccountId}
            />

            <div className="assistant-mode-note">
              <strong>Current scope:</strong> {scopeDescription}
            </div>
          </div>
        </div>

        <div className="dashboard-card assistant-card">
          <div className="section-header">
            <h2>Smart prompts</h2>
            <p>
              {suggestionsLoading
                ? "Loading finance-aware prompts..."
                : "These prompts are generated from your current financial data in the selected scope."}
            </p>
          </div>

          <div className="assistant-preset-grid">
            {displayedSuggestions.map((preset) => (
              <button
                key={preset}
                type="button"
                className="assistant-preset-button"
                onClick={() => handleAsk(preset)}
                disabled={loading}
              >
                {preset}
              </button>
            ))}
          </div>

          <div className="assistant-input-row">
            <input
              type="text"
              placeholder="Ask something like: Why did my spending increase?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="assistant-input"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAsk();
              }}
            />
            <button
              type="button"
              className="assistant-ask-button"
              onClick={() => handleAsk()}
              disabled={loading}
            >
              {loading ? "Thinking..." : "Ask"}
            </button>
          </div>

          {error && <p className="error-text">{error}</p>}
        </div>

        <div className="dashboard-card assistant-chat-card">
          <div className="section-header">
            <h2>Conversation</h2>
            <p>Your assistant keeps short conversation context and uses your analytics data to answer better.</p>
          </div>

          <div className="assistant-chat-list">
            {messages.map((message, index) => (
              <div
                key={`message-${index}`}
                className={`assistant-chat-bubble assistant-chat-${message.role}`}
              >
                <div className="assistant-chat-role">
                  {message.role === "assistant" ? "Assistant" : "You"}
                </div>

                <p className="assistant-chat-text">{message.content}</p>

                {message.role === "assistant" && message.data && (
                  <div className="assistant-chat-details">
                    {message.data.scope_label && (
                      <div className="assistant-chat-detail-block">
                        <h4>Answer Scope</h4>
                        <p className="assistant-scope-summary">{message.data.scope_label}</p>
                      </div>
                    )}

                    {message.data.supporting_points?.length > 0 && (
                      <div className="assistant-chat-detail-block">
                        <h4>Supporting Points</h4>
                        <ul className="assistant-list">
                          {message.data.supporting_points.map((item, idx) => (
                            <li key={`support-${index}-${idx}`}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="assistant-chat-detail-block">
                      <h4>Suggested Follow-ups</h4>
                      {message.data.suggested_followups?.length > 0 ? (
                        <div className="assistant-followup-list">
                          {message.data.suggested_followups.map((item, idx) => (
                            <button
                              key={`followup-${index}-${idx}`}
                              type="button"
                              className="assistant-followup-button"
                              onClick={() => handleAsk(item)}
                              disabled={loading}
                            >
                              {item}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="assistant-empty-text">
                          No follow-up suggestions available.
                        </p>
                      )}
                    </div>

                    {message.data.suggested_actions?.length > 0 && (
                      <div className="assistant-chat-detail-block assistant-actions-block">
                        <h4>Suggested Actions</h4>
                        <div className="assistant-followup-list">
                          {message.data.suggested_actions.map((action, idx) => (
                            <button
                              key={`action-${index}-${idx}`}
                              type="button"
                              className="assistant-action-button"
                              onClick={() => handleActionNavigation(action)}
                            >
                              {action.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default AssistantPage;
