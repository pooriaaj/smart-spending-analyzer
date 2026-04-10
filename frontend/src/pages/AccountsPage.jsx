import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import { setSelectedAccountId } from "../services/accountStorage";

function AccountsPage() {
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState([]);
  const [name, setName] = useState("");
  const [type, setType] = useState("chequing");
  const [error, setError] = useState("");

  const fetchAccounts = async () => {
    try {
      const response = await api.get("/accounts/");
      setAccounts(response.data || []);
    } catch (error) {
      handleApiAuthError(error, navigate);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

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
        setError(error?.response?.data?.detail || "Failed to create account.");
      }
    }
  };

  const handleDelete = async (accountId) => {
    try {
      await api.delete(`/accounts/${accountId}`);
      await fetchAccounts();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setError(error?.response?.data?.detail || "Failed to delete account.");
      }
    }
  };

  const handleReviewAccount = (accountId) => {
    setSelectedAccountId(String(accountId));
    navigate("/dashboard");
  };

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">Smart Spending Analyzer</p>
            <h1>Accounts</h1>
            <p className="hero-subtitle">
              Create separate accounts and switch between combined and account-specific views.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              Back to Dashboard
            </button>
          </div>
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>Create Account</h2>
            <p>Add a new financial account for tracking.</p>
          </div>

          <form className="transaction-form" onSubmit={handleCreate}>
            <input
              type="text"
              placeholder="Account name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />

            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="chequing">Chequing</option>
              <option value="savings">Savings</option>
              <option value="credit_card">Credit Card</option>
              <option value="cash">Cash</option>
              <option value="business">Business</option>
              <option value="other">Other</option>
            </select>

            <button type="submit">Create Account</button>
          </form>

          {error && <p className="error-text">{error}</p>}
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <h2>Your Accounts</h2>
          </div>

          {accounts.length === 0 ? (
            <div className="empty-state"><p>No accounts found.</p></div>
          ) : (
            <div className="account-summary-list">
              {accounts.map((account) => (
                <div key={account.id} className="account-summary-item">
                  <div className="account-summary-top">
                    <div>
                      <strong>{account.name}</strong>
                      <p>{account.type}</p>
                    </div>

                    <div className="transaction-actions-inline">
                      <button
                        className="secondary-button"
                        onClick={() => handleReviewAccount(account.id)}
                      >
                        Review
                      </button>
                      <button
                        className="delete-button"
                        onClick={() => handleDelete(account.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>

                  <div className="account-summary-metrics">
                    <div>
                      <span>Income</span>
                      <strong>${Number(account.total_income || 0).toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>Expenses</span>
                      <strong>${Number(account.total_expenses || 0).toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>Balance</span>
                      <strong>${Number(account.balance || 0).toFixed(2)}</strong>
                    </div>
                  </div>

                  <p className="account-summary-footnote">
                    {account.top_category
                      ? `Top category: ${account.top_category} ($${Number(account.top_category_amount || 0).toFixed(2)})`
                      : "No expense category recorded yet."}
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
