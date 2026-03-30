import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import TransactionForm from "../components/TransactionForm";

function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [recentTransactions, setRecentTransactions] = useState([]);
  const [editingTransaction, setEditingTransaction] = useState(null);
  const [loading, setLoading] = useState(true);

  const navigate = useNavigate();

  const fetchDashboardData = useCallback(async () => {
    try {
      const [summaryRes, recentRes] = await Promise.all([
        api.get("/analytics/summary"),
        api.get("/analytics/recent-transactions"),
      ]);

      setSummary(summaryRes.data);
      setRecentTransactions(recentRes.data);
    } catch (error) {
      console.error("Failed to load dashboard data:", error);

      if (error.response?.status === 401) {
        localStorage.removeItem("token");
        navigate("/", { replace: true });
      }
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/", { replace: true });
  };

  const handleExportCsv = async () => {
    try {
      const token = localStorage.getItem("token");

      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/transactions/export/csv`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "transactions_export.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Failed to export CSV:", error);
    }
  };

  if (loading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>Loading dashboard...</h2>
            <p>Please wait while your financial data is being prepared.</p>
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
            <p className="eyebrow-text">Smart Spending Analyzer</p>
            <h1>Financial Dashboard</h1>
            <p className="hero-subtitle">
              Get a quick overview of your finances, recent activity, and core actions.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/transactions")}>
              View All Transactions
            </button>
            <button className="secondary-button" onClick={() => navigate("/analytics")}>
              View Analytics
            </button>
            <button className="export-button" onClick={handleExportCsv}>
              Export CSV
            </button>
            <button className="logout-button" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </div>

        <div className="summary-grid">
          <div className="summary-card income-card">
            <span className="card-label">Total Income</span>
            <p>${summary?.total_income?.toFixed(2)}</p>
          </div>

          <div className="summary-card expense-card">
            <span className="card-label">Total Expenses</span>
            <p>${summary?.total_expenses?.toFixed(2)}</p>
          </div>

          <div className="summary-card balance-card">
            <span className="card-label">Balance</span>
            <p>${summary?.balance?.toFixed(2)}</p>
          </div>

          <div className="summary-card top-card">
            <span className="card-label">Analytics</span>
            <p>Open the analytics page for trends, charts, and deeper insights.</p>
          </div>
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>Recent Transactions</h2>
            <p>Your latest activity based on transaction date.</p>
          </div>

          {recentTransactions.length === 0 ? (
            <div className="empty-state">
              <p>No transactions found.</p>
            </div>
          ) : (
            <div className="transaction-list">
              {recentTransactions.map((transaction) => (
                <div key={transaction.id} className="transaction-item">
                  <div>
                    <strong>{transaction.category}</strong>
                    <p>{transaction.description}</p>
                  </div>

                  <div className="transaction-actions">
                    <div className="transaction-right">
                      <span
                        className={
                          transaction.type === "income"
                            ? "income-text"
                            : "expense-text"
                        }
                      >
                        {transaction.type === "income" ? "+" : "-"}$
                        {transaction.amount.toFixed(2)}
                      </span>
                      <small>{transaction.date}</small>
                    </div>

                    <button
                      className="edit-button"
                      onClick={() => setEditingTransaction(transaction)}
                    >
                      Edit
                    </button>

                    <button
                      className="delete-button"
                      onClick={async () => {
                        try {
                          await api.delete(`/transactions/${transaction.id}`);
                          fetchDashboardData();
                          if (editingTransaction?.id === transaction.id) {
                            setEditingTransaction(null);
                          }
                        } catch (error) {
                          console.error("Failed to delete transaction:", error);
                        }
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="form-section">
          <TransactionForm
            onTransactionCreated={fetchDashboardData}
            editingTransaction={editingTransaction}
            onCancelEdit={() => setEditingTransaction(null)}
          />
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;