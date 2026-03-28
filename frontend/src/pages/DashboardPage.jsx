import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import TransactionForm from "../components/TransactionForm";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [recentTransactions, setRecentTransactions] = useState([]);
  const [topCategory, setTopCategory] = useState(null);
  const [categoryBreakdown, setCategoryBreakdown] = useState([]);
  const [monthlySummary, setMonthlySummary] = useState([]);
  const [editingTransaction, setEditingTransaction] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const pieColors = ["#2563eb", "#16a34a", "#dc2626", "#f59e0b", "#7c3aed", "#0891b2"];

  const fetchDashboardData = useCallback(async () => {
    try {
      const queryParams = {
        params: {
          month: selectedMonth || undefined,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        },
      };

      const [
        summaryRes,
        recentRes,
        topCategoryRes,
        categoryBreakdownRes,
        monthlySummaryRes,
      ] = await Promise.all([
        api.get("/analytics/summary", queryParams),
        api.get("/analytics/recent-transactions", queryParams),
        api.get("/analytics/top-expense-category", queryParams),
        api.get("/analytics/category-breakdown", queryParams),
        api.get("/analytics/monthly-summary"),
      ]);

      setSummary(summaryRes.data);
      setRecentTransactions(recentRes.data);
      setTopCategory(topCategoryRes.data);
      setCategoryBreakdown(categoryBreakdownRes.data);
      setMonthlySummary(monthlySummaryRes.data);
    } catch (error) {
      console.error("Failed to load dashboard data:", error);
      localStorage.removeItem("token");
      navigate("/");
    } finally {
      setLoading(false);
    }
  }, [navigate, selectedMonth, startDate, endDate]);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/");
  };

  if (loading) {
    return (
      <div className="page-container">
        <div className="dashboard-wrapper">
          <p>Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-header">
          <div>
            <h1>Financial Dashboard</h1>
            <p>Your money overview</p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/transactions")}>
              View All Transactions
            </button>
            <button className="logout-button" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </div>

        <div className="filter-bar">
          <div>
            <label>Month:</label>
            <select
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
            >
              <option value="">All</option>
              {monthlySummary.map((item) => (
                <option key={item.month} value={item.month}>
                  {item.month}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label>From:</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div>
            <label>To:</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
        </div>

        <div className="summary-grid">
          <div className="summary-card">
            <h3>Total Income</h3>
            <p>${summary?.total_income?.toFixed(2)}</p>
          </div>

          <div className="summary-card">
            <h3>Total Expenses</h3>
            <p>${summary?.total_expenses?.toFixed(2)}</p>
          </div>

          <div className="summary-card">
            <h3>Balance</h3>
            <p>${summary?.balance?.toFixed(2)}</p>
          </div>

          <div className="summary-card">
            <h3>Top Expense Category</h3>
            <p>
              {topCategory
                ? `${topCategory.category} ($${topCategory.total.toFixed(2)})`
                : "No expense data"}
            </p>
          </div>
        </div>

        <div className="chart-grid">
          <div className="dashboard-card">
            <h2>Monthly Summary</h2>
            {monthlySummary.length === 0 ? (
              <p>No monthly data found.</p>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={monthlySummary}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="income" fill="#16a34a" />
                  <Bar dataKey="expenses" fill="#dc2626" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="dashboard-card">
            <h2>Expense Category Chart</h2>
            {categoryBreakdown.length === 0 ? (
              <p>No expense categories found.</p>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={categoryBreakdown}
                    dataKey="total"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label
                  >
                    {categoryBreakdown.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={pieColors[index % pieColors.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="dashboard-sections">
          <div className="dashboard-card large-card">
            <h2>Recent Transactions</h2>
            {recentTransactions.length === 0 ? (
              <p>No transactions found.</p>
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

          <div className="dashboard-card">
            <h2>Expense Categories</h2>
            {categoryBreakdown.length === 0 ? (
              <p>No expense categories found.</p>
            ) : (
              <div className="category-list">
                {categoryBreakdown.map((item) => (
                  <div key={item.category} className="category-item">
                    <span>{item.category}</span>
                    <strong>${item.total.toFixed(2)}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
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