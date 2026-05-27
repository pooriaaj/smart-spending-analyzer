import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "../services/api";
import PasswordField from "../components/PasswordField";
import { useLanguage } from "../i18n/LanguageContext";
import { getApiErrorMessage, getApiSuccessMessage } from "../utils/errorUtils";

function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { t } = useLanguage();

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");

    if (!token) {
      setError(t("auth.missingResetToken"));
      return;
    }

    if (newPassword !== confirmPassword) {
      setError(t("auth.passwordMismatch"));
      return;
    }

    try {
      setSubmitting(true);

      const response = await api.post("/auth/reset-password", {
        token,
        new_password: newPassword,
      });

      window.history.replaceState(null, "", "/reset-password");
      setMessage(getApiSuccessMessage(response.data, t("auth.passwordResetSuccess")));
      setTimeout(() => {
        navigate("/", { replace: true });
      }, 1500);
    } catch (err) {
      setError(getApiErrorMessage(err, t("auth.resetFailed")));
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
              <h2>{t("auth.resetPasswordTitle")}</h2>
              <p>{t("auth.resetPasswordDetail")}</p>
            </div>

            <form onSubmit={handleResetPassword} className="auth-form">
              <PasswordField
                label={t("auth.newPassword")}
                name="reset-new-password"
                placeholder={t("auth.newPasswordPlaceholder")}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                required
              />

              <PasswordField
                label={t("auth.confirmNewPassword")}
                name="reset-confirm-password"
                placeholder={t("auth.confirmNewPasswordPlaceholder")}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />

              <button
                type="submit"
                className="auth-submit-button"
                disabled={submitting}
              >
                {submitting ? t("auth.resetting") : t("auth.resetPasswordButton")}
              </button>
            </form>

            {message && <p className="success-text">{message}</p>}
            {error && <p className="error-text">{error}</p>}

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

export default ResetPasswordPage;
