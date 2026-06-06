import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import { setSelectedAccountId } from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import { getAccountsFromResponse } from "../utils/accountResponses";
import { formatAccountName, formatAccountType, formatCategoryLabel } from "../utils/displayLabels";
import { getApiErrorMessage } from "../utils/errorUtils";

const ACCOUNT_TYPE_OPTIONS = [
  "chequing",
  "savings",
  "credit_card",
  "cash",
  "business",
  "other",
];

function makeAccountDraft(account) {
  return {
    name: account?.name || "",
    type: account?.type || "other",
  };
}

function AccountsPage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [accounts, setAccounts] = useState([]);
  const [name, setName] = useState("");
  const [type, setType] = useState("chequing");
  const [editingAccounts, setEditingAccounts] = useState({});
  const [savingAccountId, setSavingAccountId] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const fetchAccounts = async () => {
    try {
      const response = await api.get("/accounts/");
      setAccounts(getAccountsFromResponse(response.data));
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setError(getApiErrorMessage(error, t("accounts.loadFailed")));
      }
    }
  };

  useEffect(() => {
    const loadAccounts = async () => {
      try {
        const response = await api.get("/accounts/");
        setAccounts(getAccountsFromResponse(response.data));
      } catch (error) {
        if (!handleApiAuthError(error, navigate)) {
          setError(getApiErrorMessage(error, t("accounts.loadFailed")));
        }
      }
    };

    loadAccounts();
  }, [navigate, t]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setError("");
    setStatus("");

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError(t("accounts.nameRequired"));
      return;
    }

    try {
      await api.post("/accounts/", { name: trimmedName, type });
      setName("");
      setType("chequing");
      await fetchAccounts();
      setStatus(t("accounts.createSuccess"));
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setError(getApiErrorMessage(error, t("accounts.createFailed")));
      }
    }
  };

  const handleDelete = async (accountId) => {
    setError("");
    setStatus("");

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

  const handleEditAccount = (account) => {
    setError("");
    setStatus("");
    setEditingAccounts((current) => ({
      ...current,
      [account.id]: makeAccountDraft(account),
    }));
  };

  const handleCancelEdit = (accountId) => {
    setEditingAccounts((current) => {
      const next = { ...current };
      delete next[accountId];
      return next;
    });
  };

  const handleEditChange = (accountId, field, value) => {
    setEditingAccounts((current) => ({
      ...current,
      [accountId]: {
        ...(current[accountId] || {}),
        [field]: value,
      },
    }));
  };

  const handleUpdateAccount = async (account) => {
    const draft = editingAccounts[account.id] || makeAccountDraft(account);
    const trimmedName = draft.name.trim();

    setError("");
    setStatus("");

    if (!trimmedName) {
      setError(t("accounts.nameRequired"));
      return;
    }

    try {
      setSavingAccountId(account.id);
      await api.put(`/accounts/${account.id}`, {
        name: trimmedName,
        type: draft.type || "other",
      });
      handleCancelEdit(account.id);
      await fetchAccounts();
      setStatus(t("accounts.updateSuccess"));
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setError(getApiErrorMessage(error, t("accounts.updateFailed")));
      }
    } finally {
      setSavingAccountId(null);
    }
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
              {ACCOUNT_TYPE_OPTIONS.map((accountType) => (
                <option key={accountType} value={accountType}>
                  {formatAccountType(accountType, t)}
                </option>
              ))}
            </select>

            <button type="submit">{t("accounts.createAccount")}</button>
          </form>

          {error && <p className="error-text">{error}</p>}
          {status && <p className="success-text">{status}</p>}
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
                    {editingAccounts[account.id] ? (
                      <div className="account-edit-form">
                        <label>
                          <span>{t("accounts.accountName")}</span>
                          <input
                            type="text"
                            value={editingAccounts[account.id].name}
                            onChange={(e) =>
                              handleEditChange(account.id, "name", e.target.value)
                            }
                            required
                          />
                        </label>
                        <label>
                          <span>{t("accounts.accountType")}</span>
                          <select
                            value={editingAccounts[account.id].type}
                            onChange={(e) =>
                              handleEditChange(account.id, "type", e.target.value)
                            }
                          >
                            {ACCOUNT_TYPE_OPTIONS.map((accountType) => (
                              <option key={accountType} value={accountType}>
                                {formatAccountType(accountType, t)}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    ) : (
                      <div>
                        <strong>{formatAccountName(account.name, t)}</strong>
                        <p>{formatAccountType(account.type, t)}</p>
                      </div>
                    )}

                    <div className="transaction-actions-inline">
                      {editingAccounts[account.id] ? (
                        <>
                          <button
                            className="secondary-button"
                            onClick={() => handleUpdateAccount(account)}
                            disabled={savingAccountId === account.id}
                          >
                            {savingAccountId === account.id
                              ? t("common.saving")
                              : t("accounts.saveAccount")}
                          </button>
                          <button
                            className="secondary-button"
                            onClick={() => handleCancelEdit(account.id)}
                            disabled={savingAccountId === account.id}
                          >
                            {t("common.cancel")}
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className="secondary-button"
                            onClick={() => handleReviewAccount(account.id)}
                          >
                            {t("accounts.review")}
                          </button>
                          <button
                            className="edit-button"
                            onClick={() => handleEditAccount(account)}
                          >
                            {t("accounts.editAccount")}
                          </button>
                          <button
                            className="delete-button"
                            onClick={() => handleDelete(account.id)}
                          >
                            {t("accounts.delete")}
                          </button>
                        </>
                      )}
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
