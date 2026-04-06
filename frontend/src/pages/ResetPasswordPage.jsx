import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "../services/api";
import PasswordField from "../components/PasswordField";

function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");

    if (!token) {
      setError("Missing reset token.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    try {
      setSubmitting(true);

      const response = await api.post("/auth/reset-password", {
        token,
        new_password: newPassword,
      });

      setMessage(response.data.message || "Password reset successfully.");
      setTimeout(() => {
        navigate("/", { replace: true });
      }, 1500);
    } catch (err) {
      setError(
        err?.response?.data?.detail || "Failed to reset password."
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
              <h2>Reset password</h2>
              <p>Create a new password for your account.</p>
            </div>

            <form onSubmit={handleResetPassword} className="auth-form">
              <PasswordField
                label="New Password"
                name="reset-new-password"
                placeholder="Enter your new password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                required
              />

              <PasswordField
                label="Confirm New Password"
                name="reset-confirm-password"
                placeholder="Confirm your new password"
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
                {submitting ? "Resetting..." : "Reset Password"}
              </button>
            </form>

            {message && <p className="success-text">{message}</p>}
            {error && <p className="error-text">{error}</p>}

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

export default ResetPasswordPage;