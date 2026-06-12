import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  IconTag,
  IconTrendingDown,
  IconTrendingUp,
  IconWallet,
} from "@tabler/icons-react";
import {
  Badge,
  Box,
  Button,
  Card,
  Container,
  Grid,
  Group,
  NativeSelect,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
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

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

function getItemsFromResponse(data) {
  if (Array.isArray(data)) {
    return data;
  }

  if (Array.isArray(data?.items)) {
    return data.items;
  }

  if (Array.isArray(data?.transactions)) {
    return data.transactions;
  }

  return [];
}

function formatCategoryName(category, t) {
  if (!category || typeof category !== "string") return formatCategoryLabel("other", t);
  const normalized = category.trim().toLowerCase();
  return formatCategoryLabel(CATEGORY_ALIASES[normalized] || category, t);
}

function mergeCategoryBreakdown(items, t) {
  const mergedMap = new Map();

  toArray(items).forEach((item) => {
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

const formatMoney = (value) => {
  const numberValue = Number(value || 0);
  const amount = Math.abs(numberValue).toFixed(2);
  return numberValue < 0 ? `-$${amount}` : `$${amount}`;
};

const sentenceCaseText = (value) => {
  const text = String(value || "").trim();
  return text ? `${text.charAt(0).toUpperCase()}${text.slice(1)}` : "";
};

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
  toArray(transactions)
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

function OverviewStatCard({ label, value, tone, helper, icon: Icon }) {
  return (
    <Card className={`overview-stat-card overview-stat-card-${tone}`} radius="lg" p="lg">
      <Stack gap="md" h="100%" justify="space-between">
        <Group justify="space-between" align="flex-start" gap="sm">
          <Text className="overview-stat-label">{label}</Text>
          {Icon && (
            <Box className={`overview-stat-icon-badge overview-stat-icon-badge-${tone}`} aria-hidden="true">
              <Icon size={18} stroke={2} />
            </Box>
          )}
        </Group>
        <Box>
          <Text className="overview-stat-value">{value}</Text>
          {helper && <Text className="overview-stat-helper">{helper}</Text>}
        </Box>
      </Stack>
    </Card>
  );
}

function InsightCard({ label, value, detail, tone = "neutral" }) {
  return (
    <Paper className={`overview-insight-card overview-insight-card-${tone}`} radius="lg" p="md">
      <Stack gap={6}>
        <Text className="overview-insight-label">{label}</Text>
        <Text className="overview-insight-value">{value}</Text>
        {detail && <Text className="overview-insight-detail">{detail}</Text>}
      </Stack>
    </Paper>
  );
}

function AnalyticsPage() {
  const { t } = useLanguage();
  const [searchParams, setSearchParams] = useSearchParams();
  const [dashboardData, setDashboardData] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [selectedMonth, setSelectedMonth] = useState(() => searchParams.get("month") || "");
  const [startDate, setStartDate] = useState(() => searchParams.get("start") || "");
  const [endDate, setEndDate] = useState(() => searchParams.get("end") || "");
  const [selectedType, setSelectedType] = useState(() => searchParams.get("type") || "");
  const [selectedCategory, setSelectedCategory] = useState(() => {
    const urlCategory = searchParams.get("category") || "";
    return urlCategory ? formatCategoryName(urlCategory, t) : "";
  });
  const [loading, setLoading] = useState(true);
  const [themeMode, setThemeMode] = useState(
    document.documentElement.getAttribute("data-theme") || "light"
  );

  const alertsRef = useRef(null);
  const monthlyRef = useRef(null);
  const categoriesRef = useRef(null);

  const navigate = useNavigate();
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
    let active = true;

    const fetchDashboardAnalytics = async () => {
      try {
        setLoading(true);
        setTransactions([]);

        const response = await api.get("/analytics/dashboard", {
          params: {
            account_id: normalizedAccountId,
            month: selectedMonth || undefined,
            start_date: startDate || undefined,
            end_date: endDate || undefined,
            transaction_type: selectedType || undefined,
            category: selectedCategory || undefined,
          },
        });

        if (!active) return;

        setDashboardData(response.data);
        setLoading(false);

        api
          .get("/transactions/", {
            params: {
              account_id: normalizedAccountId,
              limit: 1000,
            },
          })
          .then((transactionsResponse) => {
            if (active) {
              setTransactions(getItemsFromResponse(transactionsResponse.data));
            }
          })
          .catch((error) => {
            if (active) {
              console.error("Failed to load spending pulse transactions:", error);
              handleApiAuthError(error, navigate);
            }
          });
      } catch (error) {
        console.error("Failed to load analytics data:", error);

        handleApiAuthError(error, navigate);
        if (active) {
          setLoading(false);
        }
      }
    };

    fetchDashboardAnalytics();

    return () => {
      active = false;
    };
  }, [navigate, normalizedAccountId, selectedMonth, startDate, endDate, selectedType, selectedCategory]);

  useEffect(() => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (selectedMonth) next.set("month", selectedMonth); else next.delete("month");
        if (startDate) next.set("start", startDate); else next.delete("start");
        if (endDate) next.set("end", endDate); else next.delete("end");
        if (selectedType) next.set("type", selectedType); else next.delete("type");
        if (selectedCategory) next.set("category", selectedCategory); else next.delete("category");
        return next;
      },
      { replace: true }
    );
  }, [selectedMonth, startDate, endDate, selectedType, selectedCategory, setSearchParams]);

  useEffect(() => {
    const section = searchParams.get("section");
    if (!section || loading) return;

    const sectionMap = {
      alerts: alertsRef,
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
    () => toArray(dashboardData?.category_breakdown),
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
  const monthlySummary = toArray(dashboardData?.monthly_summary);
  const overspendingAlerts = dashboardData?.overspending_alerts;
  const overspendingAlertItems = toArray(overspendingAlerts?.alerts);
  const accountComparison = toArray(dashboardData?.account_comparison);

  const normalizedTopCategory = mergedCategoryBreakdown[0] || null;
  const topExpenseCategoryValue = normalizedTopCategory
    ? `${normalizedTopCategory.category} (${formatMoney(normalizedTopCategory.total)})`
    : t("analytics.noExpenseData");

  return (
    <Box className="overview-page-shell">
      <Container size="xl" px={{ base: "md", md: "lg" }} py={{ base: "lg", md: "xl" }}>
        <Stack gap="lg">
          <Paper className="overview-hero" radius="xl" p={{ base: "lg", md: "xl" }}>
            <Group justify="space-between" align="flex-start" gap="xl">
              <Stack gap="xs" className="overview-hero-copy">
                <Badge color="teal" variant="light" radius="sm">
                  {t("common.appName")}
                </Badge>
                <Title order={1}>{t("common.analytics")}</Title>
                <Text size="md">{t("headers.analyticsSubtitle")}</Text>
              </Stack>

              <Group className="overview-hero-actions" justify="flex-end" gap="sm">
                <Button color="teal" radius="md" onClick={() => navigate("/import")}>
                  {t("common.uploadStatement")}
                </Button>
                <Button variant="light" color="teal" radius="md" onClick={() => navigate("/transactions")}>
                  {t("common.addManualRow")}
                </Button>
                <Button variant="outline" color="indigo" radius="md" onClick={() => navigate("/assistant")}>
                  {t("common.assistant")}
                </Button>
              </Group>
            </Group>
          </Paper>

          <Card className="filter-card overview-filter-card" radius="xl" p={{ base: "md", md: "lg" }}>
            <Stack gap="md">
              <Box>
                <Title order={2} size="h3">{t("analytics.filtersTitle")}</Title>
                <Text size="sm" c="dimmed">{t("analytics.filtersDetail")}</Text>
              </Box>

              <Grid gutter="md" align="flex-end">
                <Grid.Col span={{ base: 12, sm: 6, lg: 4 }}>
                  <Box className="overview-account-field">
                    <AccountSelector
                      value={selectedAccountId}
                      label={t("common.accountScope")}
                      onChange={setSelectedAccountId}
                    />
                  </Box>
                </Grid.Col>

                <Grid.Col span={{ base: 12, sm: 6, lg: 2 }}>
                  <NativeSelect
                    label={t("common.month")}
                    value={selectedMonth}
                    onChange={(e) => setSelectedMonth(e.target.value)}
                    data={[
                      { value: "", label: t("common.all") },
                      ...monthlySummary.map((item) => ({ value: item.month, label: item.month })),
                    ]}
                  />
                </Grid.Col>

                <Grid.Col span={{ base: 12, sm: 6, lg: 2 }}>
                  <TextInput
                    type="date"
                    label={t("common.from")}
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                  />
                </Grid.Col>

                <Grid.Col span={{ base: 12, sm: 6, lg: 2 }}>
                  <TextInput
                    type="date"
                    label={t("common.to")}
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                  />
                </Grid.Col>

                <Grid.Col span={{ base: 12, sm: 6, lg: 2 }}>
                  <NativeSelect
                    label={t("common.type")}
                    value={selectedType}
                    onChange={(e) => setSelectedType(e.target.value)}
                    data={[
                      { value: "", label: t("common.all") },
                      { value: "income", label: t("common.income") },
                      { value: "expense", label: t("common.expense") },
                    ]}
                  />
                </Grid.Col>

                <Grid.Col span={{ base: 12, sm: 6, lg: 4 }}>
                  <NativeSelect
                    label={t("common.category")}
                    value={selectedCategory}
                    onChange={(e) => setSelectedCategory(e.target.value)}
                    data={[
                      { value: "", label: t("common.all") },
                      ...availableCategories.map((category) => ({ value: category, label: category })),
                    ]}
                  />
                </Grid.Col>
              </Grid>

              <Group justify="space-between" gap="sm" className="overview-filter-actions">
                <Group gap="xs" className="overview-quick-filters">
                  <Button type="button" variant="light" color="gray" radius="md" onClick={() => applyDatePreset("week")}>
                    {t("analytics.last7Days")}
                  </Button>
                  <Button type="button" variant="light" color="gray" radius="md" onClick={() => applyDatePreset("30d")}>
                    {t("analytics.last30Days")}
                  </Button>
                  <Button type="button" variant="light" color="gray" radius="md" onClick={() => applyDatePreset("3m")}>
                    {t("analytics.last3Months")}
                  </Button>
                  <Button type="button" variant="light" color="gray" radius="md" onClick={() => applyDatePreset("6m")}>
                    {t("analytics.last6Months")}
                  </Button>
                </Group>

                <Button variant="outline" color="gray" radius="md" onClick={clearFilters}>
                  {t("common.clearFilters")}
                </Button>
              </Group>
            </Stack>
          </Card>

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
            <OverviewStatCard
              tone="income"
              label={t("analytics.totalIncome")}
              value={formatMoney(summary.total_income)}
              icon={IconTrendingUp}
            />
            <OverviewStatCard
              tone="expense"
              label={t("analytics.totalExpenses")}
              value={formatMoney(summary.total_expenses)}
              icon={IconTrendingDown}
            />
            <OverviewStatCard
              tone="balance"
              label={t("common.balance")}
              value={formatMoney(summary.balance)}
              icon={IconWallet}
            />
            <OverviewStatCard
              tone="category"
              label={t("analytics.topExpenseCategory")}
              value={topExpenseCategoryValue}
              icon={IconTag}
            />
          </SimpleGrid>

          <Card className="dashboard-card spending-pattern-card overview-section-card" radius="xl" p={{ base: "md", md: "lg" }}>
            <Stack gap="lg">
              <Group justify="space-between" align="flex-start" gap="md">
                <Box>
                  <Title order={2} size="h3">{t("analytics.spendingPulse")}</Title>
                  <Text size="sm" c="dimmed">{t("analytics.spendingPulseDetail")}</Text>
                </Box>
                <Badge
                  className={`pattern-status-pill pattern-status-${spendingPatternPulse.tone}`}
                  color={spendingPatternPulse.tone === "warning" ? "red" : spendingPatternPulse.tone === "positive" ? "teal" : "blue"}
                  variant="light"
                  radius="sm"
                >
                  {spendingPatternPulse.status}
                </Badge>
              </Group>

              <Text className="pattern-narrative">{spendingPatternPulse.narrative}</Text>

              <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
                <InsightCard
                  tone="neutral"
                  label={t("analytics.last7DaysShort")}
                  value={formatMoney(spendingPatternPulse.lastSevenTotal)}
                  detail={t("analytics.dayAveragePace", {
                    amount: formatMoney(spendingPatternPulse.lastSevenDailyAverage),
                    change: formatPercentChange(spendingPatternPulse.sevenVsThirtyChange, t),
                  })}
                />
                <InsightCard
                  tone="neutral"
                  label={t("analytics.last30DaysShort")}
                  value={formatMoney(spendingPatternPulse.lastThirtyTotal)}
                  detail={t("analytics.last30Comparison", {
                    change: formatPercentChange(spendingPatternPulse.thirtyVsThreeChange, t),
                  })}
                />
                <InsightCard
                  tone="accent"
                  label={t("analytics.threeVsSix")}
                  value={formatPercentChange(spendingPatternPulse.threeVsSixChange, t)}
                  detail={t("analytics.threeSixComparison", {
                    three: formatMoney(spendingPatternPulse.lastThreeAverage),
                    six: formatMoney(spendingPatternPulse.lastSixAverage),
                  })}
                />
              </SimpleGrid>

              {!spendingPatternPulse.hasData ? (
                <Paper className="empty-state" radius="lg" p="md">
                  <Text>{t("analytics.noExpensePattern")}</Text>
                </Paper>
              ) : (
                <Box className="overview-chart-frame">
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
                </Box>
              )}
            </Stack>
          </Card>

          {normalizedAccountId === undefined && accountComparison.length > 1 && (
            <Card className="dashboard-card account-comparison-card overview-section-card" radius="xl" p={{ base: "md", md: "lg" }}>
              <Stack gap="md">
                <Box>
                  <Title order={2} size="h3">{t("analytics.accountsGlance")}</Title>
                  <Text size="sm" c="dimmed">{t("analytics.accountsGlanceDetail")}</Text>
                </Box>

                <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
                  {accountComparison.map((account, index) => (
                    <Paper
                      key={`account-comparison-${account.account_id}`}
                      className={`account-comparison-item ${index === 0 ? "account-comparison-leading" : ""}`}
                      radius="lg"
                      p="md"
                    >
                      <Stack gap="md">
                        <Group justify="space-between" align="flex-start" gap="sm">
                          <Box>
                            <Title order={3} size="h4">{formatAccountName(account.name, t)}</Title>
                            <Text size="sm" c="dimmed">{formatAccountType(account.type, t)}</Text>
                          </Box>
                          {index === 0 && (
                            <Badge color="teal" variant="light" radius="sm">
                              {t("analytics.highestSpend")}
                            </Badge>
                          )}
                        </Group>

                        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                          <Box>
                            <Text className="overview-micro-label">{t("common.income")}</Text>
                            <Text className="overview-micro-value">{formatMoney(account.total_income)}</Text>
                          </Box>
                          <Box>
                            <Text className="overview-micro-label">{t("common.expenses")}</Text>
                            <Text className="overview-micro-value">{formatMoney(account.total_expenses)}</Text>
                          </Box>
                          <Box>
                            <Text className="overview-micro-label">{t("common.balance")}</Text>
                            <Text className="overview-micro-value">{formatMoney(account.balance)}</Text>
                          </Box>
                        </SimpleGrid>

                        <Text size="sm" c="dimmed">
                          {account.top_category
                            ? `${t("analytics.topCategory")}: ${formatCategoryName(account.top_category, t)} (${formatMoney(account.top_category_amount)})`
                            : t("analytics.noCategorySpending")}
                        </Text>
                      </Stack>
                    </Paper>
                  ))}
                </SimpleGrid>
              </Stack>
            </Card>
          )}

          <Card
            ref={alertsRef}
            className={`dashboard-card alerts-card overview-section-card ${getSectionHighlightClass("alerts")}`}
            radius="xl"
            p={{ base: "md", md: "lg" }}
          >
            <Stack gap="md">
              <Box>
                <Title order={2} size="h3">{t("analytics.overspendingAlerts")}</Title>
                <Text size="sm" c="dimmed">{t("analytics.overspendingAlertsDetail")}</Text>
              </Box>

              {!overspendingAlerts || overspendingAlertItems.length === 0 ? (
                <Paper className="empty-state" radius="lg" p="md">
                  <Text>{t("analytics.noAlerts")}</Text>
                </Paper>
              ) : (
                <Stack gap="sm">
                  {overspendingAlertItems.map((alert, index) => (
                    <Paper
                      key={`alert-${index}`}
                      className={`alert-box alert-box-pro alert-${alert.level}`}
                      radius="lg"
                      p="md"
                    >
                      <Stack gap="sm">
                        <Group justify="space-between" align="flex-start" gap="sm">
                          <Box>
                            <Badge color={alert.level === "high" ? "red" : "orange"} variant="light" radius="sm">
                              {t("analytics.reviewSignal")}
                            </Badge>
                            <Title className="alert-title-text" order={3} size="h4">
                              {sentenceCaseText(alert.title)}
                            </Title>
                          </Box>
                          <Button variant="light" color="red" size="xs" radius="md" onClick={() => navigate("/transactions")}>
                            {t("analytics.reviewTransactions")}
                          </Button>
                        </Group>
                        <Text size="sm">{sentenceCaseText(alert.message)}</Text>
                      </Stack>
                    </Paper>
                  ))}
                </Stack>
              )}
            </Stack>
          </Card>

          <Grid
            ref={monthlyRef}
            className={`overview-chart-grid ${getSectionHighlightClass("monthly")}`}
            gutter="md"
          >
            <Grid.Col span={{ base: 12, lg: 7 }}>
              <Card className="dashboard-card overview-section-card" radius="xl" p={{ base: "md", md: "lg" }} h="100%">
                <Stack gap="md">
                  <Box>
                    <Title order={2} size="h3">{t("analytics.monthlySummary")}</Title>
                    <Text size="sm" c="dimmed">{t("analytics.monthlySummaryDetail")}</Text>
                  </Box>

            {monthlySummary.length === 0 ? (
              <Paper className="empty-state" radius="lg" p="md">
                <Text>{t("analytics.noMonthlyData")}</Text>
              </Paper>
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
              <Box className="analytics-top-pie">
                <Box className="compact-section-header">
                  <Title order={3} size="h4">{t("analytics.topFivePieTitle")}</Title>
                  <Text size="sm" c="dimmed">{t("analytics.topFivePieDetail")}</Text>
                </Box>
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
              </Box>
            )}
                </Stack>
              </Card>
            </Grid.Col>

            <Grid.Col span={{ base: 12, lg: 5 }}>
              <Card className="dashboard-card overview-section-card" radius="xl" p={{ base: "md", md: "lg" }} h="100%">
                <Stack gap="md">
                  <Box>
                    <Title order={2} size="h3">{t("analytics.categoryChartTitle")}</Title>
                    <Text size="sm" c="dimmed">{t("analytics.categoryChartDetail")}</Text>
                  </Box>

            {categoryChartData.length === 0 ? (
              <Paper className="empty-state" radius="lg" p="md">
                <Text>{t("dashboard.noExpenseCategories")}</Text>
              </Paper>
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
                </Stack>
              </Card>
            </Grid.Col>
          </Grid>

          <Card
            ref={categoriesRef}
            className={`dashboard-card overview-section-card ${getSectionHighlightClass("categories")}`}
            radius="xl"
            p={{ base: "md", md: "lg" }}
          >
            <Stack gap="md">
              <Box>
                <Title order={2} size="h3">{t("dashboard.expenseCategoriesTitle")}</Title>
                <Text size="sm" c="dimmed">{t("analytics.expenseCategoriesDetail")}</Text>
              </Box>

              {mergedCategoryBreakdown.length === 0 ? (
                <Paper className="empty-state" radius="lg" p="md">
                  <Text>{t("dashboard.noExpenseCategories")}</Text>
                </Paper>
              ) : (
                <Box className="overview-table-scroll">
                  <Table className="overview-category-table" verticalSpacing="sm">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t("common.category")}</Table.Th>
                        <Table.Th ta="right">{t("common.amount")}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {mergedCategoryBreakdown.map((item) => (
                        <Table.Tr key={item.category}>
                          <Table.Td>
                            <button
                              type="button"
                              className="overview-category-link"
                              onClick={() => handleCategoryDrilldown(item.category)}
                            >
                              {formatCategoryName(item.category, t)}
                            </button>
                          </Table.Td>
                          <Table.Td ta="right">
                            <Text fw={800}>{formatMoney(item.total)}</Text>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Box>
              )}
            </Stack>
          </Card>
        </Stack>
      </Container>
    </Box>
  );
}

export default AnalyticsPage;
