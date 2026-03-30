import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";

function AssistantPage() {
  const [question, setQuestion] = useState("");
  const [assistantResponse, setAssistantResponse] = useState(null);
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

  const handleAsk = async (customQuestion) => {
    const finalQuestion = (customQuestion ?? question).trim();

    if (!finalQuestion) {
      setError("Please enter a question.");
      return;
    }

    try {
      setLoading(true);
      setError("");

      const response = await api.post("/analytics/assistant-response", {
        question: finalQuestion,
      });

      setAssistantResponse(response.data);

      if (!customQuestion) {
        setQuestion("");
      }
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
            <h2>Ask a question</h2>
            <p>Try a quick prompt or write your own finance question.</p>
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
              placeholder="Ask something like: Give me saving advice"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="assistant-input"
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

        {assistantResponse && (
          <div className="dashboard-card assistant-response-card">
            <div className="section-header">
              <h2>Assistant Response</h2>
              <p>Here is your current finance answer based on your recorded data.</p>
            </div>

            <div className="assistant-answer-box">
              <h3>Main Answer</h3>
              <p>{assistantResponse.answer}</p>
            </div>

            <div className="assistant-response-grid">
              <div className="assistant-detail-block">
                <h3>Supporting Points</h3>
                {assistantResponse.supporting_points.length === 0 ? (
                  <p className="assistant-empty-text">No supporting points available.</p>
                ) : (
                  <ul className="assistant-list">
                    {assistantResponse.supporting_points.map((item, index) => (
                      <li key={`support-${index}`}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="assistant-detail-block">
                <h3>Suggested Follow-ups</h3>
                {assistantResponse.suggested_followups.length === 0 ? (
                  <p className="assistant-empty-text">No follow-up suggestions available.</p>
                ) : (
                  <div className="assistant-followup-list">
                    {assistantResponse.suggested_followups.map((item, index) => (
                      <button
                        key={`followup-${index}`}
                        type="button"
                        className="assistant-followup-button"
                        onClick={() => handleAsk(item)}
                        disabled={loading}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AssistantPage;