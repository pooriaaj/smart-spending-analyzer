import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import { setSelectedAccountId } from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import { getAccountsFromResponse } from "../utils/accountResponses";
import { formatAccountName, formatAccountType, formatCategoryLabel } from "../utils/displayLabels";
import { getApiErrorMessage } from "../utils/errorUtils";

function AccountsPage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [accounts, setAccounts] = useState([]);
  const [name, setName] = useState("");
  const [type, setType] = useState("chequing");
  const [error, setError] = useState("");

  const fetchAccounts = async () => {
    try {
      const response = await api.get("/accounts/");
      setAccounts(getAccountsFromResponse(response.data));
    } catch (error) {
      handleApiAuthError(error, navigate);
    }
  };

  useEffect(() => {
    const loadAccounts = async () => {
      try {
        const response = await api.get("/accounts/");
        setAccounts(getAccountsFromResponse(response.data));
      } catch (error) {
        handleApiAuthError(error, navigate);
      }
    };

    loadAccounts();
  }, [navigate]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setError("");

    try {
      await api.post("/accounts/", { name, type });
      setName("");
      setType("chequing");
      await fetchAccounts();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setError(getApiErrorMessage(error, t("accounts.createFailed")));
      }
    }
  };

  const handleDelete = async (accountId) => {
    try {
      await api.delete(`/accounts/${accountId}`);
      await fetchAccounts();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setError(getApiErrorMessage(error, t("accounts.deleteFailed")));
      }
    }
  };

  const handleReviewAccount = (accountId) => {
    setSelectedAccountId(String(accountId));
    navigate("/dashboard");
  };

  const visibleAccounts = Array.isArray(accounts) ? accounts : [];

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">{t("common.appName")}</p>
            <h1>{t("common.accounts")}</h1>
            <p className="hero-subtitle">{t("headers.accountsSubtitle")}</p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              {t("common.backToDashboard")}
            </button>
          </div>
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>{t("accounts.createAccount")}</h2>
            <p>{t("accounts.createAccountDetail")}</p>
          </div>

          <form className="transaction-form" onSubmit={handleCreate}>
            <input
              type="text"
              placeholder={t("accounts.accountName")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />

            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="chequing">{t("accounts.chequing")}</option>
              <option value="savings">{t("accounts.savings")}</option>
              <option value="credit_card">{t("accounts.creditCard")}</option>
              <option value="cash">{t("accounts.cash")}</option>
              <option value="business">{t("accounts.business")}</option>
              <option value="other">{t("accounts.other")}</option>
            </select>

            <button type="submit">{t("accounts.createAccount")}</button>
          </form>

          {error && <p className="error-text">{error}</p>}
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <h2>{t("accounts.yourAccounts")}</h2>
          </div>

          {visibleAccounts.length === 0 ? (
            <div className="empty-state"><p>{t("accounts.noAccounts")}</p></div>
          ) : (
            <div className="account-summary-list">
              {visibleAccounts.map((account) => (
                <div key={account.id} className="account-summary-item">
                  <div className="account-summary-top">
                    <div>
                      <strong>{formatAccountName(account.name, t)}</strong>
                      <p>{formatAccountType(account.type, t)}</p>
                    </div>

                    <div className="transaction-actions-inline">
                      <button
                        className="secondary-button"
                        onClick={() => handleReviewAccount(account.id)}
                      >
                        {t("accounts.review")}
                      </button>
                      <button
                        className="delete-button"
                        onClick={() => handleDelete(account.id)}
                      >
                        {t("accounts.delete")}
                      </button>
                    </div>
                  </div>

                  <div className="account-summary-metrics">
                    <div>
                      <span>{t("common.income")}</span>
                      <strong>${Number(account.total_income || 0).toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>{t("common.expenses")}</span>
                      <strong>${Number(account.total_expenses || 0).toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>{t("common.balance")}</span>
                      <strong>${Number(account.balance || 0).toFixed(2)}</strong>
                    </div>
                  </div>

                  <p className="account-summary-footnote">
                    {account.top_category
                      ? t("accounts.topCategory", {
                          category: formatCategoryLabel(account.top_category, t),
                          amount: Number(account.top_category_amount || 0).toFixed(2),
                        })
                      : t("accounts.noExpenseCategory")}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AccountsPage;
