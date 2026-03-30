import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";

function AssistantPage() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hi — I’m your financial assistant. Ask me about your balance, spending, categories, or savings.",
      data: null,
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const navigate = useNavigate();

  const presetQuestions = [
    "What is my balance?",
    "What is my top expense category?",
    "Did my spending increase?",
    "Give me saving advice",
    "Summarize my finances",
  ];

  const buildHistoryPayload = (existingMessages, newQuestion) => {
    const historyMessages = [...existingMessages]
      .filter((message) => message.role === "user" || message.role === "assistant")
      .map((message) => ({
        role: message.role,
        content: message.content,
      }));

    historyMessages.push({
      role: "user",
      content: newQuestion,
    });

    return historyMessages.slice(-8);
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
    } catch (err) {
      console.error("Failed to get assistant response:", err);
      setError("Failed to get assistant response.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">Smart Spending Analyzer</p>
            <h1>Financial Assistant</h1>
            <p className="hero-subtitle">
              Ask questions about your balance, spending, categories, and savings.
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
            <h2>Quick prompts</h2>
            <p>Start with a common question or type your own.</p>
          </div>

          <div className="assistant-preset-grid">
            {presetQuestions.map((preset) => (
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
              placeholder="Ask something like: How can I reduce my top expense category?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="assistant-input"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleAsk();
                }
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
            <p>Your assistant now keeps short conversation context for follow-up questions.</p>
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

                    {message.data.suggested_followups?.length > 0 && (
                      <div className="assistant-chat-detail-block">
                        <h4>Suggested Follow-ups</h4>
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