import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";

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
            <div className="transaction-list">
              {accounts.map((account) => (
                <div key={account.id} className="transaction-item">
                  <div>
                    <strong>{account.name}</strong>
                    <p>{account.type}</p>
                  </div>
                  <div className="transaction-actions-inline">
                    <button
                      className="delete-button"
                      onClick={() => handleDelete(account.id)}
                    >
                      Delete
                    </button>
                  </div>
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