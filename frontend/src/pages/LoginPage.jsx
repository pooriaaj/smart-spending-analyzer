import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../services/api";
import PasswordField from "../components/PasswordField";

function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleExploreChange = (event) => {
    const value = event.target.value;
    if (!value) return;

    if (value === "create") {
      navigate("/register");
    }
    event.target.value = "";
  };

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
              Write daily transactions, reconcile bank statements at month-end, and let the app
              learn your categories, recurring habits, and future money outlook.
            </p>

            <div className="public-nav-strip">
              <label htmlFor="public-explore">Explore</label>
              <select id="public-explore" defaultValue="" onChange={handleExploreChange}>
                <option value="" disabled>
                  Choose where to start
                </option>
                <option value="create">Create free account</option>
              </select>
            </div>

            <div className="auth-feature-list">
              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>Month-end reconciliation</strong>
                  <p>Compare what you wrote daily against your real bank statement.</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>Learned category memory</strong>
                  <p>Teach the app your personal naming habits instead of accepting generic guesses.</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>Premium planning cockpit</strong>
                  <p>Advanced forecasts, larger statement batches, saved scenarios, and guided spending plans.</p>
                </div>
              </div>
            </div>

            <div className="auth-premium-card">
              <strong>Premium preview</strong>
              <p>
                Unlock deeper 3 and 6 month analysis, bigger import batches, simulator portfolios,
                and smarter recurring-charge decisions when plans launch.
              </p>
              <Link to="/register">Start free, upgrade later</Link>
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

              <div className="auth-inline-link-row">
                <Link to="/forgot-password" className="auth-inline-link">
                  Forgot password?
                </Link>
              </div>

              <button type="submit" className="auth-submit-button">
                Login
              </button>
            </form>

            {error && <p className="error-text">{error}</p>}

            <div className="auth-footer">
              <p>
                Don't have an account? <Link to="/register">Create one</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
