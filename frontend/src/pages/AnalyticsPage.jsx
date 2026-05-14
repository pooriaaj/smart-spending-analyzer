import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "../services/api";
import AccountSelector from "../components/AccountSelector";
import PageHeader from "../components/PageHeader";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId } from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import { formatAccountName, formatAccountType, formatCategoryLabel } from "../utils/displayLabels";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
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

const CASHFLOW_NEUTRAL_CATEGORIES = new Set(["transfer", "transfers", "refund", "refunds"]);
const CASHFLOW_NEUTRAL_DESCRIPTION_MARKERS = [
  "e-transfer received",
  "e-transfer sent",
  "interac received",
  "interac sent",
  "online transfer",
  "online banking transfer",
  "payment - thank you",
  "payment thank you",
  "paiement - merci",
  "payback with points",
  "atm deposit",
  "virement interac",
  "virement en ligne",
];
const CATEGORY_PIE_COLORS = ["#60a5fa", "#34d399", "#f87171", "#fbbf24", "#a78bfa"];

function formatCategoryName(category, t) {
  if (!category || typeof category !== "string") return formatCategoryLabel("other", t);
  const normalized = category.trim().toLowerCase();
  return formatCategoryLabel(CATEGORY_ALIASES[normalized] || category, t);
}

function mergeCategoryBreakdown(items, t) {
  const mergedMap = new Map();

  (items || []).forEach((item) => {
    const displayCategory = formatCategoryName(item.category, t);
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

const formatPercentChange = (value, t) => {
  if (value == null || Number.isNaN(value)) return t("analytics.notEnoughData");
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
        transaction.parsedDate &&
        !CASHFLOW_NEUTRAL_CATEGORIES.has(String(transaction.category || "").trim().toLowerCase()) &&
        !CASHFLOW_NEUTRAL_DESCRIPTION_MARKERS.some((marker) =>
          String(transaction.description || "").toLowerCase().includes(marker)
        )
    );

const sumExpensesBetween = (transactions, startDate, endDate) =>
  transactions.reduce((total, transaction) => {
    if (transaction.parsedDate >= startDate && transaction.parsedDate <= endDate) {
      return total + transaction.amount;
    }
    return total;
  }, 0);

function buildSpendingPatternPulse(transactions, t) {
  const expenseTransactions = getExpenseTransactions(transactions);
  const today = new Date();
  today.setHours(23, 59, 59, 999);
  const lastSevenStart = new Date(today);
  lastSevenStart.setDate(today.getDate() - 6);
  lastSevenStart.setHours(0, 0, 0, 0);
  const lastThirtyStart = new Date(today);
  lastThirtyStart.setDate(today.getDate() - 29);
  lastThirtyStart.setHours(0, 0, 0, 0);

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
  const lastThirtyTotal = sumExpensesBetween(expenseTransactions, lastThirtyStart, today);
  const lastSevenDailyAverage = lastSevenTotal / 7;
  const lastThirtyDailyAverage = lastThirtyTotal / 30;

  const sevenVsThirtyChange = calculateChangePercent(lastSevenDailyAverage, lastThirtyDailyAverage);
  const threeVsSixChange = calculateChangePercent(lastThreeAverage, lastSixAverage);
  const thirtyVsThreeChange = calculateChangePercent(lastThirtyTotal, lastThreeAverage);
  const primaryMovement =
    sevenVsThirtyChange != null ? sevenVsThirtyChange : threeVsSixChange;

  let status = t("analytics.buildingPattern");
  let tone = "neutral";
  if (expenseTransactions.length > 0 && primaryMovement != null) {
    if (primaryMovement > 15) {
      status = t("analytics.spendingRising");
      tone = "warning";
    } else if (primaryMovement < -15) {
      status = t("analytics.spendingDropping");
      tone = "positive";
    } else {
      status = t("analytics.spendingSteady");
      tone = "stable";
    }
  }

  const narrative =
    expenseTransactions.length === 0
      ? t("analytics.unlockMovementSignals")
      : t("analytics.pulseNarrative", {
          sevenDayAverage: formatMoney(lastSevenDailyAverage),
          monthAverage: formatMoney(lastThirtyDailyAverage),
          threeMonthAverage: formatMoney(lastThreeAverage),
          sixMonthAverage: formatMoney(lastSixAverage),
        });

  return {
    hasData: expenseTransactions.length > 0,
    status,
    tone,
    narrative,
    lastSevenTotal,
    lastSevenDailyAverage,
    lastThirtyTotal,
    lastThirtyDailyAverage,
    lastThreeAverage,
    lastSixAverage,
    sevenVsThirtyChange,
    threeVsSixChange,
    thirtyVsThreeChange,
    chartData: monthKeys.map((monthKey, index) => ({
      month: formatShortMonth(monthKey),
      expenses: monthlyValues[index],
      threeMonthAverage: Number(lastThreeAverage.toFixed(2)),
      sixMonthAverage: Number(lastSixAverage.toFixed(2)),
    })),
  };
}

function AnalyticsPage() {
  const { t } = useLanguage();
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
    if (urlCategory) setSelectedCategory(formatCategoryName(urlCategory, t));
  }, [searchParams, t]);

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
    };
  }, [themeMode]);

  const rawCategoryBreakdown = useMemo(
    () => dashboardData?.category_breakdown || [],
    [dashboardData?.category_breakdown]
  );

  const mergedCategoryBreakdown = useMemo(() => {
    return mergeCategoryBreakdown(rawCategoryBreakdown, t);
  }, [rawCategoryBreakdown, t]);

  const categoryChartData = useMemo(() => {
    return mergedCategoryBreakdown.map((item) => ({
      ...item,
      totalLabel: formatMoney(item.total),
    }));
  }, [mergedCategoryBreakdown]);

  const topCategoryPieData = useMemo(() => {
    const topCategories = mergedCategoryBreakdown.slice(0, 5);
    const total = topCategories.reduce((sum, item) => sum + Number(item.total || 0), 0);

    return topCategories.map((item, index) => ({
      ...item,
      fill: CATEGORY_PIE_COLORS[index % CATEGORY_PIE_COLORS.length],
      sharePercent: total > 0 ? (Number(item.total || 0) / total) * 100 : 0,
      label: `${item.category} ${total > 0 ? `${((Number(item.total || 0) / total) * 100).toFixed(0)}%` : ""}`,
    }));
  }, [mergedCategoryBreakdown]);

  const categoryChartHeight = Math.max(320, categoryChartData.length * 46 + 80);

  const availableCategories = useMemo(() => {
    return mergedCategoryBreakdown.map((item) => item.category);
  }, [mergedCategoryBreakdown]);

  const spendingPatternPulse = useMemo(() => {
    return buildSpendingPatternPulse(transactions, t);
  }, [transactions, t]);

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

    const start = new Date(today);
    if (preset === "week") {
      start.setDate(today.getDate() - 6);
    }
    if (preset === "30d") {
      start.setDate(today.getDate() - 29);
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

  const handleCategoryDrilldown = (category) => {
    if (!category) return;
    navigate(`/transactions?category=${encodeURIComponent(category)}`);
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

  if (loading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>{t("analytics.loadingTitle")}</h2>
            <p>{t("analytics.loadingDetail")}</p>
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
  const monthlySummary = dashboardData?.monthly_summary || [];
  const spendingInsights = dashboardData?.spending_insights;
  const overspendingAlerts = dashboardData?.overspending_alerts;
  const categoryTrends = dashboardData?.category_trends;
  const accountComparison = dashboardData?.account_comparison || [];

  const normalizedTopCategory = mergedCategoryBreakdown[0] || null;

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <PageHeader
          icon="AN"
          titleKey="common.analyticsInsights"
          subtitleKey="headers.analyticsSubtitle"
          actions={(
            <button className="secondary-button" onClick={() => navigate("/transactions")}>
              {t("common.viewLedger")}
            </button>
          )}
        />

        <div className="dashboard-card product-guide-card">
          <div className="section-header">
            <h2>{t("analytics.howTitle")}</h2>
            <p>{t("analytics.howDetail")}</p>
          </div>

          <div className="feature-guide-grid">
            <div className="feature-guide-item">
              <span className="feature-step">{t("analytics.daily")}</span>
              <h3>{t("analytics.shortTermPace")}</h3>
              <p>{t("analytics.shortTermDetail")}</p>
            </div>

            <div className="feature-guide-item">
              <span className="feature-step">{t("analytics.monthly")}</span>
              <h3>{t("analytics.rolling30DayControl")}</h3>
              <p>{t("analytics.rolling30DayDetail")}</p>
            </div>

            <div className="feature-guide-item">
              <span className="feature-step">3 / 6</span>
              <h3>{t("analytics.longerDirection")}</h3>
              <p>{t("analytics.longerDirectionDetail")}</p>
            </div>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>{t("analytics.filtersTitle")}</h2>
            <p>{t("analytics.filtersDetail")}</p>
          </div>

          <div className="filter-bar">
            <AccountSelector
              value={selectedAccountId}
              label={t("common.accountScope")}
              onChange={setSelectedAccountId}
            />

            <div>
              <label>{t("common.month")}</label>
              <select
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
              >
                <option value="">{t("common.all")}</option>
                {monthlySummary.map((item) => (
                  <option key={item.month} value={item.month}>
                    {item.month}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label>{t("common.from")}</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>

            <div>
              <label>{t("common.to")}</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>

            <div>
              <label>{t("common.type")}</label>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
              >
                <option value="">{t("common.all")}</option>
                <option value="income">{t("common.income")}</option>
                <option value="expense">{t("common.expense")}</option>
              </select>
            </div>

            <div>
              <label>{t("common.category")}</label>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
              >
                <option value="">{t("common.all")}</option>
                {availableCategories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </div>

            <div className="filter-actions">
              <button className="clear-filter-button" onClick={clearFilters}>
                {t("common.clearFilters")}
              </button>
            </div>
          </div>

          <div className="analytics-preset-row">
            <button type="button" className="secondary-button" onClick={() => applyDatePreset("week")}>
              {t("analytics.last7Days")}
            </button>
            <button type="button" className="secondary-button" onClick={() => applyDatePreset("30d")}>
              {t("analytics.last30Days")}
            </button>
            <button type="button" className="secondary-button" onClick={() => applyDatePreset("3m")}>
              {t("analytics.last3Months")}
            </button>
            <button type="button" className="secondary-button" onClick={() => applyDatePreset("6m")}>
              {t("analytics.last6Months")}
            </button>
          </div>
        </div>

        <div className="summary-grid">
          <div className="summary-card income-card">
            <span className="card-label">{t("analytics.totalIncome")}</span>
            <p>${summary.total_income.toFixed(2)}</p>
          </div>

          <div className="summary-card expense-card">
            <span className="card-label">{t("analytics.totalExpenses")}</span>
            <p>${summary.total_expenses.toFixed(2)}</p>
          </div>

          <div className="summary-card balance-card">
            <span className="card-label">{t("common.balance")}</span>
            <p>${summary.balance.toFixed(2)}</p>
          </div>

          <div className="summary-card top-card">
            <span className="card-label">{t("analytics.topExpenseCategory")}</span>
            <p>
              {normalizedTopCategory
                ? `${normalizedTopCategory.category} ($${normalizedTopCategory.total.toFixed(2)})`
                : t("analytics.noExpenseData")}
            </p>
          </div>
        </div>

        <div className="dashboard-card spending-pattern-card">
          <div className="section-header">
            <div>
              <h2>{t("analytics.spendingPulse")}</h2>
              <p>{t("analytics.spendingPulseDetail")}</p>
            </div>
            <span className={`pattern-status-pill pattern-status-${spendingPatternPulse.tone}`}>
              {spendingPatternPulse.status}
            </span>
          </div>

          <p className="pattern-narrative">{spendingPatternPulse.narrative}</p>

          <div className="pattern-comparison-grid">
            <div className="pattern-metric-card">
              <span>{t("analytics.last7DaysShort")}</span>
              <strong>{formatMoney(spendingPatternPulse.lastSevenTotal)}</strong>
              <p>
                {t("analytics.dayAveragePace", {
                  amount: formatMoney(spendingPatternPulse.lastSevenDailyAverage),
                  change: formatPercentChange(spendingPatternPulse.sevenVsThirtyChange, t),
                })}
              </p>
            </div>

            <div className="pattern-metric-card">
              <span>{t("analytics.last30DaysShort")}</span>
              <strong>{formatMoney(spendingPatternPulse.lastThirtyTotal)}</strong>
              <p>
                {t("analytics.last30Comparison", {
                  change: formatPercentChange(spendingPatternPulse.thirtyVsThreeChange, t),
                })}
              </p>
            </div>

            <div className="pattern-metric-card">
              <span>{t("analytics.threeVsSix")}</span>
              <strong>{formatPercentChange(spendingPatternPulse.threeVsSixChange, t)}</strong>
              <p>
                {t("analytics.threeSixComparison", {
                  three: formatMoney(spendingPatternPulse.lastThreeAverage),
                  six: formatMoney(spendingPatternPulse.lastSixAverage),
                })}
              </p>
            </div>
          </div>

          {!spendingPatternPulse.hasData ? (
            <div className="empty-state">
              <p>{t("analytics.noExpensePattern")}</p>
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
                  name={t("analytics.monthlyExpenses")}
                  stroke={chartTheme.patternLine}
                  strokeWidth={3}
                  dot={{ r: 5, strokeWidth: 2 }}
                  activeDot={{ r: 8 }}
                />
                <Line
                  type="monotone"
                  dataKey="threeMonthAverage"
                  name={t("analytics.threeMonthAverage")}
                  stroke={chartTheme.threeMonthLine}
                  strokeWidth={2}
                  strokeDasharray="6 5"
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="sixMonthAverage"
                  name={t("analytics.sixMonthAverage")}
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
              <h2>{t("analytics.accountsGlance")}</h2>
              <p>{t("analytics.accountsGlanceDetail")}</p>
            </div>

            <div className="account-comparison-grid">
              {accountComparison.map((account, index) => (
                <div
                  key={`account-comparison-${account.account_id}`}
                  className={`account-comparison-item ${index === 0 ? "account-comparison-leading" : ""}`}
                >
                  <div className="account-comparison-header">
                    <div>
                      <h3>{formatAccountName(account.name, t)}</h3>
                      <p>{formatAccountType(account.type, t)}</p>
                    </div>
                    {index === 0 && <span className="account-comparison-badge">{t("analytics.highestSpend")}</span>}
                  </div>

                  <div className="account-comparison-metrics">
                    <div>
                      <span>{t("common.income")}</span>
                      <strong>${account.total_income.toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>{t("common.expenses")}</span>
                      <strong>${account.total_expenses.toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>{t("common.balance")}</span>
                      <strong>${account.balance.toFixed(2)}</strong>
                    </div>
                  </div>

                  <p className="account-comparison-footnote">
                    {account.top_category
                      ? `${t("analytics.topCategory")}: ${formatCategoryName(account.top_category, t)} ($${account.top_category_amount.toFixed(2)})`
                      : t("analytics.noCategorySpending")}
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
            <h2>{t("analytics.overspendingAlerts")}</h2>
            <p>{t("analytics.overspendingAlertsDetail")}</p>
          </div>

          {!overspendingAlerts || overspendingAlerts.alerts.length === 0 ? (
            <div className="empty-state">
              <p>{t("analytics.noAlerts")}</p>
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
            <h2>{t("analytics.categoryTrendComparison")}</h2>
            <p>{t("analytics.categoryTrendDetail")}</p>
          </div>

          {!categoryTrends ? (
            <div className="empty-state">
              <p>{t("analytics.noTrendData")}</p>
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
                  <h3>{t("analytics.topIncreases")}</h3>
                  {categoryTrends.top_increases.length === 0 ? (
                    <p className="trend-empty-text">{t("analytics.noIncreases")}</p>
                  ) : (
                    <div className="trend-list">
                      {categoryTrends.top_increases.map((item) => (
                        <div key={`increase-${item.category}`} className="trend-item">
                          <div>
                            <strong>{formatCategoryName(item.category, t)}</strong>
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
                  <h3>{t("analytics.topDecreases")}</h3>
                  {categoryTrends.top_decreases.length === 0 ? (
                    <p className="trend-empty-text">{t("analytics.noDecreases")}</p>
                  ) : (
                    <div className="trend-list">
                      {categoryTrends.top_decreases.map((item) => (
                        <div key={`decrease-${item.category}`} className="trend-item">
                          <div>
                            <strong>{formatCategoryName(item.category, t)}</strong>
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
            <h2>{t("analytics.spendingInsights")}</h2>
            <p>{t("analytics.spendingInsightsDetail")}</p>
          </div>

          {!spendingInsights ? (
            <div className="empty-state">
              <p>{t("analytics.noInsights")}</p>
            </div>
          ) : (
            <div className="insights-grid">
              <div className="insights-block">
                <h3>{t("analytics.observations")}</h3>
                <ul className="insights-list">
                  {spendingInsights.insights.map((item, index) => (
                    <li key={`insight-${index}`}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="insights-block">
                <h3>{t("analytics.recommendations")}</h3>
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
              <h2>{t("analytics.monthlySummary")}</h2>
              <p>{t("analytics.monthlySummaryDetail")}</p>
            </div>

            {monthlySummary.length === 0 ? (
              <div className="empty-state">
                <p>{t("analytics.noMonthlyData")}</p>
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

            {topCategoryPieData.length > 0 && (
              <div className="analytics-top-pie">
                <div className="section-header compact-section-header">
                  <h3>{t("analytics.topFivePieTitle")}</h3>
                  <p>{t("analytics.topFivePieDetail")}</p>
                </div>
                <div className="analytics-top-pie-layout">
                  <ResponsiveContainer width="100%" height={260}>
                    <PieChart>
                      <Pie
                        data={topCategoryPieData}
                        dataKey="total"
                        nameKey="category"
                        cx="50%"
                        cy="50%"
                        innerRadius={58}
                        outerRadius={96}
                        paddingAngle={3}
                        labelLine={false}
                        label={({ payload }) => `${Number(payload?.sharePercent || 0).toFixed(0)}%`}
                        onClick={(entry) => handleCategoryDrilldown(entry?.category)}
                        cursor="pointer"
                      >
                        {topCategoryPieData.map((item) => (
                          <Cell key={`pie-cell-${item.category}`} fill={item.fill} />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(value, _name, props) => [
                          `${formatMoney(value)} (${Number(props?.payload?.sharePercent || 0).toFixed(1)}%)`,
                          props?.payload?.category || t("common.category"),
                        ]}
                        contentStyle={customTooltipStyle}
                      />
                    </PieChart>
                  </ResponsiveContainer>

                  <div className="analytics-top-pie-legend">
                    {topCategoryPieData.map((item) => (
                      <button
                        key={`pie-legend-${item.category}`}
                        type="button"
                        className="analytics-top-pie-row"
                        onClick={() => handleCategoryDrilldown(item.category)}
                      >
                        <span style={{ backgroundColor: item.fill }} />
                        <strong>{formatCategoryName(item.category, t)}</strong>
                        <em>{formatMoney(item.total)}</em>
                        <small>{item.sharePercent.toFixed(1)}%</small>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="dashboard-card">
            <div className="section-header">
              <h2>{t("analytics.categoryChartTitle")}</h2>
              <p>{t("analytics.categoryChartDetail")}</p>
            </div>

            {categoryChartData.length === 0 ? (
              <div className="empty-state">
                <p>{t("dashboard.noExpenseCategories")}</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={categoryChartHeight}>
                <BarChart
                  data={categoryChartData}
                  layout="vertical"
                  margin={{ top: 8, right: 42, bottom: 8, left: 18 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fill: chartTheme.text, fontSize: 12 }}
                    tickFormatter={(value) => `$${Number(value).toFixed(0)}`}
                  />
                  <YAxis
                    type="category"
                    dataKey="category"
                    width={118}
                    tick={{ fill: chartTheme.text, fontSize: 12 }}
                  />
                  <Tooltip
                    formatter={(value) => [formatMoney(value), t("common.amount")]}
                    contentStyle={customTooltipStyle}
                  />
                  <Bar
                    dataKey="total"
                    fill={chartTheme.patternLine}
                    radius={[0, 10, 10, 0]}
                    label={{
                      dataKey: "totalLabel",
                      position: "right",
                      fill: chartTheme.text,
                      fontSize: 12,
                    }}
                    onClick={(entry) => handleCategoryDrilldown(entry?.category)}
                    cursor="pointer"
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div
          ref={categoriesRef}
          className={`dashboard-card ${getSectionHighlightClass("categories")}`}
        >
          <div className="section-header">
            <h2>{t("dashboard.expenseCategoriesTitle")}</h2>
            <p>{t("analytics.expenseCategoriesDetail")}</p>
          </div>

          {mergedCategoryBreakdown.length === 0 ? (
            <div className="empty-state">
              <p>{t("dashboard.noExpenseCategories")}</p>
            </div>
          ) : (
            <div className="category-list">
              {mergedCategoryBreakdown.map((item) => (
                <button
                  key={item.category}
                  type="button"
                  className="category-item category-drilldown-item"
                  onClick={() => handleCategoryDrilldown(item.category)}
                >
                  <span>{formatCategoryName(item.category, t)}</span>
                  <strong>{formatMoney(item.total)}</strong>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AnalyticsPage;
