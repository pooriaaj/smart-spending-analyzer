import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";

function AssistantPage() {
  const [question, setQuestion] = useState("");
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

  const fallbackQuestions = [
    "What is my balance?",
    "What is my top expense category?",
    "Did my spending increase?",
    "Show my recent transactions",
    "Give me saving advice",
    "Summarize my finances",
  ];

  useEffect(() => {
    const loadSuggestions = async () => {
      try {
        setSuggestionsLoading(true);
        const response = await api.get("/analytics/assistant-suggestions");
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
  }, [navigate]);

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

    if (action.page === "analytics") {
      const params = new URLSearchParams();

      if (action.section) params.set("section", action.section);
      if (action.category) params.set("category", action.category);
      if (action.month) params.set("month", action.month);

      navigate(`/analytics${params.toString() ? `?${params.toString()}` : ""}`);
      return;
    }

    if (action.page === "transactions") {
      const params = new URLSearchParams();

      if (action.category) params.set("category", action.category);
      if (action.transaction_type) params.set("type", action.transaction_type);
      if (action.month) params.set("month", action.month);

      navigate(`/transactions${params.toString() ? `?${params.toString()}` : ""}`);
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
          </div>
        </div>

        <div className="dashboard-card assistant-card">
          <div className="section-header">
            <h2>Smart prompts</h2>
            <p>
              {suggestionsLoading
                ? "Loading finance-aware prompts..."
                : "These prompts are generated from your current financial data."}
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