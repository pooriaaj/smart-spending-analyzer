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
    <div className="auth-shell auth-shell-recovery">
      <div className="auth-layout auth-layout-single auth-layout-recovery">
        <div className="auth-recovery-rail">
          <p className="auth-eyebrow">{t("common.appName")}</p>
          <h1>{t("auth.accountRecovery")}</h1>

          <div className="auth-recovery-steps" aria-label={t("auth.accountRecovery")}>
            <div className="auth-recovery-step active">
              <span>1</span>
              <strong>{t("auth.email")}</strong>
            </div>
            <div className="auth-recovery-line" aria-hidden="true" />
            <div className="auth-recovery-step">
              <span>2</span>
              <strong>{t("auth.resetPasswordTitle")}</strong>
            </div>
            <div className="auth-recovery-line" aria-hidden="true" />
            <div className="auth-recovery-step">
              <span>3</span>
              <strong>{t("auth.login")}</strong>
            </div>
          </div>
        </div>

        <div className="auth-panel auth-panel-centered">
          <div className="auth-card auth-recovery-card">
            <div className="auth-card-topline" aria-hidden="true" />
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

            <div className="auth-feedback-stack">
              {message && <p className="success-text">{message}</p>}
              {error && <p className="error-text">{error}</p>}
            </div>

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
