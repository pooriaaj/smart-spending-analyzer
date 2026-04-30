import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId } from "../services/accountStorage";
import {
  buildBudgetForecastSummary,
  buildBudgetPaceLabel,
  buildBudgetProjectionLabel,
} from "../utils/budgetDisplay";

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

function BudgetsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [month, setMonth] = useState(
    searchParams.get("month") || new Date().toISOString().slice(0, 7)
  );
  const [budgetData, setBudgetData] = useState(null);
  const [category, setCategory] = useState(
    formatBudgetCategory(searchParams.get("category") || "")
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
        setError("Failed to load budgets.");
      }
    } finally {
      setLoading(false);
    }
  }, [month, navigate, normalizedAccountId]);

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
      setCategory(formatBudgetCategory(urlCategory));
    }

    if (searchParams.has("amount")) {
      setAmount(urlAmount || "");
    } else if (urlMonth || urlCategory) {
      setAmount("");
    }
  }, [searchParams]);

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
      setMessage("Budget saved.");
      await fetchBudgets();
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setError(saveError?.response?.data?.detail || "Failed to save budget.");
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
      setMessage("Budget deleted.");
      await fetchBudgets();
    } catch (deleteError) {
      if (!handleApiAuthError(deleteError, navigate)) {
        setError(deleteError?.response?.data?.detail || "Failed to delete budget.");
      }
    }
  };

  const scopeDescription =
    normalizedAccountId == null
      ? "These budgets apply across all accounts combined."
      : "These budgets apply only to the selected account.";

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
  const budgetInsights = budgetData?.insights || [];
  const suggestedBudgets = budgetData?.suggestions || [];
  const previousMonth = useMemo(() => shiftMonthLabel(month, -1), [month]);
  const nextMonth = useMemo(() => shiftMonthLabel(month, 1), [month]);
  const categoryOptions = useMemo(
    () => budgetData?.available_categories || [],
    [budgetData]
  );
  const formattedCategoryOptions = useMemo(
    () => categoryOptions.map((item) => formatBudgetCategory(item)),
    [categoryOptions]
  );

  const getBudgetStatusMeta = (status) => {
    if (status === "over_budget") {
      return { label: "Over budget", className: "budget-status budget-status-over" };
    }
    if (status === "at_risk") {
      return { label: "At risk", className: "budget-status budget-status-risk" };
    }
    return { label: "On track", className: "budget-status budget-status-on-track" };
  };

  const getBudgetInsightMeta = (severity) => {
    if (severity === "action") {
      return { label: "Act now", className: "budget-insight-badge budget-insight-badge-action" };
    }
    if (severity === "watch") {
      return { label: "Watch closely", className: "budget-insight-badge budget-insight-badge-watch" };
    }
    return { label: "On pace", className: "budget-insight-badge budget-insight-badge-positive" };
  };

  const handleUseSuggestion = (suggestion) => {
    setCategory(formatBudgetCategory(suggestion.category));
    setAmount(String(suggestion.suggested_amount));
    setMessage(`Loaded ${formatBudgetCategory(suggestion.category)} into the form.`);
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
        `${sourceLabel} saved ${normalizedCategory} at $${Number(targetAmount).toFixed(2)}.`
      );
      await fetchBudgets();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setError(saveError?.response?.data?.detail || "Failed to save budget target.");
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
        response.data?.message ||
          `${sourceLabel} saved ${uniqueTargets.length} budget target${
            uniqueTargets.length === 1 ? "" : "s"
          }.`
      );
      await fetchBudgets();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setError(saveError?.response?.data?.detail || "Failed to apply budget targets.");
      }
    } finally {
      setBulkApplyingKey("");
    }
  };

  const handleUseInsightTarget = (insight) => {
    if (insight.recommended_amount == null) return;

    setCategory(formatBudgetCategory(insight.category));
    setAmount(String(insight.recommended_amount));
    setMessage(
      `Loaded ${formatBudgetCategory(insight.category)} target ${Number(
        insight.recommended_amount
      ).toFixed(2)} into the form.`
    );
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleApplySuggestion = async (suggestion) => {
    await saveBudgetTarget(
      suggestion.category,
      suggestion.suggested_amount,
      "Suggested budget"
    );
  };

  const handleApplyInsightTarget = async (insight) => {
    if (insight.recommended_amount == null) return;

    await saveBudgetTarget(
      insight.category,
      insight.recommended_amount,
      "Budget move"
    );
  };

  const handleApplyAllSuggestions = async () => {
    await saveBudgetTargets(
      suggestedBudgets.map((suggestion) => ({
        category: suggestion.category,
        amount: suggestion.suggested_amount,
      })),
      "Suggested budgets",
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
      "Budget moves",
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
      setMessage(response.data.message || `Copied budgets from ${previousMonth}.`);
      await fetchBudgets();
    } catch (copyError) {
      if (!handleApiAuthError(copyError, navigate)) {
        setError(copyError?.response?.data?.detail || "Failed to copy previous month budgets.");
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
      setMessage(response.data.message || `Built ${nextMonth} budgets from current pace.`);
      setMonth(response.data.target_month || nextMonth);
    } catch (buildError) {
      if (!handleApiAuthError(buildError, navigate)) {
        setError(buildError?.response?.data?.detail || "Failed to build next month budgets.");
      }
    } finally {
      setBuildingNextMonth(false);
    }
  };

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">Smart Spending Analyzer</p>
            <h1>Budgets</h1>
            <p className="hero-subtitle">
              Plan category limits by month and see how your real spending is tracking against them.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              Back to Dashboard
            </button>
            <button className="secondary-button" onClick={() => navigate("/analytics")}>
              View Analytics
            </button>
            <button className="secondary-button" onClick={() => navigate("/money-map")}>
              Money Map
            </button>
            <button className="secondary-button" onClick={() => navigate("/simulator")}>
              Simulator
            </button>
            <button className="secondary-button" onClick={() => navigate("/assistant")}>
              Assistant
            </button>
          </div>
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <h2>Budget Scope</h2>
            <p>{scopeDescription}</p>
          </div>

          <div className="assistant-mode-row">
            <AccountSelector
              value={selectedAccountId}
              label="Budget scope"
              onChange={setSelectedAccountId}
            />

            <div className="assistant-mode-field">
              <label htmlFor="budget-month">Month</label>
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
              Reuse the previous month for a straight rollover, or build {nextMonth} from {month}
              &apos;s live pace when you want smarter targets. Existing budgets in the target month
              stay untouched.
            </p>
            <div className="budget-section-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={handleCopyPreviousMonth}
                disabled={copying || buildingNextMonth}
              >
                {copying ? "Copying..." : `Copy ${previousMonth} Budgets`}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={handleBuildNextMonth}
                disabled={buildingNextMonth || copying}
              >
                {buildingNextMonth ? "Building..." : `Build ${nextMonth} From Pace`}
              </button>
            </div>
          </div>
        </div>

        {suggestedBudgets.length > 0 && (
          <div className="dashboard-card">
            <div className="section-header">
              <div>
                <h2>Suggested Budgets</h2>
                <p>Quick starting points based on your recent spending in this scope.</p>
              </div>
              <div className="budget-section-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={handleApplyAllSuggestions}
                  disabled={bulkApplyingKey === "suggestions"}
                >
                  {bulkApplyingKey === "suggestions" ? "Applying..." : "Apply All Suggestions"}
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
                      <h3>{formatBudgetCategory(suggestion.category)}</h3>
                      <p>Suggested budget ${suggestion.suggested_amount.toFixed(2)}</p>
                    </div>
                  </div>

                  <div className="budget-suggestion-meta">
                    <span>Average spent: ${suggestion.average_spent.toFixed(2)}</span>
                    <span>Current month: ${suggestion.latest_month_spent.toFixed(2)}</span>
                  </div>
                  <p className="budget-inline-note">{suggestion.note}</p>

                  <div className="budget-suggestion-actions">
                    <button
                      type="button"
                      className="secondary-button budget-suggestion-load-button"
                      onClick={() => handleUseSuggestion(suggestion)}
                    >
                      Load Form
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
                        ? "Applying..."
                        : "Save Budget"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="dashboard-card">
          <div className="section-header">
            <h2>Create Or Update Budget</h2>
            <p>Set a monthly spending target for a category. Saving the same category again updates it.</p>
          </div>

          <form className="transaction-form budget-form" onSubmit={handleSaveBudget}>
            <div className="budget-form-field">
              <label htmlFor="budget-category">Category</label>
              <input
                id="budget-category"
                list="budget-category-options"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                placeholder="Groceries"
                required
              />
              <datalist id="budget-category-options">
                {formattedCategoryOptions.map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
            </div>

            <div className="budget-form-field">
              <label htmlFor="budget-amount">Budget amount</label>
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
              {saving ? "Saving..." : "Save Budget"}
            </button>
          </form>

          {message && <p className="success-text">{message}</p>}
          {error && <p className="error-text">{error}</p>}
        </div>

        <div className="summary-grid">
          <div className="summary-card income-card">
            <span className="card-label">Budgeted</span>
            <p>${budgetSummary.total_budgeted.toFixed(2)}</p>
          </div>

          <div className="summary-card expense-card">
            <span className="card-label">Spent</span>
            <p>${budgetSummary.total_spent.toFixed(2)}</p>
          </div>

          <div className="summary-card balance-card">
            <span className="card-label">Remaining</span>
            <p>${budgetSummary.total_remaining.toFixed(2)}</p>
          </div>

          <div className="summary-card top-card">
            <span className="card-label">Watchlist</span>
            <p>{budgetSummary.over_budget_count} over / {budgetSummary.at_risk_count} at risk</p>
          </div>
        </div>

        {budgetCards.length > 0 && (
          <p className="budget-forecast-banner">{buildBudgetForecastSummary(budgetSummary)}</p>
        )}

        {budgetInsights.length > 0 && (
          <div className="dashboard-card">
            <div className="section-header">
              <div>
                <h2>Budget Moves</h2>
                <p>Concrete next steps based on your current pace and month-end forecast.</p>
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
                  {bulkApplyingKey === "insights" ? "Applying..." : "Apply All Targets"}
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
                      <strong>{formatBudgetCategory(insight.category)}</strong>
                    </div>
                    <p className="budget-insight-title">{insight.title}</p>
                    <p className="budget-inline-note">{insight.detail}</p>
                    {insight.recommended_amount != null && (
                      <div className="budget-insight-actions">
                        <span className="budget-inline-note">
                          Suggested target: ${Number(insight.recommended_amount).toFixed(2)}
                        </span>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => handleUseInsightTarget(insight)}
                        >
                          Load Target
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
                            ? "Applying..."
                            : "Apply Target"}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="dashboard-card">
          <div className="section-header">
            <h2>Budget Tracking</h2>
            <p>Watch each category move from safe to at-risk to over budget.</p>
          </div>

          {loading ? (
            <div className="empty-state">
              <p>Loading budgets...</p>
            </div>
          ) : budgetCards.length === 0 ? (
            <div className="empty-state">
              <p>No budgets set for this scope and month yet.</p>
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
                        <h3>{formatBudgetCategory(budget.category)}</h3>
                        <p>
                          Budget ${budget.amount.toFixed(2)} • Spent ${budget.spent_amount.toFixed(2)}
                        </p>
                      </div>

                      <div className="budget-card-actions">
                        <span className={statusMeta.className}>{statusMeta.label}</span>
                        <button
                          className="delete-button"
                          onClick={() => handleDeleteBudget(budget.id)}
                        >
                          Delete
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
                      <span>{budget.usage_percent.toFixed(1)}% used</span>
                      <span>
                        {budget.remaining_amount >= 0
                          ? `$${budget.remaining_amount.toFixed(2)} remaining`
                          : `$${Math.abs(budget.remaining_amount).toFixed(2)} over`}
                      </span>
                    </div>

                    {buildBudgetPaceLabel(budget) && (
                      <p className="budget-pace-metrics">{buildBudgetPaceLabel(budget)}</p>
                    )}
                    {budget.pace_note && <p className="budget-pace-note">{budget.pace_note}</p>}
                    {buildBudgetProjectionLabel(budget) && (
                      <p className="budget-projection-metrics">
                        {buildBudgetProjectionLabel(budget)}
                      </p>
                    )}
                    {budget.projection_note && (
                      <p className="budget-projection-note">{budget.projection_note}</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default BudgetsPage;
