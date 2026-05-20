import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import { useLanguage } from "../i18n/LanguageContext";
import { getApiErrorMessage, getApiSuccessMessage } from "../utils/errorUtils";

function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [resetUrl, setResetUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { t } = useLanguage();

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");
    setResetUrl("");

    try {
      setSubmitting(true);

      const response = await api.post("/auth/forgot-password", { email });

      setMessage(getApiSuccessMessage(response.data, t("auth.resetLinkSent")));
      setResetUrl(response.data.reset_url || "");
    } catch (err) {
      setError(getApiErrorMessage(err, t("auth.forgotFailed")));
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
              <p className="auth-card-kicker">{t("auth.accountRecovery")}</p>
              <h2>{t("auth.forgotPasswordTitle")}</h2>
              <p>{t("auth.forgotPasswordDetail")}</p>
            </div>

            <form onSubmit={handleForgotPassword} className="auth-form">
              <div className="auth-field">
                <label htmlFor="forgot-email">{t("auth.email")}</label>
                <input
                  id="forgot-email"
                  type="email"
                  placeholder={t("auth.emailPlaceholder")}
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
                {submitting ? t("auth.generating") : t("auth.sendResetLink")}
              </button>
            </form>

            {message && <p className="success-text">{message}</p>}
            {error && <p className="error-text">{error}</p>}

            {resetUrl && (
              <div className="reset-link-box">
                <p className="reset-link-label">{t("auth.testResetLink")}</p>
                <a href={resetUrl} className="auth-inline-link">
                  {t("auth.openResetPage")}
                </a>
              </div>
            )}

            <div className="auth-footer">
              <p>
                {t("auth.backTo")} <Link to="/">{t("auth.login")}</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ForgotPasswordPage;
