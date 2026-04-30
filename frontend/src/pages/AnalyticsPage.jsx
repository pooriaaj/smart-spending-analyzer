import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "../services/api";
import AccountSelector from "../components/AccountSelector";
import PageHeader from "../components/PageHeader";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId } from "../services/accountStorage";
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
  Legend,
  LineChart,
  Line,
} from "recharts";

const CATEGORY_ALIASES = {
  grocery: "Groceries",
  groceries: "Groceries",
  transport: "Transport",
  transportation: "Transport",
  cafe: "Café",
  café: "Café",
  personal: "Personal",
  shopping: "Shopping",
  transfer: "Transfer",
  utilities: "Utilities",
  utility: "Utilities",
  other: "Other",
  misc: "Other",
  miscellaneous: "Other",
  uncategorized: "Other",
  unknown: "Other",
  restaurant: "Restaurant",
  restaurants: "Restaurant",
  salary: "Salary",
  income: "Income",
  rent: "Rent",
  internet: "Internet",
  phone: "Phone",
  entertainment: "Entertainment",
  "car maintenance": "Car Maintenance",
};

function formatCategoryName(category) {
  if (!category || typeof category !== "string") return "Other";

  const normalized = category.trim().toLowerCase();
  if (!normalized) return "Other";

  if (CATEGORY_ALIASES[normalized]) {
    return CATEGORY_ALIASES[normalized];
  }

  return normalized
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function mergeCategoryBreakdown(items) {
  const mergedMap = new Map();

  (items || []).forEach((item) => {
    const displayCategory = formatCategoryName(item.category);
    const currentTotal = mergedMap.get(displayCategory) || 0;
    mergedMap.set(displayCategory, currentTotal + Number(item.total || 0));
  });

  return Array.from(mergedMap.entries())
    .map(([category, total]) => ({
      category,
      total: Number(total.toFixed(2)),
    }))
    .sort((a, b) => b.total - a.total);
}

function buildTopPieData(items, topN = 5) {
  const merged = mergeCategoryBreakdown(items);

  if (merged.length <= topN) {
    return merged;
  }

  const topItems = merged.slice(0, topN);
  const remainingTotal = merged
    .slice(topN)
    .reduce((sum, item) => sum + item.total, 0);

  if (remainingTotal > 0) {
    topItems.push({
      category: "Other",
      total: Number(remainingTotal.toFixed(2)),
    });
  }

  return topItems;
}

const toLocalDate = (dateValue) => {
  const parsed = new Date(`${dateValue}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const getMonthKey = (dateValue) => {
  const month = dateValue.getMonth() + 1;
  return `${dateValue.getFullYear()}-${String(month).padStart(2, "0")}`;
};

const formatShortMonth = (monthKey) => {
  const parsed = new Date(`${monthKey}-01T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return monthKey;
  return parsed.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
};

const formatMoney = (value) => `$${Number(value || 0).toFixed(2)}`;

const calculateChangePercent = (currentValue, baselineValue) => {
  if (!baselineValue || baselineValue <= 0) return null;
  return ((currentValue - baselineValue) / baselineValue) * 100;
};

const formatPercentChange = (value) => {
  if (value == null || Number.isNaN(value)) return "Not enough data";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
};

const buildRecentMonthKeys = (monthCount) => {
  const today = new Date();
  const monthKeys = [];

  for (let index = monthCount - 1; index >= 0; index -= 1) {
    const monthDate = new Date(today.getFullYear(), today.getMonth() - index, 1);
    monthKeys.push(getMonthKey(monthDate));
  }

  return monthKeys;
};

const getExpenseTransactions = (transactions) =>
  (transactions || [])
    .map((transaction) => ({
      ...transaction,
      amount: Number(transaction.amount || 0),
      parsedDate: toLocalDate(transaction.date),
    }))
    .filter(
      (transaction) =>
        transaction.type === "expense" &&
        transaction.amount > 0 &&
        transaction.parsedDate
    );

const sumExpensesBetween = (transactions, startDate, endDate) =>
  transactions.reduce((total, transaction) => {
    if (transaction.parsedDate >= startDate && transaction.parsedDate <= endDate) {
      return total + transaction.amount;
    }
    return total;
  }, 0);

function buildSpendingPatternPulse(transactions) {
  const expenseTransactions = getExpenseTransactions(transactions);
  const today = new Date();
  today.setHours(23, 59, 59, 999);
  const currentMonthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastSevenStart = new Date(today);
  lastSevenStart.setDate(today.getDate() - 6);
  lastSevenStart.setHours(0, 0, 0, 0);

  const monthKeys = buildRecentMonthKeys(6);
  const expensesByMonth = new Map(monthKeys.map((monthKey) => [monthKey, 0]));

  expenseTransactions.forEach((transaction) => {
    const monthKey = getMonthKey(transaction.parsedDate);
    if (expensesByMonth.has(monthKey)) {
      expensesByMonth.set(monthKey, expensesByMonth.get(monthKey) + transaction.amount);
    }
  });

  const monthlyValues = monthKeys.map((monthKey) => Number((expensesByMonth.get(monthKey) || 0).toFixed(2)));
  const lastThreeValues = monthlyValues.slice(-3);
  const lastSixValues = monthlyValues;
  const lastThreeAverage =
    lastThreeValues.reduce((total, value) => total + value, 0) / Math.max(lastThreeValues.length, 1);
  const lastSixAverage =
    lastSixValues.reduce((total, value) => total + value, 0) / Math.max(lastSixValues.length, 1);

  const lastSevenTotal = sumExpensesBetween(expenseTransactions, lastSevenStart, today);
  const currentMonthTotal = sumExpensesBetween(expenseTransactions, currentMonthStart, today);
  const daysElapsedThisMonth = Math.max(today.getDate(), 1);
  const lastSevenDailyAverage = lastSevenTotal / 7;
  const monthDailyAverage = currentMonthTotal / daysElapsedThisMonth;

  const sevenVsMonthChange = calculateChangePercent(lastSevenDailyAverage, monthDailyAverage);
  const threeVsSixChange = calculateChangePercent(lastThreeAverage, lastSixAverage);
  const currentVsThreeChange = calculateChangePercent(currentMonthTotal, lastThreeAverage);
  const primaryMovement =
    sevenVsMonthChange != null ? sevenVsMonthChange : threeVsSixChange;

  let status = "Building pattern";
  let tone = "neutral";
  if (expenseTransactions.length > 0 && primaryMovement != null) {
    if (primaryMovement > 15) {
      status = "Spending is rising";
      tone = "warning";
    } else if (primaryMovement < -15) {
      status = "Spending is dropping";
      tone = "positive";
    } else {
      status = "Spending is steady";
      tone = "stable";
    }
  }

  const narrative =
    expenseTransactions.length === 0
      ? "Add daily transactions or import a statement to unlock spending movement signals."
      : `Your last 7-day daily average is ${formatMoney(lastSevenDailyAverage)} compared with ${formatMoney(monthDailyAverage)} for this month so far. The 3-month average is ${formatMoney(lastThreeAverage)} versus ${formatMoney(lastSixAverage)} across 6 months.`;

  return {
    hasData: expenseTransactions.length > 0,
    status,
    tone,
    narrative,
    lastSevenTotal,
    lastSevenDailyAverage,
    currentMonthTotal,
    monthDailyAverage,
    lastThreeAverage,
    lastSixAverage,
    sevenVsMonthChange,
    threeVsSixChange,
    currentVsThreeChange,
    chartData: monthKeys.map((monthKey, index) => ({
      month: formatShortMonth(monthKey),
      expenses: monthlyValues[index],
      threeMonthAverage: Number(lastThreeAverage.toFixed(2)),
      sixMonthAverage: Number(lastSixAverage.toFixed(2)),
    })),
  };
}

function AnalyticsPage() {
  const [dashboardData, setDashboardData] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [selectedMonth, setSelectedMonth] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedType, setSelectedType] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [themeMode, setThemeMode] = useState(
    document.documentElement.getAttribute("data-theme") || "light"
  );

  const alertsRef = useRef(null);
  const trendsRef = useRef(null);
  const insightsRef = useRef(null);
  const monthlyRef = useRef(null);
  const categoriesRef = useRef(null);

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setThemeMode(document.documentElement.getAttribute("data-theme") || "light");
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const urlMonth = searchParams.get("month") || "";
    const urlCategory = searchParams.get("category") || "";

    if (urlMonth) setSelectedMonth(urlMonth);
    if (urlCategory) setSelectedCategory(formatCategoryName(urlCategory));
  }, [searchParams]);

  useEffect(() => {
    const fetchDashboardAnalytics = async () => {
      try {
        setLoading(true);

        const [response, transactionsResponse] = await Promise.all([
          api.get("/analytics/dashboard", {
            params: {
              account_id: normalizedAccountId,
              month: selectedMonth || undefined,
              start_date: startDate || undefined,
              end_date: endDate || undefined,
              transaction_type: selectedType || undefined,
              category: selectedCategory || undefined,
            },
          }),
          api.get("/transactions/", {
            params: {
              account_id: normalizedAccountId,
            },
          }),
        ]);

        setDashboardData(response.data);
        setTransactions(transactionsResponse.data || []);
      } catch (error) {
        console.error("Failed to load analytics data:", error);

        if (error.response?.status === 401) {
          localStorage.removeItem("token");
          navigate("/", { replace: true });
        }
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardAnalytics();
  }, [navigate, normalizedAccountId, selectedMonth, startDate, endDate, selectedType, selectedCategory]);

  useEffect(() => {
    const section = searchParams.get("section");
    if (!section || loading) return;

    const sectionMap = {
      alerts: alertsRef,
      trends: trendsRef,
      insights: insightsRef,
      monthly: monthlyRef,
      categories: categoriesRef,
    };

    const targetRef = sectionMap[section];
    if (targetRef?.current) {
      setTimeout(() => {
        targetRef.current.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 150);
    }
  }, [searchParams, loading]);

  const chartTheme = useMemo(() => {
    const isDark = themeMode === "dark";

    return {
      text: isDark ? "#cbd5e1" : "#475569",
      grid: isDark ? "rgba(148, 163, 184, 0.12)" : "rgba(15, 23, 42, 0.08)",
      tooltipBg: isDark ? "rgba(15, 23, 42, 0.96)" : "rgba(255, 255, 255, 0.96)",
      tooltipBorder: isDark ? "rgba(148, 163, 184, 0.16)" : "rgba(15, 23, 42, 0.08)",
      incomeBar: isDark ? "#4ade80" : "#16a34a",
      expenseBar: isDark ? "#f87171" : "#dc2626",
      patternLine: isDark ? "#60a5fa" : "#2563eb",
      threeMonthLine: isDark ? "#fbbf24" : "#d97706",
      sixMonthLine: isDark ? "#a78bfa" : "#7c3aed",
      pieColors: isDark
        ? ["#60a5fa", "#4ade80", "#f87171", "#fbbf24", "#a78bfa", "#22d3ee"]
        : ["#2563eb", "#16a34a", "#dc2626", "#f59e0b", "#7c3aed", "#0891b2"],
    };
  }, [themeMode]);

  const rawCategoryBreakdown = useMemo(
    () => dashboardData?.category_breakdown || [],
    [dashboardData?.category_breakdown]
  );

  const mergedCategoryBreakdown = useMemo(() => {
    return mergeCategoryBreakdown(rawCategoryBreakdown);
  }, [rawCategoryBreakdown]);

  const topPieData = useMemo(() => {
    return buildTopPieData(rawCategoryBreakdown, 5);
  }, [rawCategoryBreakdown]);

  const totalPieAmount = useMemo(() => {
    return topPieData.reduce((sum, item) => sum + item.total, 0);
  }, [topPieData]);

  const availableCategories = useMemo(() => {
    return mergedCategoryBreakdown.map((item) => item.category);
  }, [mergedCategoryBreakdown]);

  const spendingPatternPulse = useMemo(() => {
    return buildSpendingPatternPulse(transactions);
  }, [transactions]);

  const clearFilters = () => {
    setSelectedMonth("");
    setStartDate("");
    setEndDate("");
    setSelectedType("");
    setSelectedCategory("");
  };

  const applyDatePreset = (preset) => {
    const today = new Date();
    const toIso = (value) => value.toISOString().slice(0, 10);

    setSelectedMonth("");
    setSelectedType("");
    setSelectedCategory("");

    if (preset === "month") {
      setStartDate("");
      setEndDate("");
      setSelectedMonth(today.toISOString().slice(0, 7));
      return;
    }

    const start = new Date(today);
    if (preset === "week") {
      start.setDate(today.getDate() - 6);
    }
    if (preset === "3m") {
      start.setMonth(today.getMonth() - 3);
    }
    if (preset === "6m") {
      start.setMonth(today.getMonth() - 6);
    }

    setStartDate(toIso(start));
    setEndDate(toIso(today));
  };

  const renderTrendAmount = (value) => {
    const prefix = value > 0 ? "+" : "";
    return `${prefix}$${value.toFixed(2)}`;
  };

  const getSectionHighlightClass = (sectionName) => {
    return searchParams.get("section") === sectionName
      ? "analytics-section-highlight"
      : "";
  };

  const customTooltipStyle = {
    backgroundColor: chartTheme.tooltipBg,
    border: `1px solid ${chartTheme.tooltipBorder}`,
    borderRadius: "14px",
    color: chartTheme.text,
    boxShadow:
      themeMode === "dark"
        ? "0 18px 40px rgba(0, 0, 0, 0.28)"
        : "0 18px 40px rgba(15, 23, 42, 0.12)",
  };

  const pieTooltipFormatter = (value, name) => {
    const percentage = totalPieAmount > 0 ? ((value / totalPieAmount) * 100).toFixed(1) : "0.0";
    return [`$${Number(value).toFixed(2)} (${percentage}%)`, name];
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

  const summary = dashboardData?.summary || {
    total_income: 0,
    total_expenses: 0,
    balance: 0,
  };
  const topCategory = dashboardData?.top_category;
  const monthlySummary = dashboardData?.monthly_summary || [];
  const spendingInsights = dashboardData?.spending_insights;
  const overspendingAlerts = dashboardData?.overspending_alerts;
  const categoryTrends = dashboardData?.category_trends;
  const accountComparison = dashboardData?.account_comparison || [];

  const normalizedTopCategory = topCategory
    ? {
        ...topCategory,
        category: formatCategoryName(topCategory.category),
      }
    : null;

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <PageHeader
          icon="AN"
          title="Analytics & Insights"
          subtitle="Learn what changed, what is driving your spending, and whether your recent pace is getting better or worse."
          actions={(
            <button className="secondary-button" onClick={() => navigate("/transactions")}>
              View Ledger
            </button>
          )}
        />

        <div className="dashboard-card product-guide-card">
          <div className="section-header">
            <h2>How to read Analytics</h2>
            <p>
              Analytics is the deeper learning page. Use the quick ranges first, then read the
              pattern chart to see whether spending is rising, dropping, or staying stable.
            </p>
          </div>

          <div className="feature-guide-grid">
            <div className="feature-guide-item">
              <span className="feature-step">Daily</span>
              <h3>Short-term pace</h3>
              <p>
                Last 7 Days shows the newest spending pulse. Use it when you want to know if this
                week is heavier than normal.
              </p>
            </div>

            <div className="feature-guide-item">
              <span className="feature-step">Monthly</span>
              <h3>Current month control</h3>
              <p>
                Current Month keeps the view focused on the month you are living in right now,
                which is the best range for budgeting decisions.
              </p>
            </div>

            <div className="feature-guide-item">
              <span className="feature-step">3 / 6</span>
              <h3>Longer-term direction</h3>
              <p>
                Last 3 Months catches recent behavior changes. Last 6 Months shows the bigger
                baseline so you can tell whether the change is real or just one odd month.
              </p>
            </div>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Analytics Filters</h2>
            <p>Refine the analysis using account scope, month, date range, type, and category.</p>
          </div>

          <div className="filter-bar">
            <AccountSelector
              value={selectedAccountId}
              label="Account scope"
              onChange={setSelectedAccountId}
            />

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

          <div className="analytics-preset-row">
            <button type="button" className="secondary-button" onClick={() => applyDatePreset("week")}>
              Last 7 Days
            </button>
            <button type="button" className="secondary-button" onClick={() => applyDatePreset("month")}>
              Current Month
            </button>
            <button type="button" className="secondary-button" onClick={() => applyDatePreset("3m")}>
              Last 3 Months
            </button>
            <button type="button" className="secondary-button" onClick={() => applyDatePreset("6m")}>
              Last 6 Months
            </button>
          </div>
        </div>

        <div className="summary-grid">
          <div className="summary-card income-card">
            <span className="card-label">Total Income</span>
            <p>${summary.total_income.toFixed(2)}</p>
          </div>

          <div className="summary-card expense-card">
            <span className="card-label">Total Expenses</span>
            <p>${summary.total_expenses.toFixed(2)}</p>
          </div>

          <div className="summary-card balance-card">
            <span className="card-label">Balance</span>
            <p>${summary.balance.toFixed(2)}</p>
          </div>

          <div className="summary-card top-card">
            <span className="card-label">Top Expense Category</span>
            <p>
              {normalizedTopCategory
                ? `${normalizedTopCategory.category} ($${normalizedTopCategory.total.toFixed(2)})`
                : "No expense data"}
            </p>
          </div>
        </div>

        <div className="dashboard-card spending-pattern-card">
          <div className="section-header">
            <div>
              <h2>Spending Pattern Pulse</h2>
              <p>
                Dot-and-line view of your expense movement. It compares this week against the
                current month, then recent 3-month behavior against the 6-month baseline.
              </p>
            </div>
            <span className={`pattern-status-pill pattern-status-${spendingPatternPulse.tone}`}>
              {spendingPatternPulse.status}
            </span>
          </div>

          <p className="pattern-narrative">{spendingPatternPulse.narrative}</p>

          <div className="pattern-comparison-grid">
            <div className="pattern-metric-card">
              <span>Last 7 days</span>
              <strong>{formatMoney(spendingPatternPulse.lastSevenTotal)}</strong>
              <p>
                {formatMoney(spendingPatternPulse.lastSevenDailyAverage)}/day,
                {" "}
                {formatPercentChange(spendingPatternPulse.sevenVsMonthChange)}
                {" "}
                vs this month&apos;s daily pace.
              </p>
            </div>

            <div className="pattern-metric-card">
              <span>Current month</span>
              <strong>{formatMoney(spendingPatternPulse.currentMonthTotal)}</strong>
              <p>
                Month-to-date spending compared with the 3-month average:
                {" "}
                {formatPercentChange(spendingPatternPulse.currentVsThreeChange)}.
              </p>
            </div>

            <div className="pattern-metric-card">
              <span>3 months vs 6 months</span>
              <strong>{formatPercentChange(spendingPatternPulse.threeVsSixChange)}</strong>
              <p>
                3-month average {formatMoney(spendingPatternPulse.lastThreeAverage)} vs
                6-month average {formatMoney(spendingPatternPulse.lastSixAverage)}.
              </p>
            </div>
          </div>

          {!spendingPatternPulse.hasData ? (
            <div className="empty-state">
              <p>No expense pattern yet. Add transactions or import a statement to activate this chart.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={spendingPatternPulse.chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="month" tick={{ fill: chartTheme.text, fontSize: 12 }} />
                <YAxis tick={{ fill: chartTheme.text, fontSize: 12 }} />
                <Tooltip contentStyle={customTooltipStyle} formatter={(value, name) => [formatMoney(value), name]} />
                <Legend
                  verticalAlign="bottom"
                  height={36}
                  formatter={(value) => (
                    <span style={{ color: chartTheme.text }}>{value}</span>
                  )}
                />
                <Line
                  type="monotone"
                  dataKey="expenses"
                  name="Monthly expenses"
                  stroke={chartTheme.patternLine}
                  strokeWidth={3}
                  dot={{ r: 5, strokeWidth: 2 }}
                  activeDot={{ r: 8 }}
                />
                <Line
                  type="monotone"
                  dataKey="threeMonthAverage"
                  name="3-month average"
                  stroke={chartTheme.threeMonthLine}
                  strokeWidth={2}
                  strokeDasharray="6 5"
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="sixMonthAverage"
                  name="6-month average"
                  stroke={chartTheme.sixMonthLine}
                  strokeWidth={2}
                  strokeDasharray="3 5"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {normalizedAccountId === undefined && accountComparison.length > 1 && (
          <div className="dashboard-card account-comparison-card">
            <div className="section-header">
              <h2>Accounts at a Glance</h2>
              <p>See which account is carrying the most income, expenses, and balance pressure.</p>
            </div>

            <div className="account-comparison-grid">
              {accountComparison.map((account, index) => (
                <div
                  key={`account-comparison-${account.account_id}`}
                  className={`account-comparison-item ${index === 0 ? "account-comparison-leading" : ""}`}
                >
                  <div className="account-comparison-header">
                    <div>
                      <h3>{account.name}</h3>
                      <p>{account.type}</p>
                    </div>
                    {index === 0 && <span className="account-comparison-badge">Highest spend</span>}
                  </div>

                  <div className="account-comparison-metrics">
                    <div>
                      <span>Income</span>
                      <strong>${account.total_income.toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>Expenses</span>
                      <strong>${account.total_expenses.toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>Balance</span>
                      <strong>${account.balance.toFixed(2)}</strong>
                    </div>
                  </div>

                  <p className="account-comparison-footnote">
                    {account.top_category
                      ? `Top category: ${formatCategoryName(account.top_category)} ($${account.top_category_amount.toFixed(2)})`
                      : "No category spending recorded yet."}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div
          ref={alertsRef}
          className={`dashboard-card alerts-card ${getSectionHighlightClass("alerts")}`}
        >
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

        <div
          ref={trendsRef}
          className={`dashboard-card trends-card ${getSectionHighlightClass("trends")}`}
        >
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
                            <strong>{formatCategoryName(item.category)}</strong>
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
                            <strong>{formatCategoryName(item.category)}</strong>
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

        <div
          ref={insightsRef}
          className={`dashboard-card insights-card ${getSectionHighlightClass("insights")}`}
        >
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

        <div
          ref={monthlyRef}
          className={`chart-grid ${getSectionHighlightClass("monthly")}`}
        >
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
                  <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                  <XAxis dataKey="month" tick={{ fill: chartTheme.text, fontSize: 12 }} />
                  <YAxis tick={{ fill: chartTheme.text, fontSize: 12 }} />
                  <Tooltip contentStyle={customTooltipStyle} />
                  <Bar dataKey="income" fill={chartTheme.incomeBar} radius={[8, 8, 0, 0]} />
                  <Bar dataKey="expenses" fill={chartTheme.expenseBar} radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="dashboard-card">
            <div className="section-header">
              <h2>Top 5 Expense Categories</h2>
              <p>Focus on the categories that have the biggest effect on your balance.</p>
            </div>

            {topPieData.length === 0 ? (
              <div className="empty-state">
                <p>No expense categories found.</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={340}>
                <PieChart>
                  <Pie
                    data={topPieData}
                    dataKey="total"
                    nameKey="category"
                    cx="50%"
                    cy="46%"
                    outerRadius={100}
                    innerRadius={52}
                    paddingAngle={4}
                    labelLine={false}
                    label={({ name, percent }) =>
                      percent >= 0.05 ? `${name} ${(percent * 100).toFixed(0)}%` : ""
                    }
                  >
                    {topPieData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={chartTheme.pieColors[index % chartTheme.pieColors.length]}
                      />
                    ))}
                  </Pie>

                  <Tooltip
                    formatter={pieTooltipFormatter}
                    contentStyle={customTooltipStyle}
                  />

                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(value) => (
                      <span style={{ color: chartTheme.text }}>{value}</span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div
          ref={categoriesRef}
          className={`dashboard-card ${getSectionHighlightClass("categories")}`}
        >
          <div className="section-header">
            <h2>Expense Categories</h2>
            <p>Ranked from highest to lowest total expense, with duplicates merged cleanly.</p>
          </div>

          {mergedCategoryBreakdown.length === 0 ? (
            <div className="empty-state">
              <p>No expense categories found.</p>
            </div>
          ) : (
            <div className="category-list">
              {mergedCategoryBreakdown.map((item) => (
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
