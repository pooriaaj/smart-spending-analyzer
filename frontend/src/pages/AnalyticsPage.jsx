import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
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

function AnalyticsPage() {
  const [summary, setSummary] = useState(null);
  const [topCategory, setTopCategory] = useState(null);
  const [categoryBreakdown, setCategoryBreakdown] = useState([]);
  const [monthlySummary, setMonthlySummary] = useState([]);
  const [allTransactions, setAllTransactions] = useState([]);
  const [spendingInsights, setSpendingInsights] = useState(null);
  const [overspendingAlerts, setOverspendingAlerts] = useState(null);
  const [categoryTrends, setCategoryTrends] = useState(null);
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

  const fetchAnalyticsData = useCallback(async () => {
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
        topCategoryRes,
        categoryBreakdownRes,
        monthlySummaryRes,
        allTransactionsRes,
        insightsRes,
        alertsRes,
        trendsRes,
      ] = await Promise.all([
        api.get("/analytics/summary", queryParams),
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
        api.get("/analytics/spending-insights"),
        api.get("/analytics/overspending-alerts"),
        api.get("/analytics/category-trends"),
      ]);

      setSummary(summaryRes.data);
      setTopCategory(topCategoryRes.data);
      setCategoryBreakdown(categoryBreakdownRes.data);
      setMonthlySummary(monthlySummaryRes.data);
      setAllTransactions(allTransactionsRes.data);
      setSpendingInsights(insightsRes.data);
      setOverspendingAlerts(alertsRes.data);
      setCategoryTrends(trendsRes.data);
    } catch (error) {
      console.error("Failed to load analytics data:", error);

      if (error.response?.status === 401) {
        localStorage.removeItem("token");
        navigate("/", { replace: true });
      }
    } finally {
      setLoading(false);
    }
  }, [navigate, selectedMonth, startDate, endDate, selectedType, selectedCategory]);

  useEffect(() => {
    fetchAnalyticsData();
  }, [fetchAnalyticsData]);

  const clearFilters = () => {
    setSelectedMonth("");
    setStartDate("");
    setEndDate("");
    setSelectedType("");
    setSelectedCategory("");
  };

  const renderTrendAmount = (value) => {
    const prefix = value > 0 ? "+" : "";
    return `${prefix}$${value.toFixed(2)}`;
  };

  if (loading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>Loading analytics...</h2>
            <p>Please wait while your analysis page is being prepared.</p>
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
            <h1>Analytics & Insights</h1>
            <p className="hero-subtitle">
              Explore charts, category patterns, and intelligent spending insights.
            </p>
          </div>

          <div className="header-actions">
            <button
              className="secondary-button"
              onClick={() => navigate("/dashboard")}
            >
              Back to Dashboard
            </button>

            <button
              className="secondary-button"
              onClick={() => navigate("/transactions")}
            >
              View All Transactions
            </button>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Analytics Filters</h2>
            <p>Refine the analysis using month, date range, type, and category.</p>
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

        <div className="dashboard-card alerts-card">
          <div className="section-header">
            <h2>Overspending Alerts</h2>
            <p>Warnings based on unusual monthly or category-level spending increases.</p>
          </div>

          {!overspendingAlerts || overspendingAlerts.alerts.length === 0 ? (
            <div className="empty-state">
              <p>No alerts available.</p>
            </div>
          ) : (
            <div className="alerts-list">
              {overspendingAlerts.alerts.map((alert, index) => (
                <div
                  key={`alert-${index}`}
                  className={`alert-box alert-${alert.level}`}
                >
                  <h3>{alert.title}</h3>
                  <p>{alert.message}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="dashboard-card trends-card">
          <div className="section-header">
            <h2>Category Trend Comparison</h2>
            <p>See which categories increased or decreased the most month over month.</p>
          </div>

          {!categoryTrends ? (
            <div className="empty-state">
              <p>No trend data available.</p>
            </div>
          ) : (
            <>
              <div className="trend-summary-box">
                {categoryTrends.summary.map((item, index) => (
                  <p key={`trend-summary-${index}`}>{item}</p>
                ))}
              </div>

              <div className="trend-grid">
                <div className="trend-block">
                  <h3>Top Increases</h3>
                  {categoryTrends.top_increases.length === 0 ? (
                    <p className="trend-empty-text">No increases detected.</p>
                  ) : (
                    <div className="trend-list">
                      {categoryTrends.top_increases.map((item) => (
                        <div key={`increase-${item.category}`} className="trend-item">
                          <div>
                            <strong>{item.category}</strong>
                            <p>
                              {categoryTrends.previous_month}: ${item.previous_amount.toFixed(2)} → {categoryTrends.current_month}: ${item.current_amount.toFixed(2)}
                            </p>
                          </div>
                          <span className="trend-positive">
                            {renderTrendAmount(item.change_amount)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="trend-block">
                  <h3>Top Decreases</h3>
                  {categoryTrends.top_decreases.length === 0 ? (
                    <p className="trend-empty-text">No decreases detected.</p>
                  ) : (
                    <div className="trend-list">
                      {categoryTrends.top_decreases.map((item) => (
                        <div key={`decrease-${item.category}`} className="trend-item">
                          <div>
                            <strong>{item.category}</strong>
                            <p>
                              {categoryTrends.previous_month}: ${item.previous_amount.toFixed(2)} → {categoryTrends.current_month}: ${item.current_amount.toFixed(2)}
                            </p>
                          </div>
                          <span className="trend-negative">
                            {renderTrendAmount(item.change_amount)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="dashboard-card insights-card">
          <div className="section-header">
            <h2>Spending Insights</h2>
            <p>Simple observations and recommendations based on your spending data.</p>
          </div>

          {!spendingInsights ? (
            <div className="empty-state">
              <p>No insights available yet.</p>
            </div>
          ) : (
            <div className="insights-grid">
              <div className="insights-block">
                <h3>Observations</h3>
                <ul className="insights-list">
                  {spendingInsights.insights.map((item, index) => (
                    <li key={`insight-${index}`}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="insights-block">
                <h3>Recommendations</h3>
                <ul className="insights-list">
                  {spendingInsights.recommendations.map((item, index) => (
                    <li key={`recommendation-${index}`}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
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
    </div>
  );
}

export default AnalyticsPage;