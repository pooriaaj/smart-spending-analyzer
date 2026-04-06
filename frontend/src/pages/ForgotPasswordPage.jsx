import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";

function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [resetUrl, setResetUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");
    setResetUrl("");

    try {
      setSubmitting(true);

      const response = await api.post("/auth/forgot-password", { email });

      setMessage(response.data.message);
      setResetUrl(response.data.reset_url || "");
    } catch (err) {
      setError(
        err?.response?.data?.detail || "Failed to process forgot password request."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-layout auth-layout-single">
        <div className="auth-panel auth-panel-centered">
          <div className="auth-card">
            <div className="auth-card-header">
              <p className="auth-card-kicker">Account recovery</p>
              <h2>Forgot password</h2>
              <p>Enter your email and we’ll generate a password reset link.</p>
            </div>

            <form onSubmit={handleForgotPassword} className="auth-form">
              <div className="auth-field">
                <label htmlFor="forgot-email">Email</label>
                <input
                  id="forgot-email"
                  type="email"
                  placeholder="Enter your email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>

              <button
                type="submit"
                className="auth-submit-button"
                disabled={submitting}
              >
                {submitting ? "Generating..." : "Send Reset Link"}
              </button>
            </form>

            {message && <p className="success-text">{message}</p>}
            {error && <p className="error-text">{error}</p>}

            {resetUrl && (
              <div className="reset-link-box">
                <p className="reset-link-label">Test reset link:</p>
                <a href={resetUrl} className="auth-inline-link">
                  Open password reset page
                </a>
              </div>
            )}

            <div className="auth-footer">
              <p>
                Back to <Link to="/">Login</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ForgotPasswordPage;