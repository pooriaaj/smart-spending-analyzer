import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import PasswordField from "../components/PasswordField";
import { useLanguage } from "../i18n/LanguageContext";

function ProfilePage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const deleteConfirmationWord = t("profile.deleteConfirmationWord");

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
      setProfileMessage(t("profile.profileUpdated"));
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setProfileError(
          error?.response?.data?.detail || t("profile.profileUpdateFailed")
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

      setPasswordMessage(response.data.message || t("profile.passwordChanged"));
      setCurrentPassword("");
      setNewPassword("");
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setPasswordError(
          error?.response?.data?.detail || t("profile.passwordChangeFailed")
        );
      }
    }
  };

  const handleDeleteAccount = async (e) => {
    e.preventDefault();
    setDeleteError("");

    if (deleteConfirmText.trim().toUpperCase() !== deleteConfirmationWord.toUpperCase()) {
      setDeleteError(t("profile.deleteConfirmError"));
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
          error?.response?.data?.detail || t("profile.deleteFailed")
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
            <h2>{t("profile.premiumPlans")}</h2>
            <p>{t("profile.premiumPlansDetail")}</p>
          </div>

          <div className="pricing-grid">
            <div className="pricing-card">
              <span className="pricing-kicker">{t("profile.free")}</span>
              <h3>{t("profile.smartStarter")}</h3>
              <p className="pricing-price">$0</p>
              <p>{t("profile.freePlanDetail")}</p>
              <button className="secondary-button" type="button">
                {t("profile.currentPlan")}
              </button>
            </div>

            <div className="pricing-card pricing-card-featured">
              <span className="pricing-kicker">{t("common.premium")}</span>
              <h3>{t("profile.moneyOperator")}</h3>
              <p className="pricing-price">{t("profile.comingSoon")}</p>
              <p>{t("profile.premiumPlanDetail")}</p>
              <button className="premium-header-button" type="button">
                {t("profile.notifyMe")}
              </button>
            </div>
          </div>
        </div>

        <div className="dashboard-card large-card danger-zone-card">
          <div className="section-header">
            <h2>{t("profile.dangerZone")}</h2>
            <p>{t("profile.dangerZoneDetail")}</p>
          </div>

          <form className="auth-form" onSubmit={handleDeleteAccount}>
            <PasswordField
              label={t("profile.confirmPassword")}
              name="delete-password"
              placeholder={t("profile.enterPassword")}
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              autoComplete="current-password"
              required
            />

            <div className="auth-field">
              <label htmlFor="delete-confirm-text">
                {t("profile.typeDelete")}
              </label>
              <input
                id="delete-confirm-text"
                type="text"
                placeholder={t("profile.typeDeletePlaceholder")}
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
              {deleting ? t("profile.deletingAccount") : t("profile.deleteAccount")}
            </button>
          </form>

          {deleteError && <p className="error-text">{deleteError}</p>}
        </div>
      </div>
    </div>
  );
}

export default ProfilePage;
