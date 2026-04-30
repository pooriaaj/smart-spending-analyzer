import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../services/api";
import PasswordField from "../components/PasswordField";

function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      navigate("/dashboard", { replace: true });
    }
  }, [navigate]);

  const handleRegister = async (e) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    try {
      const response = await api.post("/auth/register", {
        email,
        password,
      });

      localStorage.setItem("token", response.data.access_token);
      navigate("/money-map", { replace: true });
    } catch {
      setError("Registration failed. Email may already be in use.");
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-layout">
        <div className="auth-showcase">
          <div className="auth-showcase-content">
            <p className="auth-eyebrow">Smart Spending Analyzer</p>
            <h1>Build a better view of your spending from day one.</h1>
            <p className="auth-description">
              Create your account to import transactions, explore analytics, and
              use intelligent guidance designed around your financial behavior.
            </p>

            <div className="auth-feature-list">
              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>Simple onboarding</strong>
                  <p>Start with manual entries or import your existing records.</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>Actionable analytics</strong>
                  <p>See what changed, what dominates spending, and where to improve.</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>Assistant-guided exploration</strong>
                  <p>Ask questions and move naturally through your data.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-panel">
          <div className="auth-card">
            <div className="auth-card-header">
              <p className="auth-card-kicker">Get started</p>
              <h2>Create account</h2>
              <p>Set up your account and start using the full platform.</p>
            </div>

            <form onSubmit={handleRegister} className="auth-form">
              <div className="auth-field">
                <label htmlFor="register-email">Email</label>
                <input
                  id="register-email"
                  type="email"
                  placeholder="Enter your email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>

              <PasswordField
                label="Password"
                name="register-password"
                placeholder="Create a password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
              />

              <PasswordField
                label="Confirm Password"
                name="register-confirm-password"
                placeholder="Confirm your password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />

              <button type="submit" className="auth-submit-button">
                Create Account
              </button>
            </form>

            {error && <p className="error-text">{error}</p>}

            <div className="auth-footer">
              <p>
                Already have an account? <Link to="/">Login</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default RegisterPage;
