import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../services/api";
import PasswordField from "../components/PasswordField";

function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      navigate("/dashboard", { replace: true });
    }
  }, [navigate]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");

    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const response = await api.post("/auth/login", formData, {
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      });

      localStorage.setItem("token", response.data.access_token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError("Login failed. Please check your email and password.");
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-layout">
        <div className="auth-showcase">
          <div className="auth-showcase-content">
            <p className="auth-eyebrow">Smart Spending Analyzer</p>
            <h1>Understand your money with a cleaner, smarter workflow.</h1>
            <p className="auth-description">
              Track transactions, detect trends, uncover overspending patterns,
              and use an assistant designed to turn financial data into clear decisions.
            </p>

            <div className="auth-feature-list">
              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>Spending intelligence</strong>
                  <p>Insights, trends, alerts, and category analysis in one place.</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>CSV import + validation</strong>
                  <p>Bring in bank-style transaction data with duplicate protection.</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>Built-in financial assistant</strong>
                  <p>Ask natural questions and explore guided next actions.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-panel">
          <div className="auth-card">
            <div className="auth-card-header">
              <p className="auth-card-kicker">Welcome back</p>
              <h2>Login</h2>
              <p>Sign in to access your dashboard, analytics, and assistant.</p>
            </div>

            <form onSubmit={handleLogin} className="auth-form">
              <div className="auth-field">
                <label htmlFor="login-email">Email</label>
                <input
                  id="login-email"
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
                name="login-password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />

              <button type="submit" className="auth-submit-button">
                Login
              </button>
            </form>

            {error && <p className="error-text">{error}</p>}

            <div className="auth-footer">
              <p>
                Don’t have an account? <Link to="/register">Create one</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;