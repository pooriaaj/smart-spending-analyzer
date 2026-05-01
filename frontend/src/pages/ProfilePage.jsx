import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import PasswordField from "../components/PasswordField";
import { useLanguage } from "../i18n/LanguageContext";

function ProfilePage() {
  const navigate = useNavigate();
  const { t } = useLanguage();

  const [email, setEmail] = useState("");
  const [profileLoading, setProfileLoading] = useState(true);

  const [profileMessage, setProfileMessage] = useState("");
  const [profileError, setProfileError] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");

  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);

  const fetchProfile = useCallback(async () => {
    try {
      const response = await api.get("/users/me");
      setEmail(response.data.email);
    } catch (error) {
      handleApiAuthError(error, navigate);
    } finally {
      setProfileLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setProfileMessage("");
    setProfileError("");

    try {
      const response = await api.put("/users/me", { email });
      setEmail(response.data.email);
      setProfileMessage("Profile updated successfully.");
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setProfileError(
          error?.response?.data?.detail || "Failed to update profile."
        );
      }
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPasswordMessage("");
    setPasswordError("");

    try {
      const response = await api.put("/users/me/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });

      setPasswordMessage(response.data.message || "Password changed successfully.");
      setCurrentPassword("");
      setNewPassword("");
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setPasswordError(
          error?.response?.data?.detail || "Failed to change password."
        );
      }
    }
  };

  const handleDeleteAccount = async (e) => {
    e.preventDefault();
    setDeleteError("");

    if (deleteConfirmText !== "DELETE") {
      setDeleteError('Please type DELETE to confirm account deletion.');
      return;
    }

    try {
      setDeleting(true);

      await api.delete("/users/me", {
        data: {
          password: deletePassword,
        },
      });

      localStorage.removeItem("token");
      navigate("/", { replace: true });
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setDeleteError(
          error?.response?.data?.detail || "Failed to delete account."
        );
      }
    } finally {
      setDeleting(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/", { replace: true });
  };

  if (profileLoading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>{t("profile.loadingTitle")}</h2>
            <p>{t("profile.loadingDetail")}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">{t("profile.eyebrow")}</p>
            <h1>{t("profile.title")}</h1>
            <p className="hero-subtitle">
              {t("profile.subtitle")}
            </p>
          </div>

          <div className="header-actions">
            <button
              className="secondary-button"
              onClick={() => navigate("/dashboard")}
            >
              {t("common.dashboard")}
            </button>

            <button className="logout-button" onClick={handleLogout}>
              {t("common.logout")}
            </button>
          </div>
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>{t("profile.infoTitle")}</h2>
            <p>{t("profile.infoDetail")}</p>
          </div>

          <form className="transaction-form" onSubmit={handleUpdateProfile}>
            <input
              type="email"
              placeholder={t("profile.emailAddress")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <button type="submit">{t("profile.saveProfile")}</button>
          </form>

          {profileMessage && <p style={{ color: "green" }}>{profileMessage}</p>}
          {profileError && <p className="error-text">{profileError}</p>}
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>{t("profile.changePassword")}</h2>
            <p>{t("profile.changePasswordDetail")}</p>
          </div>

          <form className="auth-form" onSubmit={handleChangePassword}>
            <PasswordField
              label={t("profile.currentPassword")}
              name="current-password"
              placeholder={t("profile.currentPasswordPlaceholder")}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              required
            />

            <PasswordField
              label={t("profile.newPassword")}
              name="new-password"
              placeholder={t("profile.newPasswordPlaceholder")}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              required
            />

            <button type="submit" className="auth-submit-button">
              {t("profile.changePassword")}
            </button>
          </form>

          {passwordMessage && <p style={{ color: "green" }}>{passwordMessage}</p>}
          {passwordError && <p className="error-text">{passwordError}</p>}
        </div>

        <div id="plans" className="dashboard-card large-card premium-plans-card">
          <div className="section-header">
            <h2>Premium Plans</h2>
            <p>
              Free is for daily tracking and month-end reconciliation. Premium is for deeper forecasting,
              larger statement workflows, and smarter decision support.
            </p>
          </div>

          <div className="pricing-grid">
            <div className="pricing-card">
              <span className="pricing-kicker">Free</span>
              <h3>Smart Starter</h3>
              <p className="pricing-price">$0</p>
              <p>Manual tracking, basic statement import, current-month dashboard, and clean transaction review.</p>
              <button className="secondary-button" type="button">
                Current Plan
              </button>
            </div>

            <div className="pricing-card pricing-card-featured">
              <span className="pricing-kicker">Premium</span>
              <h3>Money Operator</h3>
              <p className="pricing-price">Coming soon</p>
              <p>
                Larger statement batches, advanced simulator plans, 3 and 6 month trend intelligence,
                recurring-charge levers, and personalized category learning controls.
              </p>
              <button className="premium-header-button" type="button">
                Notify Me
              </button>
            </div>
          </div>
        </div>

        <div className="dashboard-card large-card danger-zone-card">
          <div className="section-header">
            <h2>Danger Zone</h2>
            <p>
              Deleting your account permanently removes your profile, transactions,
              and saved category memory.
            </p>
          </div>

          <form className="auth-form" onSubmit={handleDeleteAccount}>
            <PasswordField
              label="Confirm Password"
              name="delete-password"
              placeholder="Enter your password"
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              autoComplete="current-password"
              required
            />

            <div className="auth-field">
              <label htmlFor="delete-confirm-text">
                Type <strong>DELETE</strong> to confirm
              </label>
              <input
                id="delete-confirm-text"
                type="text"
                placeholder="Type DELETE"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                required
              />
            </div>

            <button
              type="submit"
              className="delete-account-button"
              disabled={deleting}
            >
              {deleting ? "Deleting Account..." : "Delete Account"}
            </button>
          </form>

          {deleteError && <p className="error-text">{deleteError}</p>}
        </div>
      </div>
    </div>
  );
}

export default ProfilePage;
