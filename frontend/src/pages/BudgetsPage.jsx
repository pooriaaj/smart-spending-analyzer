import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  IconAlertTriangle,
  IconTarget,
  IconTrendingDown,
  IconWallet,
} from "@tabler/icons-react";
import { Box, Card, Stack, Text, Title } from "@mantine/core";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import PageHeader from "../components/PageHeader";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId } from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import {
  buildBudgetForecastSummary,
  buildBudgetPaceLabel,
  buildBudgetProjectionLabel,
} from "../utils/budgetDisplay";
import { formatCategoryLabel } from "../utils/displayLabels";
import { getApiErrorMessage, getApiSuccessMessage } from "../utils/errorUtils";

function formatBudgetCategory(value) {
  if (!value || typeof value !== "string") return "";

  return value
    .trim()
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function shiftMonthLabel(month, offset) {
  const [yearText, monthText] = (month || "").split("-");
  const year = Number(yearText);
  const monthNumber = Number(monthText);

  if (!year || !monthNumber) return month;

  const totalMonths = year * 12 + (monthNumber - 1) + offset;
  const shiftedYear = Math.floor(totalMonths / 12);
  const shiftedMonth = (totalMonths % 12) + 1;
  return `${shiftedYear.toString().padStart(4, "0")}-${shiftedMonth.toString().padStart(2, "0")}`;
}

function buildQuickSaveKey(category, amount) {
  return `${formatBudgetCategory(category)}-${Number(amount || 0).toFixed(2)}`;
}

function formatBudgetSuggestionNote(suggestion, t) {
  const latestMonthSpent = Number(suggestion?.latest_month_spent || 0);
  const averageSpent = Number(suggestion?.average_spent || 0);

  return latestMonthSpent > averageSpent
    ? t("budgets.suggestionPaceNote")
    : t("budgets.suggestionAverageNote");
}

function formatBudgetInsightTitle(insight, t) {
  const category = formatCategoryLabel(insight?.category, t);

  if (insight?.severity === "action") {
    return t("budgets.insightActionTitle", { category });
  }

  if (insight?.severity === "watch") {
    return t("budgets.insightWatchTitle", { category });
  }

  return t("budgets.insightPositiveTitle", { category });
}

function formatBudgetInsightDetail(insight, t) {
  const recommendedAmount = Number(insight?.recommended_amount || 0).toFixed(2);

  if (insight?.severity === "action") {
    return t("budgets.insightActionDetail", { amount: recommendedAmount });
  }

  if (insight?.severity === "watch") {
    return t("budgets.insightWatchDetail", { amount: recommendedAmount });
  }

  return t("budgets.insightPositiveDetail");
}

function formatBudgetPaceNote(budget, t) {
  if (!budget) return "";

  const remainingAmount = Number(budget.remaining_amount || 0);
  const daysRemaining = Number(budget.days_remaining || 0);

  if (Number(budget.days_elapsed || 0) === 0) {
    return t("budgets.paceNotStartedNote");
  }

  if (daysRemaining <= 0) {
    return remainingAmount >= 0
      ? t("budgets.paceClosedRemainingNote", { amount: remainingAmount.toFixed(2) })
      : t("budgets.paceClosedOverNote", { amount: Math.abs(remainingAmount).toFixed(2) });
  }

  if (remainingAmount < 0) {
    return t("budgets.paceAlreadyOverNote", {
      amount: Math.abs(remainingAmount).toFixed(2),
      days: daysRemaining,
    });
  }

  if (budget.status === "at_risk") {
    return t("budgets.paceAtRiskNote", { days: daysRemaining });
  }

  return t("budgets.paceOnTrackNote", { days: daysRemaining });
}

function formatBudgetProjectionNote(budget, t) {
  if (!budget) return "";

  const projectedRemainingAmount = Number(budget.projected_remaining_amount || 0);
  const projectedUsagePercent = Number(budget.projected_usage_percent || 0);
  const projectedStatus = budget.projected_status || budget.status;

  if (Number(budget.projected_spent_amount || 0) <= 0) {
    return t("budgets.projectionNoSpendNote");
  }

  if (projectedStatus === "over_budget") {
    return t("budgets.projectionOverNote", {
      amount: Math.abs(projectedRemainingAmount).toFixed(2),
    });
  }

  if (projectedStatus === "at_risk") {
    return t("budgets.projectionRiskNote", {
      percent: projectedUsagePercent.toFixed(1),
    });
  }

  return t("budgets.projectionHealthyNote", {
    amount: projectedRemainingAmount.toFixed(2),
  });
}

function BudgetsPage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [searchParams] = useSearchParams();
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [month, setMonth] = useState(
    searchParams.get("month") || new Date().toISOString().slice(0, 7)
  );
  const [budgetData, setBudgetData] = useState(null);
  const [category, setCategory] = useState(
    searchParams.get("category") ? formatCategoryLabel(searchParams.get("category"), t) : ""
  );
  const [amount, setAmount] = useState(searchParams.get("amount") || "");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [copying, setCopying] = useState(false);
  const [buildingNextMonth, setBuildingNextMonth] = useState(false);
  const [quickSavingKey, setQuickSavingKey] = useState("");
  const [bulkApplyingKey, setBulkApplyingKey] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);

  const fetchBudgets = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const response = await api.get("/budgets/", {
        params: {
          month,
          account_id: normalizedAccountId,
        },
      });
      setBudgetData(response.data);
    } catch (fetchError) {
      if (!handleApiAuthError(fetchError, navigate)) {
        setError(t("budgets.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [month, navigate, normalizedAccountId, t]);

  useEffect(() => {
    fetchBudgets();
  }, [fetchBudgets]);

  useEffect(() => {
    const urlMonth = searchParams.get("month");
    const urlCategory = searchParams.get("category");
    const urlAmount = searchParams.get("amount");

    if (urlMonth && /^\d{4}-\d{2}$/.test(urlMonth)) {
      setMonth(urlMonth);
    }

    if (urlCategory) {
      setCategory(formatCategoryLabel(urlCategory, t));
    }

    if (searchParams.has("amount")) {
      setAmount(urlAmount || "");
    } else if (urlMonth || urlCategory) {
      setAmount("");
    }
  }, [searchParams, t]);

  const handleSaveBudget = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");

    try {
      await api.post("/budgets/", {
        month,
        category,
        amount: Number(amount),
        account_id: normalizedAccountId,
      });
      setCategory("");
      setAmount("");
      setMessage(t("budgets.budgetSaved"));
      await fetchBudgets();
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setError(getApiErrorMessage(saveError, t("budgets.saveFailed")));
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteBudget = async (budgetId) => {
    setError("");
    setMessage("");

    try {
      await api.delete(`/budgets/${budgetId}`);
      setMessage(t("budgets.budgetDeleted"));
      await fetchBudgets();
    } catch (deleteError) {
      if (!handleApiAuthError(deleteError, navigate)) {
        setError(getApiErrorMessage(deleteError, t("budgets.deleteFailed")));
      }
    }
  };

  const scopeDescription =
    normalizedAccountId == null
      ? t("budgets.scopeAll")
      : t("budgets.scopeOne");

  const budgetSummary = budgetData?.summary || {
    total_budgeted: 0,
    total_spent: 0,
    total_remaining: 0,
    over_budget_count: 0,
    at_risk_count: 0,
    on_track_count: 0,
    projected_total_spent: 0,
    projected_total_remaining: 0,
    projected_over_budget_count: 0,
    projected_at_risk_count: 0,
    projected_on_track_count: 0,
  };

  const budgetCards = budgetData?.budgets || [];

  const spentPercent =
    budgetSummary.total_budgeted > 0
      ? (budgetSummary.total_spent / budgetSummary.total_budgeted) * 100
      : 0;
  const budgetInsights = budgetData?.insights || [];
  const suggestedBudgets = budgetData?.suggestions || [];
  const previousMonth = useMemo(() => shiftMonthLabel(month, -1), [month]);
  const nextMonth = useMemo(() => shiftMonthLabel(month, 1), [month]);
  const categoryOptions = useMemo(
    () => budgetData?.available_categories || [],
    [budgetData]
  );
  const formattedCategoryOptions = useMemo(
    () => categoryOptions.map((item) => formatCategoryLabel(item, t)),
    [categoryOptions, t]
  );

  const getBudgetStatusMeta = (status) => {
    if (status === "over_budget") {
      return { label: t("budgets.overBudget"), className: "budget-status budget-status-over" };
    }
    if (status === "at_risk") {
      return { label: t("budgets.atRisk"), className: "budget-status budget-status-risk" };
    }
    return { label: t("budgets.onTrack"), className: "budget-status budget-status-on-track" };
  };

  const getBudgetInsightMeta = (severity) => {
    if (severity === "action") {
      return { label: t("budgets.actNow"), className: "budget-insight-badge budget-insight-badge-action" };
    }
    if (severity === "watch") {
      return { label: t("budgets.watchClosely"), className: "budget-insight-badge budget-insight-badge-watch" };
    }
    return { label: t("budgets.onPace"), className: "budget-insight-badge budget-insight-badge-positive" };
  };

  const handleUseSuggestion = (suggestion) => {
    setCategory(formatCategoryLabel(suggestion.category, t));
    setAmount(String(suggestion.suggested_amount));
    setMessage(t("budgets.loadedCategory", { category: formatCategoryLabel(suggestion.category, t) }));
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const saveBudgetTarget = async (targetCategory, targetAmount, sourceLabel) => {
    const normalizedCategory = formatBudgetCategory(targetCategory);
    const quickKey = buildQuickSaveKey(normalizedCategory, targetAmount);

    try {
      setQuickSavingKey(quickKey);
      setError("");
      setMessage("");

      await api.post("/budgets/", {
        month,
        category: normalizedCategory,
        amount: Number(targetAmount),
        account_id: normalizedAccountId,
      });

      setCategory(normalizedCategory);
      setAmount(String(targetAmount));
      setMessage(
        t("budgets.targetSaved", {
          source: sourceLabel,
          category: formatCategoryLabel(normalizedCategory, t),
          amount: Number(targetAmount).toFixed(2),
        })
      );
      await fetchBudgets();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setError(getApiErrorMessage(saveError, t("budgets.targetSaveFailed")));
      }
    } finally {
      setQuickSavingKey("");
    }
  };

  const saveBudgetTargets = async (targets, sourceLabel, bulkKey) => {
    const normalizedTargets = targets
      .map((target) => ({
        category: formatBudgetCategory(target.category),
        amount: Number(target.amount),
      }))
      .filter((target) => target.category && Number.isFinite(target.amount) && target.amount > 0);

    const uniqueTargets = Array.from(
      normalizedTargets.reduce((map, target) => {
        map.set(target.category.toLowerCase(), target);
        return map;
      }, new Map()).values()
    );

    if (uniqueTargets.length === 0) {
      return;
    }

    try {
      setBulkApplyingKey(bulkKey);
      setError("");
      setMessage("");

      const response = await api.post("/budgets/bulk-upsert", {
        month,
        account_id: normalizedAccountId,
        items: uniqueTargets,
      });

      const lastTarget = uniqueTargets[uniqueTargets.length - 1];
      setCategory(lastTarget.category);
      setAmount(String(lastTarget.amount));
      setMessage(
        getApiSuccessMessage(
          response.data,
          t("budgets.targetsSaved", {
            source: sourceLabel,
            count: uniqueTargets.length,
            plural: uniqueTargets.length === 1 ? "" : "s",
          })
        )
      );
      await fetchBudgets();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setError(getApiErrorMessage(saveError, t("budgets.targetsApplyFailed")));
      }
    } finally {
      setBulkApplyingKey("");
    }
  };

  const handleUseInsightTarget = (insight) => {
    if (insight.recommended_amount == null) return;

    setCategory(formatCategoryLabel(insight.category, t));
    setAmount(String(insight.recommended_amount));
    setMessage(
      t("budgets.loadedTarget", {
        category: formatCategoryLabel(insight.category, t),
        amount: Number(insight.recommended_amount).toFixed(2),
      })
    );
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleApplySuggestion = async (suggestion) => {
    await saveBudgetTarget(
      suggestion.category,
      suggestion.suggested_amount,
      t("budgets.suggestedBudgetSource")
    );
  };

  const handleApplyInsightTarget = async (insight) => {
    if (insight.recommended_amount == null) return;

    await saveBudgetTarget(
      insight.category,
      insight.recommended_amount,
      t("budgets.budgetMoveSource")
    );
  };

  const handleApplyAllSuggestions = async () => {
    await saveBudgetTargets(
      suggestedBudgets.map((suggestion) => ({
        category: suggestion.category,
        amount: suggestion.suggested_amount,
      })),
      t("budgets.suggestedBudgetsSource"),
      "suggestions"
    );
  };

  const handleApplyAllInsightTargets = async () => {
    await saveBudgetTargets(
      budgetInsights
        .filter((insight) => insight.recommended_amount != null)
        .map((insight) => ({
          category: insight.category,
          amount: insight.recommended_amount,
        })),
      t("budgets.budgetMovesSource"),
      "insights"
    );
  };

  const handleCopyPreviousMonth = async () => {
    setCopying(true);
    setError("");
    setMessage("");

    try {
      const response = await api.post("/budgets/copy-previous-month", {
        month,
        account_id: normalizedAccountId,
      });
      setMessage(
        getApiSuccessMessage(response.data, t("budgets.copiedBudgets", { month: previousMonth }))
      );
      await fetchBudgets();
    } catch (copyError) {
      if (!handleApiAuthError(copyError, navigate)) {
        setError(getApiErrorMessage(copyError, t("budgets.copyFailed")));
      }
    } finally {
      setCopying(false);
    }
  };

  const handleBuildNextMonth = async () => {
    setBuildingNextMonth(true);
    setError("");
    setMessage("");

    try {
      const response = await api.post("/budgets/build-next-month", {
        month,
        account_id: normalizedAccountId,
      });
      setCategory("");
      setAmount("");
      setMessage(
        getApiSuccessMessage(response.data, t("budgets.builtBudgets", { month: nextMonth }))
      );
      setMonth(response.data.target_month || nextMonth);
    } catch (buildError) {
      if (!handleApiAuthError(buildError, navigate)) {
        setError(getApiErrorMessage(buildError, t("budgets.buildFailed")));
      }
    } finally {
      setBuildingNextMonth(false);
    }
  };

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <PageHeader
          icon={IconTarget}
          titleKey="common.budgets"
          subtitleKey="headers.budgetsSubtitle"
        />

        <Card className="filter-card" radius="xl" p={{ base: "md", md: "lg" }}>
          <Stack gap="md">
            <Box>
              <Title order={2} size="h3">{t("budgets.scopeTitle")}</Title>
              <Text size="sm" c="dimmed">{scopeDescription}</Text>
            </Box>

          <div className="assistant-mode-row">
            <AccountSelector
              value={selectedAccountId}
              label={t("budgets.scopeLabel")}
              onChange={setSelectedAccountId}
            />

            <div className="assistant-mode-field">
              <label htmlFor="budget-month">{t("common.month")}</label>
              <input
                id="budget-month"
                type="month"
                value={month}
                onChange={(event) => setMonth(event.target.value)}
              />
            </div>
          </div>

          <div className="budget-scope-actions">
            <p className="budget-inline-note">
              {t("budgets.rolloverNote", { nextMonth, month })}
            </p>
            <div className="budget-section-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={handleCopyPreviousMonth}
                disabled={copying || buildingNextMonth}
              >
                {copying
                  ? t("budgets.copying")
                  : t("budgets.copyBudgets", { month: previousMonth })}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={handleBuildNextMonth}
                disabled={buildingNextMonth || copying}
              >
                {buildingNextMonth
                  ? t("budgets.building")
                  : t("budgets.buildFromPace", { month: nextMonth })}
              </button>
            </div>
          </div>
          </Stack>
        </Card>

        {suggestedBudgets.length > 0 && (
          <div className="dashboard-card">
            <div className="section-header">
              <div>
                <h2>{t("budgets.suggestedBudgets")}</h2>
                <p>{t("budgets.suggestedBudgetsDetail")}</p>
              </div>
              <div className="budget-section-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={handleApplyAllSuggestions}
                  disabled={bulkApplyingKey === "suggestions"}
                >
                  {bulkApplyingKey === "suggestions"
                    ? t("transactions.applying")
                    : t("budgets.applyAllSuggestions")}
                </button>
              </div>
            </div>

            <div className="budget-suggestion-grid">
              {suggestedBudgets.map((suggestion) => (
                <div
                  key={`${suggestion.category}-${suggestion.suggested_amount}`}
                  className="budget-card budget-suggestion-card"
                >
                  <div className="budget-suggestion-header">
                    <div>
                      <h3>{formatCategoryLabel(suggestion.category, t)}</h3>
                      <p>{t("budgets.suggestedBudget", { amount: suggestion.suggested_amount.toFixed(2) })}</p>
                    </div>
                  </div>

                  <div className="budget-suggestion-meta">
                    <span>{t("budgets.averageSpent", { amount: suggestion.average_spent.toFixed(2) })}</span>
                    <span>{t("budgets.currentMonthSpent", { amount: suggestion.latest_month_spent.toFixed(2) })}</span>
                  </div>
                  <p className="budget-inline-note">{formatBudgetSuggestionNote(suggestion, t)}</p>

                  <div className="budget-suggestion-actions">
                    <button
                      type="button"
                      className="secondary-button budget-suggestion-load-button"
                      onClick={() => handleUseSuggestion(suggestion)}
                    >
                      {t("budgets.loadForm")}
                    </button>
                    <button
                      type="button"
                      className="budget-suggestion-apply-button"
                      onClick={() => handleApplySuggestion(suggestion)}
                      disabled={
                        bulkApplyingKey === "suggestions" ||
                        quickSavingKey ===
                          buildQuickSaveKey(suggestion.category, suggestion.suggested_amount)
                      }
                    >
                      {quickSavingKey === buildQuickSaveKey(suggestion.category, suggestion.suggested_amount)
                        ? t("transactions.applying")
                        : t("budgets.saveBudget")}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <Card className="filter-card" radius="xl" p={{ base: "md", md: "lg" }}>
          <Stack gap="md">
            <Box>
              <Title order={2} size="h3">{t("budgets.createOrUpdate")}</Title>
              <Text size="sm" c="dimmed">{t("budgets.createOrUpdateDetail")}</Text>
            </Box>

          <form className="transaction-form budget-form" onSubmit={handleSaveBudget}>
            <div className="budget-form-field">
              <label htmlFor="budget-category">{t("common.category")}</label>
              <input
                id="budget-category"
                list="budget-category-options"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                placeholder={t("budgets.categoryPlaceholder")}
                required
              />
              <datalist id="budget-category-options">
                {formattedCategoryOptions.map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
            </div>

            <div className="budget-form-field">
              <label htmlFor="budget-amount">{t("budgets.budgetAmount")}</label>
              <input
                id="budget-amount"
                type="number"
                min="0.01"
                step="0.01"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder="400"
                required
              />
            </div>

            <button type="submit" disabled={saving}>
              {saving ? t("common.saving") : t("budgets.saveBudget")}
            </button>
          </form>

          {message && <p className="success-text">{message}</p>}
          {error && <p className="error-text">{error}</p>}
          </Stack>
        </Card>

        <div className="summary-grid">
          <div className="summary-card income-card">
            <div className="budget-kpi-header">
              <span className="card-label">{t("dashboard.budgeted")}</span>
              <span className="budget-kpi-icon budget-kpi-icon-income" aria-hidden="true">
                <IconTarget size={15} stroke={2} />
              </span>
            </div>
            <p>${budgetSummary.total_budgeted.toFixed(2)}</p>
          </div>

          <div className="summary-card expense-card">
            <div className="budget-kpi-header">
              <span className="card-label">{t("dashboard.spent")}</span>
              <span className="budget-kpi-icon budget-kpi-icon-expense" aria-hidden="true">
                <IconTrendingDown size={15} stroke={2} />
              </span>
            </div>
            <div className="budget-kpi-bottom">
              <p>${budgetSummary.total_spent.toFixed(2)}</p>
              <div className="budget-progress-track">
                <div
                  className="budget-progress-fill budget-progress-fill-expense"
                  style={{ width: `${Math.min(100, spentPercent)}%` }}
                />
              </div>
              <span className="budget-kpi-note">{t("budgets.used", { percent: spentPercent.toFixed(0) })}</span>
            </div>
          </div>

          <div className="summary-card balance-card">
            <div className="budget-kpi-header">
              <span className="card-label">{t("dashboard.remaining")}</span>
              <span className="budget-kpi-icon budget-kpi-icon-balance" aria-hidden="true">
                <IconWallet size={15} stroke={2} />
              </span>
            </div>
            <div className="budget-kpi-bottom">
              <p>${budgetSummary.total_remaining.toFixed(2)}</p>
              <div className="budget-progress-track">
                <div
                  className="budget-progress-fill budget-progress-fill-balance"
                  style={{ width: `${Math.max(0, Math.min(100, 100 - spentPercent))}%` }}
                />
              </div>
            </div>
          </div>

          <div className="summary-card top-card">
            <div className="budget-kpi-header">
              <span className="card-label">{t("dashboard.watchlist")}</span>
              <span className="budget-kpi-icon budget-kpi-icon-top" aria-hidden="true">
                <IconAlertTriangle size={15} stroke={2} />
              </span>
            </div>
            <p>
              {t("dashboard.overAtRisk", {
                over: budgetSummary.over_budget_count,
                risk: budgetSummary.at_risk_count,
              })}
            </p>
          </div>
        </div>

        {budgetCards.length > 0 && (
          <p className="budget-forecast-banner">{buildBudgetForecastSummary(budgetSummary, t)}</p>
        )}

        {budgetInsights.length > 0 && (
          <div className="dashboard-card">
            <div className="section-header">
              <div>
                <h2>{t("budgets.budgetMoves")}</h2>
                <p>{t("budgets.budgetMovesDetail")}</p>
              </div>
              <div className="budget-section-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={handleApplyAllInsightTargets}
                  disabled={
                    bulkApplyingKey === "insights" ||
                    !budgetInsights.some((insight) => insight.recommended_amount != null)
                  }
                >
                  {bulkApplyingKey === "insights"
                    ? t("transactions.applying")
                    : t("budgets.applyAllTargets")}
                </button>
              </div>
            </div>

            <div className="budget-insight-list">
              {budgetInsights.map((insight) => {
                const insightMeta = getBudgetInsightMeta(insight.severity);

                return (
                  <div
                    key={`${insight.category}-${insight.title}`}
                    className="budget-insight-item"
                  >
                    <div className="budget-insight-top">
                      <span className={insightMeta.className}>{insightMeta.label}</span>
                      <strong>{formatCategoryLabel(insight.category, t)}</strong>
                    </div>
                    <p className="budget-insight-title">{formatBudgetInsightTitle(insight, t)}</p>
                    <p className="budget-inline-note">{formatBudgetInsightDetail(insight, t)}</p>
                    {insight.recommended_amount != null && (
                      <div className="budget-insight-actions">
                        <span className="budget-inline-note">
                          {t("budgets.suggestedTarget", {
                            amount: Number(insight.recommended_amount).toFixed(2),
                          })}
                        </span>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => handleUseInsightTarget(insight)}
                        >
                          {t("budgets.loadTarget")}
                        </button>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => handleApplyInsightTarget(insight)}
                          disabled={
                            bulkApplyingKey === "insights" ||
                            quickSavingKey ===
                              buildQuickSaveKey(insight.category, insight.recommended_amount)
                          }
                        >
                          {quickSavingKey === buildQuickSaveKey(insight.category, insight.recommended_amount)
                            ? t("transactions.applying")
                            : t("budgets.applyTarget")}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <Card className="filter-card" radius="xl" p={{ base: "md", md: "lg" }}>
          <Stack gap="md">
            <Box>
              <Title order={2} size="h3">{t("budgets.budgetTracking")}</Title>
              <Text size="sm" c="dimmed">{t("budgets.budgetTrackingDetail")}</Text>
            </Box>

          {loading ? (
            <div className="empty-state">
              <p>{t("budgets.loadingBudgets")}</p>
            </div>
          ) : budgetCards.length === 0 ? (
            <div className="empty-state">
              <p>{t("budgets.noBudgetsScope")}</p>
            </div>
          ) : (
            <div className="budget-list">
              {budgetCards.map((budget) => {
                const statusMeta = getBudgetStatusMeta(budget.status);
                const progressWidth = Math.min(budget.usage_percent, 100);

                return (
                  <div key={budget.id} className="budget-card">
                    <div className="budget-card-top">
                      <div>
                        <h3>{formatCategoryLabel(budget.category, t)}</h3>
                        <p>
                          {t("budgets.budgetSpent", {
                            budget: budget.amount.toFixed(2),
                            spent: budget.spent_amount.toFixed(2),
                          })}
                        </p>
                      </div>

                      <div className="budget-card-actions">
                        <span className={statusMeta.className}>{statusMeta.label}</span>
                        <button
                          className="delete-button"
                          onClick={() => handleDeleteBudget(budget.id)}
                        >
                          {t("common.delete")}
                        </button>
                      </div>
                    </div>

                    <div className="budget-progress-track">
                      <div
                        className={`budget-progress-fill budget-progress-${budget.status}`}
                        style={{ width: `${progressWidth}%` }}
                      />
                    </div>

                    <div className="budget-card-meta">
                      <span>{t("budgets.used", { percent: budget.usage_percent.toFixed(1) })}</span>
                      <span>
                        {budget.remaining_amount >= 0
                          ? t("budgets.remainingAmount", {
                              amount: budget.remaining_amount.toFixed(2),
                            })
                          : t("budgets.overAmount", {
                              amount: Math.abs(budget.remaining_amount).toFixed(2),
                            })}
                      </span>
                    </div>

                    {buildBudgetPaceLabel(budget, t) && (
                      <p className="budget-pace-metrics">{buildBudgetPaceLabel(budget, t)}</p>
                    )}
                    <p className="budget-pace-note">{formatBudgetPaceNote(budget, t)}</p>
                    {buildBudgetProjectionLabel(budget, t) && (
                      <p className="budget-projection-metrics">
                        {buildBudgetProjectionLabel(budget, t)}
                      </p>
                    )}
                    <p className="budget-projection-note">{formatBudgetProjectionNote(budget, t)}</p>
                  </div>
                );
              })}
            </div>
          )}
          </Stack>
        </Card>
      </div>
    </div>
  );
}

export default BudgetsPage;
