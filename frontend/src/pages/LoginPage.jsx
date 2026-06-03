import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../services/api";
import PasswordField from "../components/PasswordField";
import { useLanguage } from "../i18n/LanguageContext";

function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { t } = useLanguage();

  const handleExploreChange = (event) => {
    const value = event.target.value;
    if (!value) return;

    if (value === "create") {
      navigate("/register");
    }
    event.target.value = "";
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");

    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      await api.post("/auth/login", formData, {
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      });

      navigate("/analytics", { replace: true });
    } catch {
      setError(t("auth.loginFailed"));
    }
  };

  return (
    <div className="auth-shell auth-shell-login">
      <div className="auth-layout">
        <div className="auth-showcase">
          <div className="auth-showcase-content">
            <p className="auth-eyebrow">{t("common.appName")}</p>
            <h1>{t("auth.heroTitle")}</h1>
            <p className="auth-description">
              {t("auth.heroDescription")}
            </p>

            <div className="public-nav-strip">
              <label htmlFor="public-explore">{t("auth.explore")}</label>
              <select id="public-explore" defaultValue="" onChange={handleExploreChange}>
                <option value="" disabled>
                  {t("auth.chooseWhereToStart")}
                </option>
                <option value="create">{t("auth.createFreeAccount")}</option>
              </select>
            </div>

            <div className="auth-feature-list">
              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>{t("auth.monthEndTitle")}</strong>
                  <p>{t("auth.monthEndDetail")}</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>{t("auth.categoryMemoryTitle")}</strong>
                  <p>{t("auth.categoryMemoryDetail")}</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>{t("auth.premiumTitle")}</strong>
                  <p>{t("auth.premiumDetail")}</p>
                </div>
              </div>
            </div>

            <div className="auth-premium-card">
              <strong>{t("auth.premiumPreview")}</strong>
              <p>{t("auth.premiumPreviewDetail")}</p>
              <Link to="/register">{t("auth.startFree")}</Link>
            </div>
          </div>
        </div>

        <div className="auth-panel">
          <div className="auth-card auth-card-login">
            <div className="auth-card-topline" aria-hidden="true" />
            <div className="auth-card-header">
              <p className="auth-card-kicker">{t("auth.welcomeBack")}</p>
              <h2>{t("auth.login")}</h2>
              <p>{t("auth.loginDetail")}</p>
            </div>

            <form onSubmit={handleLogin} className="auth-form">
              <div className="auth-field">
                <label htmlFor="login-email">{t("auth.email")}</label>
                <input
                  id="login-email"
                  type="email"
                  placeholder={t("auth.emailPlaceholder")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>

              <PasswordField
                label={t("auth.password")}
                name="login-password"
                placeholder={t("auth.passwordPlaceholder")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />

              <div className="auth-inline-link-row">
                <Link to="/forgot-password" className="auth-inline-link">
                  {t("auth.forgotPassword")}
                </Link>
              </div>

              <button type="submit" className="auth-submit-button">
                {t("auth.login")}
              </button>
            </form>

            {error && <p className="error-text">{error}</p>}

            <div className="auth-footer">
              <p>
                {t("auth.noAccount")} <Link to="/register">{t("auth.createOne")}</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
