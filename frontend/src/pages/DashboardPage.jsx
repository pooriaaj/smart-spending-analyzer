import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";

function DashboardPage() {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);

  const navigate = useNavigate();

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const response = await api.get("/analytics/dashboard");
        setDashboardData(response.data);
      } catch (error) {
        console.error("Failed to load dashboard:", error);

        if (error.response?.status === 401) {
          localStorage.removeItem("token");
          navigate("/", { replace: true });
        }
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/", { replace: true });
  };

  if (loading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>Loading dashboard...</h2>
            <p>Please wait while your financial overview is being prepared.</p>
          </div>
        </div>
      </div>
    );
  }

  const summary = dashboardData?.summary || {
    total_income: 0,
    total_expenses: 0,
    balance: 0,
  };

  const recentTransactions = dashboardData?.recent_transactions || [];
  const topCategory = dashboardData?.top_category;
  const insights = dashboardData?.spending_insights;

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">Smart Spending Analyzer</p>
            <h1>Dashboard</h1>
            <p className="hero-subtitle">
              Your financial overview, recent activity, and key insights in one place.
            </p>
          </div>

          <div className="header-actions">
            <button
              className="secondary-button"
              onClick={() => navigate("/transactions")}
            >
              View Transactions
            </button>

            <button
              className="secondary-button"
              onClick={() => navigate("/assistant")}
            >
              Assistant
            </button>

            <button className="logout-button" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </div>

        <div className="summary-grid">
          <div className="summary-card income-card">
            <span className="card-label">Income</span>
            <p>${summary.total_income.toFixed(2)}</p>
          </div>

          <div className="summary-card expense-card">
            <span className="card-label">Expenses</span>
            <p>${summary.total_expenses.toFixed(2)}</p>
          </div>

          <div className="summary-card balance-card">
            <span className="card-label">Balance</span>
            <p>${summary.balance.toFixed(2)}</p>
          </div>

          <div className="summary-card analytics-summary-card compact-summary-card">
            <span className="card-label">Analytics</span>
            <p>{topCategory ? topCategory.category : "Insights"}</p>
            <button
              className="analytics-card-button"
              onClick={() => navigate("/analytics")}
            >
              Open Analytics
            </button>
          </div>
        </div>

        <div className="chart-grid">
          <div className="dashboard-card large-card">
            <div className="section-header">
              <h2>Recent Transactions</h2>
              <p>Your latest recorded income and expense activity.</p>
            </div>

            {recentTransactions.length === 0 ? (
              <div className="empty-state">
                <p>No recent transactions found.</p>
              </div>
            ) : (
              <div className="transaction-list">
                {recentTransactions.map((transaction) => (
                  <div key={transaction.id} className="transaction-item">
                    <div>
                      <strong>{transaction.description}</strong>
                      <p>
                        {transaction.category} • {transaction.type} • {transaction.date}
                      </p>
                    </div>

                    <div className="transaction-right">
                      <strong
                        className={
                          transaction.type === "income"
                            ? "income-text"
                            : "expense-text"
                        }
                      >
                        {transaction.type === "income" ? "+" : "-"}$
                        {transaction.amount.toFixed(2)}
                      </strong>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="dashboard-card large-card">
            <div className="section-header">
              <h2>Quick Insight</h2>
              <p>A high-level summary generated from your current financial data.</p>
            </div>

            {!insights ? (
              <div className="empty-state">
                <p>No insights available yet.</p>
              </div>
            ) : (
              <div className="insights-grid">
                <div className="insights-block">
                  <h3>Observations</h3>
                  <ul className="insights-list">
                    {insights.insights.map((item, index) => (
                      <li key={`dashboard-insight-${index}`}>{item}</li>
                    ))}
                  </ul>
                </div>

                <div className="insights-block">
                  <h3>Recommendations</h3>
                  <ul className="insights-list">
                    {insights.recommendations.map((item, index) => (
                      <li key={`dashboard-recommendation-${index}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;