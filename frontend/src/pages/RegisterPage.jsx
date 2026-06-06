import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../services/api";
import PasswordField from "../components/PasswordField";
import { useLanguage } from "../i18n/LanguageContext";

function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { t } = useLanguage();

  const handleRegister = async (e) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError(t("auth.passwordMismatch"));
      return;
    }

    try {
      await api.post("/auth/register", {
        email,
        password,
      });

      navigate("/import", { replace: true });
    } catch {
      setError(t("auth.registrationFailed"));
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-layout">
        <div className="auth-showcase">
          <div className="auth-showcase-content">
            <p className="auth-eyebrow">{t("common.appName")}</p>
            <h1>{t("auth.registerHeroTitle")}</h1>
            <p className="auth-description">{t("auth.registerHeroDetail")}</p>

            <div className="auth-feature-list">
              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>{t("auth.simpleOnboarding")}</strong>
                  <p>{t("auth.simpleOnboardingDetail")}</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>{t("auth.actionableAnalytics")}</strong>
                  <p>{t("auth.actionableAnalyticsDetail")}</p>
                </div>
              </div>

              <div className="auth-feature-item">
                <span className="auth-feature-dot" />
                <div>
                  <strong>{t("auth.guidedExploration")}</strong>
                  <p>{t("auth.guidedExplorationDetail")}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-panel">
          <div className="auth-card">
            <div className="auth-card-header">
              <p className="auth-card-kicker">{t("auth.getStarted")}</p>
              <h2>{t("auth.createAccount")}</h2>
              <p>{t("auth.createAccountDetail")}</p>
            </div>

            <form onSubmit={handleRegister} className="auth-form">
              <div className="auth-field">
                <label htmlFor="register-email">{t("auth.email")}</label>
                <input
                  id="register-email"
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
                name="register-password"
                placeholder={t("auth.createPassword")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
              />

              <PasswordField
                label={t("auth.confirmPassword")}
                name="register-confirm-password"
                placeholder={t("auth.confirmPasswordPlaceholder")}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />

              <button type="submit" className="auth-submit-button">
                {t("auth.createAccountButton")}
              </button>
            </form>

            {error && <p className="error-text">{error}</p>}

            <div className="auth-footer">
              <p>
                {t("auth.alreadyHaveAccount")} <Link to="/">{t("auth.login")}</Link>
              </p>
              <p className="legal-footer-text">{t("common.legalFooter")}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default RegisterPage;
