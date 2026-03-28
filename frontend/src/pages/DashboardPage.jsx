import { useEffect, useState, useCallback, useMemo } from "react";
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
  const [allTransactions, setAllTransactions] = useState([]);
  const [editingTransaction, setEditingTransaction] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedType, setSelectedType] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const pieColors = ["#2563eb", "#16a34a", "#dc2626", "#f59e0b", "#7c3aed", "#0891b2"];

  const availableCategories = useMemo(() => {
    const categories = new Set(
      allTransactions.map((transaction) => transaction.category)
    );
    return Array.from(categories).sort();
  }, [allTransactions]);

  const fetchDashboardData = useCallback(async () => {
    try {
      const queryParams = {
        params: {
          month: selectedMonth || undefined,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          transaction_type: selectedType || undefined,
          category: selectedCategory || undefined,
        },
      };

      const [
        summaryRes,
        recentRes,
        topCategoryRes,
        categoryBreakdownRes,
        monthlySummaryRes,
        allTransactionsRes,
      ] = await Promise.all([
        api.get("/analytics/summary", queryParams),
        api.get("/analytics/recent-transactions", queryParams),
        api.get("/analytics/top-expense-category", queryParams),
        api.get("/analytics/category-breakdown", queryParams),
        api.get("/analytics/monthly-summary", {
          params: {
            start_date: startDate || undefined,
            end_date: endDate || undefined,
            transaction_type: selectedType || undefined,
            category: selectedCategory || undefined,
          },
        }),
        api.get("/transactions/"),
      ]);

      setSummary(summaryRes.data);
      setRecentTransactions(recentRes.data);
      setTopCategory(topCategoryRes.data);
      setCategoryBreakdown(categoryBreakdownRes.data);
      setMonthlySummary(monthlySummaryRes.data);
      setAllTransactions(allTransactionsRes.data);
    } catch (error) {
      console.error("Failed to load dashboard data:", error);
      localStorage.removeItem("token");
      navigate("/");
    } finally {
      setLoading(false);
    }
  }, [navigate, selectedMonth, startDate, endDate, selectedType, selectedCategory]);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/");
  };

  const clearFilters = () => {
    setSelectedMonth("");
    setStartDate("");
    setEndDate("");
    setSelectedType("");
    setSelectedCategory("");
  };

  const handleExportCsv = async () => {
    try {
      const token = localStorage.getItem("token");

      const queryParams = new URLSearchParams({
        ...(selectedMonth && { month: selectedMonth }),
        ...(startDate && { start_date: startDate }),
        ...(endDate && { end_date: endDate }),
        ...(selectedType && { transaction_type: selectedType }),
        ...(selectedCategory && { category: selectedCategory }),
      });

      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/transactions/export/csv?${queryParams.toString()}`,
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
              Track income, expenses, trends, and categories in one place.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/transactions")}>
              View All Transactions
            </button>
            <button className="export-button" onClick={handleExportCsv}>
              Export CSV
            </button>
            <button className="logout-button" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Filters</h2>
            <p>Refine the dashboard using month, date range, type, and category.</p>
          </div>

          <div className="filter-bar">
            <div>
              <label>Month</label>
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
              <label>From</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>

            <div>
              <label>To</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>

            <div>
              <label>Type</label>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
              >
                <option value="">All</option>
                <option value="income">Income</option>
                <option value="expense">Expense</option>
              </select>
            </div>

            <div>
              <label>Category</label>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
              >
                <option value="">All</option>
                {availableCategories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </div>

            <div className="filter-actions">
              <button className="clear-filter-button" onClick={clearFilters}>
                Clear Filters
              </button>
            </div>
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
            <span className="card-label">Top Expense Category</span>
            <p>
              {topCategory
                ? `${topCategory.category} ($${topCategory.total.toFixed(2)})`
                : "No expense data"}
            </p>
          </div>
        </div>

        <div className="chart-grid">
          <div className="dashboard-card">
            <div className="section-header">
              <h2>Monthly Summary</h2>
              <p>Compare income and expense amounts by month.</p>
            </div>

            {monthlySummary.length === 0 ? (
              <div className="empty-state">
                <p>No monthly data found.</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={monthlySummary}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="income" fill="#16a34a" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="expenses" fill="#dc2626" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="dashboard-card">
            <div className="section-header">
              <h2>Expense Category Chart</h2>
              <p>See which spending categories take the largest share.</p>
            </div>

            {categoryBreakdown.length === 0 ? (
              <div className="empty-state">
                <p>No expense categories found.</p>
              </div>
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
            <div className="section-header">
              <h2>Recent Transactions</h2>
              <p>Your latest activity based on the selected filters.</p>
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

          <div className="dashboard-card">
            <div className="section-header">
              <h2>Expense Categories</h2>
              <p>Ranked from highest to lowest total expense.</p>
            </div>

            {categoryBreakdown.length === 0 ? (
              <div className="empty-state">
                <p>No expense categories found.</p>
              </div>
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