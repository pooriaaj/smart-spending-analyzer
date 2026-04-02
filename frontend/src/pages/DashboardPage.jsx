import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";

const CATEGORY_RULES = {
  groceries: ["walmart", "costco", "freshco", "nofrills", "grocery", "supermarket"],
  transport: ["uber", "lyft", "ttc", "metro", "gas", "shell", "esso"],
  cafe: ["coffee", "cafe", "starbucks", "tim hortons"],
  restaurant: ["pizza", "burger", "restaurant", "mcdonald", "shawarma", "subway", "kfc"],
  rent: ["rent", "lease", "landlord"],
  salary: ["salary", "payroll", "paycheck", "paycheque"],
  internet: ["internet", "wifi", "rogers", "bell"],
  phone: ["phone", "mobile", "cell", "freedom", "telus"],
  entertainment: ["netflix", "spotify", "youtube", "cinema", "movie"],
};

function DashboardPage() {
  const [dashboardData, setDashboardData] = useState(null);
  const [allTransactions, setAllTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  const [typeFilter, setTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");

  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("Other");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [transactionType, setTransactionType] = useState("expense");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [suggestion, setSuggestion] = useState(null);

  const navigate = useNavigate();

  const fetchData = async () => {
    try {
      const [dashboardRes, transactionsRes] = await Promise.all([
        api.get("/analytics/dashboard"),
        api.get("/transactions/"),
      ]);

      setDashboardData(dashboardRes.data);
      setAllTransactions(transactionsRes.data);
    } catch (error) {
      console.error("Failed to load dashboard:", error);
      handleApiAuthError(error, navigate);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const filteredRecentTransactions = useMemo(() => {
    const transactions = [...allTransactions]
      .sort((a, b) => new Date(b.date) - new Date(a.date))
      .filter((transaction) => {
        const transactionMonth = transaction.date.slice(0, 7);

        if (typeFilter && transaction.type !== typeFilter) return false;
        if (monthFilter && transactionMonth !== monthFilter) return false;

        return true;
      });

    return transactions.slice(0, 5);
  }, [allTransactions, typeFilter, monthFilter]);

  const availableMonths = useMemo(() => {
    return Array.from(new Set(allTransactions.map((item) => item.date.slice(0, 7))))
      .sort()
      .reverse();
  }, [allTransactions]);

  const categoryBreakdown = dashboardData?.category_breakdown || [];
  const topCategories = categoryBreakdown.slice(0, 5);

  const summary = dashboardData?.summary || {
    total_income: 0,
    total_expenses: 0,
    balance: 0,
  };

  const suggestCategory = () => {
    const text = description.trim().toLowerCase();

    if (!text) {
      setSuggestion({
        category: "Other",
        confidence: 35,
        reason: "No description entered, used fallback category.",
      });
      return;
    }

    if (transactionType === "income") {
      const salaryMatch = CATEGORY_RULES.salary.find((keyword) =>
        text.includes(keyword)
      );

      if (salaryMatch) {
        const suggested = {
          category: "Salary",
          confidence: 95,
          reason: `Matched keyword '${salaryMatch}' in description.`,
        };
        setSuggestion(suggested);
        setCategory(suggested.category);
        return;
      }

      const suggested = {
        category: "Income",
        confidence: 70,
        reason: "No salary keyword matched, used generic income category.",
      };
      setSuggestion(suggested);
      setCategory(suggested.category);
      return;
    }

    for (const [ruleCategory, keywords] of Object.entries(CATEGORY_RULES)) {
      const matchedKeyword = keywords.find((keyword) => text.includes(keyword));
      if (matchedKeyword) {
        const suggested = {
          category: ruleCategory.charAt(0).toUpperCase() + ruleCategory.slice(1),
          confidence: 92,
          reason: `Matched keyword '${matchedKeyword}' in description.`,
        };
        setSuggestion(suggested);
        setCategory(suggested.category);
        return;
      }
    }

    const suggested = {
      category: "Other",
      confidence: 35,
      reason: "No rule matched, used fallback category.",
    };
    setSuggestion(suggested);
    setCategory(suggested.category);
  };

  const handleAddTransaction = async (e) => {
    e.preventDefault();
    setFormError("");

    if (!amount || !description || !date || !transactionType || !category) {
      setFormError("Please fill all transaction fields.");
      return;
    }

    try {
      setSubmitting(true);

      await api.post("/transactions/", {
        amount: Number(amount),
        category,
        description,
        date,
        type: transactionType,
      });

      setAmount("");
      setCategory("Other");
      setDescription("");
      setDate(new Date().toISOString().slice(0, 10));
      setTransactionType("expense");
      setSuggestion(null);

      await fetchData();
    } catch (error) {
      console.error("Failed to add transaction:", error);

      if (!handleApiAuthError(error, navigate)) {
        setFormError("Failed to add transaction.");
      }
    } finally {
      setSubmitting(false);
    }
  };

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
            <div className="summary-card-content">
              <p>${summary.total_income.toFixed(2)}</p>
              <small className="summary-card-note">Total recorded income</small>
            </div>
          </div>

          <div className="summary-card expense-card">
            <span className="card-label">Expenses</span>
            <div className="summary-card-content">
              <p>${summary.total_expenses.toFixed(2)}</p>
              <small className="summary-card-note">Total recorded expenses</small>
            </div>
          </div>

          <div className="summary-card balance-card">
            <span className="card-label">Balance</span>
            <div className="summary-card-content">
              <p>${summary.balance.toFixed(2)}</p>
              <small className="summary-card-note">Income minus expenses</small>
            </div>
          </div>

          <div className="summary-card analytics-summary-card compact-summary-card">
            <span className="card-label">Analytics</span>
            <div className="summary-card-content analytics-card-content">
              <small className="summary-card-note">Open trends, charts, and insights</small>
              <button
                className="analytics-card-button"
                onClick={() => navigate("/analytics")}
              >
                Open Analytics
              </button>
            </div>
          </div>
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>Add Transaction</h2>
            <p>Add a new income or expense entry and use suggestion help if needed.</p>
          </div>

          <form className="transaction-form" onSubmit={handleAddTransaction}>
            <input
              type="number"
              step="0.01"
              placeholder="Amount"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />

            <input
              type="text"
              placeholder="Category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />

            <input
              type="text"
              placeholder="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />

            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />

            <select
              value={transactionType}
              onChange={(e) => setTransactionType(e.target.value)}
            >
              <option value="expense">Expense</option>
              <option value="income">Income</option>
            </select>

            <button
              type="button"
              className="suggest-button"
              onClick={suggestCategory}
            >
              Suggest Category
            </button>

            <button type="submit" disabled={submitting}>
              {submitting ? "Adding..." : "Add Transaction"}
            </button>
          </form>

          {formError && <p className="error-text">{formError}</p>}

          {suggestion && (
            <div className="suggestion-box">
              <h3>Suggested Category</h3>
              <p>
                <strong>{suggestion.category}</strong>
              </p>
              <p>Confidence: {suggestion.confidence}%</p>
              <p>{suggestion.reason}</p>
            </div>
          )}
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Recent Transaction Filters</h2>
            <p>Filter the recent activity list by type and month.</p>
          </div>

          <div className="filter-bar">
            <div>
              <label>Type</label>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
              >
                <option value="">All</option>
                <option value="income">Income</option>
                <option value="expense">Expense</option>
              </select>
            </div>

            <div>
              <label>Month</label>
              <select
                value={monthFilter}
                onChange={(e) => setMonthFilter(e.target.value)}
              >
                <option value="">All</option>
                {availableMonths.map((month) => (
                  <option key={month} value={month}>
                    {month}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="chart-grid">
          <div className="dashboard-card large-card">
            <div className="section-header">
              <h2>Recent Transactions</h2>
              <p>Your latest recorded income and expense activity.</p>
            </div>

            {filteredRecentTransactions.length === 0 ? (
              <div className="empty-state">
                <p>No recent transactions found.</p>
              </div>
            ) : (
              <div className="transaction-list">
                {filteredRecentTransactions.map((transaction) => (
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
              <h2>Expense Categories</h2>
              <p>Ranked from highest to lowest total expense.</p>
            </div>

            {topCategories.length === 0 ? (
              <div className="empty-state">
                <p>No expense categories found.</p>
              </div>
            ) : (
              <div className="category-list">
                {topCategories.map((item) => (
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
    </div>
  );
}

export default DashboardPage;