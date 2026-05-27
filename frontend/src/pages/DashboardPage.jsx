import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import PageHeader from "../components/PageHeader";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId, setSelectedAccountId as persistSelectedAccountId } from "../services/accountStorage";
import { buildBudgetForecastSummary } from "../utils/budgetDisplay";
import { useLanguage } from "../i18n/LanguageContext";
import { formatAccountLabel, formatCategoryLabel } from "../utils/displayLabels";
import { getApiErrorMessage } from "../utils/errorUtils";

const normalizeRepeatDescription = (value = "") => {
  let normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  normalized = normalized.replace(
    /\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b/g,
    " "
  );
  normalized = normalized.replace(/\b\d+\b/g, " ");
  return normalized.replace(/\s+/g, " ").trim();
};

const buildManualRepeatNotice = (savedTransaction, existingTransactions, t) => {
  const repeatKey = normalizeRepeatDescription(savedTransaction?.description || "");
  if (!repeatKey) return "";

  const matches = existingTransactions.filter((transaction) => {
    if (transaction.id === savedTransaction.id) return false;
    return (
      transaction.type === savedTransaction.type &&
      normalizeRepeatDescription(transaction.description) === repeatKey
    );
  });

  if (matches.length === 0) return "";

  const amounts = [...matches.map((item) => Number(item.amount || 0)), Number(savedTransaction.amount || 0)];
  const averageAmount = amounts.reduce((total, value) => total + value, 0) / amounts.length;
  const label = savedTransaction.type === "income" ? t("common.income").toLowerCase() : t("common.expense").toLowerCase();

  return t("dashboard.repeatNotice", {
    type: label,
    count: matches.length + 1,
    amount: averageAmount.toFixed(2),
  });
};

const formatMonthLabel = (monthValue) => {
  const parsed = new Date(`${monthValue}-01T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return monthValue;
  return parsed.toLocaleDateString(undefined, { month: "long", year: "numeric" });
};

function DashboardPage() {
  const { t } = useLanguage();
  const [dashboardData, setDashboardData] = useState(null);
  const [allTransactions, setAllTransactions] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [budgetData, setBudgetData] = useState(null);
  const [simulatorData, setSimulatorData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [scopeNotice, setScopeNotice] = useState("");

  const [typeFilter, setTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");

  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("Other");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [transactionAccountId, setTransactionAccountId] = useState("");
  const [transactionType, setTransactionType] = useState("expense");
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [suggestion, setSuggestion] = useState(null);
  const [suggestingCategory, setSuggestingCategory] = useState(false);

  const navigate = useNavigate();

  const currentBudgetMonth = new Date().toISOString().slice(0, 7);
  const currentMonthLabel = formatMonthLabel(currentBudgetMonth);

  const fetchData = useCallback(async () => {
    try {
      const accountsRes = await api.get("/accounts/");
      const loadedAccounts = accountsRes.data || [];
      setAccounts(loadedAccounts);

      const selectedAccountExists = loadedAccounts.some(
        (account) => String(account.id) === String(selectedAccountId)
      );
      const repairedAccountId =
        selectedAccountId !== ALL_ACCOUNTS_VALUE && !selectedAccountExists
          ? ALL_ACCOUNTS_VALUE
          : selectedAccountId;
      const scopedAccountId =
        repairedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(repairedAccountId);

      if (repairedAccountId !== selectedAccountId) {
        persistSelectedAccountId(repairedAccountId);
        setSelectedAccountId(repairedAccountId);
      }

      if (loadedAccounts.length > 0) {
        setTransactionAccountId((currentValue) => {
          const currentStillExists = loadedAccounts.some(
            (account) => String(account.id) === String(currentValue)
          );
          if (currentStillExists) {
            return currentValue;
          }

          if (scopedAccountId) {
            return String(scopedAccountId);
          }

          return String(loadedAccounts[0].id);
        });
      }

      let [dashboardRes, transactionsRes, budgetsRes, simulatorRes] = await Promise.all([
        api.get("/analytics/dashboard", {
          params: {
            account_id: scopedAccountId,
            month: currentBudgetMonth,
          },
        }),
        api.get("/transactions/", {
          params: {
            account_id: scopedAccountId,
          },
        }),
        api.get("/budgets/", {
          params: {
            month: currentBudgetMonth,
            account_id: scopedAccountId,
          },
        }),
        api
          .get("/analytics/future-simulator", {
            params: {
              account_id: scopedAccountId,
              months: 3,
            },
          })
          .catch(() => null),
      ]);

      if (scopedAccountId && (transactionsRes.data || []).length === 0) {
        const allTransactionsRes = await api.get("/transactions/");

        if ((allTransactionsRes.data || []).length > 0) {
          const [allDashboardRes, allBudgetsRes, allSimulatorRes] = await Promise.all([
            api.get("/analytics/dashboard", {
              params: {
                month: currentBudgetMonth,
              },
            }),
            api.get("/budgets/", {
              params: {
                month: currentBudgetMonth,
              },
            }),
            api
              .get("/analytics/future-simulator", {
                params: {
                  months: 3,
                },
              })
              .catch(() => null),
          ]);

          dashboardRes = allDashboardRes;
          transactionsRes = allTransactionsRes;
          budgetsRes = allBudgetsRes;
          simulatorRes = allSimulatorRes;
          persistSelectedAccountId(ALL_ACCOUNTS_VALUE);
          setSelectedAccountId(ALL_ACCOUNTS_VALUE);
          setScopeNotice(t("transactions.switchedAllAccountsNotice"));
        } else {
          setScopeNotice("");
        }
      } else {
        setScopeNotice("");
      }

      setDashboardData(dashboardRes.data);
      setAllTransactions(transactionsRes.data);
      setBudgetData(budgetsRes.data);
      setSimulatorData(simulatorRes?.data || null);
    } catch (error) {
      console.error("Failed to load dashboard:", error);
      handleApiAuthError(error, navigate);
    } finally {
      setLoading(false);
    }
  }, [currentBudgetMonth, navigate, selectedAccountId, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!accounts.length) {
      setTransactionAccountId("");
      return;
    }

    if (selectedAccountId !== ALL_ACCOUNTS_VALUE) {
      const scopedAccountId = String(selectedAccountId);
      if (accounts.some((account) => String(account.id) === scopedAccountId)) {
        setTransactionAccountId(scopedAccountId);
        return;
      }
    }

    setTransactionAccountId((currentValue) => {
      if (currentValue && accounts.some((account) => String(account.id) === String(currentValue))) {
        return currentValue;
      }
      return String(accounts[0].id);
    });
  }, [accounts, selectedAccountId]);

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
  const budgetSummary = budgetData?.summary || {
    total_budgeted: 0,
    total_spent: 0,
    total_remaining: 0,
    over_budget_count: 0,
    at_risk_count: 0,
    projected_total_spent: 0,
    projected_total_remaining: 0,
    projected_over_budget_count: 0,
    projected_at_risk_count: 0,
  };
  const hasBudgets = (budgetData?.budgets || []).length > 0;
  const hasTransactions = allTransactions.length > 0;
  const simulatorNarrative = simulatorData
    ? t("dashboard.futureOutlookNarrative", {
        amount: Math.abs(Number(simulatorData.projected_change_amount || 0)).toFixed(2),
        months: simulatorData.months || 3,
        balance: Number(simulatorData.projected_end_balance || 0).toFixed(2),
      })
    : "";

  const suggestCategory = async () => {
    const text = description.trim();

    if (!text) {
      setSuggestion({
        category: "Other",
        confidence: 35,
        reason: t("dashboard.noDescriptionFallback"),
      });
      return;
    }

    setSuggestingCategory(true);
    try {
      const numericAmount = Number(amount);
      const response = await api.post("/transactions/categorize/suggest", {
        description: text,
        type: transactionType,
        ...(Number.isFinite(numericAmount) && numericAmount > 0 ? { amount: numericAmount } : {}),
      });

      const confidenceScore = Number(response.data?.confidence || 0);
      const confidencePercent =
        confidenceScore <= 1 ? Math.round(confidenceScore * 100) : Math.round(confidenceScore);
      const suggestedCategory = response.data?.suggested_category || "other";

      setSuggestion({
        category: suggestedCategory,
        confidence: Math.max(0, Math.min(100, confidencePercent)),
        reason: response.data?.reason || t("dashboard.noRuleFallback"),
      });
      setCategory(suggestedCategory);
    } catch (error) {
      console.error("Failed to suggest category:", error);
      if (!handleApiAuthError(error, navigate)) {
        const fallback = {
          category: "Other",
          confidence: 35,
          reason: t("dashboard.noRuleFallback"),
        };
        setSuggestion(fallback);
        setCategory(fallback.category);
      }
    } finally {
      setSuggestingCategory(false);
    }
  };

  const handleAddTransaction = async (e) => {
    e.preventDefault();
    setFormError("");
    setFormSuccess("");

    if (!transactionAccountId) {
      setFormError(t("dashboard.chooseAccountError"));
      return;
    }

    if (!amount || !description || !date || !transactionType || !category) {
      setFormError(t("dashboard.fillFieldsError"));
      return;
    }

    try {
      setSubmitting(true);

      const response = await api.post("/transactions/", {
        amount: Number(amount),
        category,
        description,
        date,
        type: transactionType,
        account_id: Number(transactionAccountId),
      });
      const savedTransaction = response.data;
      const repeatNotice = buildManualRepeatNotice(savedTransaction, allTransactions, t);

      setAmount("");
      setCategory("Other");
      setDescription("");
      setDate(new Date().toISOString().slice(0, 10));
      setTransactionType("expense");
      setSuggestion(null);
      setFormSuccess(`${t("dashboard.transactionAdded")}${repeatNotice}`);
      setAllTransactions((currentTransactions) => {
        if (currentTransactions.some((transaction) => transaction.id === savedTransaction.id)) {
          return currentTransactions;
        }
        return [savedTransaction, ...currentTransactions];
      });

      await fetchData();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setFormError(getApiErrorMessage(error, t("dashboard.addTransactionFailed")));
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>{t("dashboard.loadingTitle")}</h2>
            <p>{t("dashboard.loadingDetail")}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <PageHeader
          icon="$"
          titleKey="common.dashboard"
          subtitleKey="headers.dashboardSubtitle"
          actions={(
            <button
              className="logout-button"
              onClick={async () => {
                await api.post("/auth/logout").catch(() => {});
                navigate("/", { replace: true });
              }}
            >
              {t("common.logout")}
            </button>
          )}
        />

        <div className="dashboard-card product-guide-card">
          <div className="section-header">
            <h2>{t("dashboard.howTitle")}</h2>
            <p>{t("dashboard.howDetail")}</p>
          </div>

          <div className="feature-guide-grid">
            <div className="feature-guide-item">
              <span className="feature-step">1</span>
              <h3>{t("dashboard.chooseViewTitle")}</h3>
              <p>{t("dashboard.chooseViewDetail")}</p>
            </div>

            <div className="feature-guide-item">
              <span className="feature-step">2</span>
              <h3>{t("dashboard.writeDailyTitle")}</h3>
              <p>{t("dashboard.writeDailyDetail")}</p>
            </div>

            <div className="feature-guide-item">
              <span className="feature-step">3</span>
              <h3>{t("dashboard.watchMonthTitle")}</h3>
              <p>{t("dashboard.watchMonthDetail")}</p>
            </div>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>{t("dashboard.accountView")}</h2>
            <p>{t("dashboard.accountViewDetail")}</p>
          </div>
          <AccountSelector value={selectedAccountId} onChange={setSelectedAccountId} allowAll={true} />
          {scopeNotice && <div className="bulk-message-box">{scopeNotice}</div>}
        </div>

        {!hasTransactions && (
          <div className="dashboard-card money-map-command-card">
            <div className="money-map-command-top">
              <div>
                <span className="money-map-confidence-pill money-map-confidence-low">
                  {t("dashboard.dayZero")}
                </span>
                <h2>{t("dashboard.moneyMapTitle")}</h2>
                <p>{t("dashboard.moneyMapDetail")}</p>
              </div>
            </div>
            <div className="budget-section-actions">
              <button className="secondary-button" onClick={() => navigate("/import")}>
                {t("common.uploadStatement")}
              </button>
              <button className="secondary-button" onClick={() => navigate("/money-map")}>
                {t("dashboard.openMoneyMap")}
              </button>
            </div>
          </div>
        )}

        <div className="dashboard-card">
          <div className="section-header">
            <h2>{currentMonthLabel} {t("dashboard.overview")}</h2>
            <p>{t("dashboard.overviewDetail")}</p>
          </div>

          <div className="summary-grid">
            <div className="summary-card income-card">
              <span className="card-label">{t("common.income")}</span>
              <div className="summary-card-content">
                <p>${summary.total_income.toFixed(2)}</p>
                <small className="summary-card-note">{t("dashboard.incomeNote")}</small>
              </div>
            </div>

            <div className="summary-card expense-card">
              <span className="card-label">{t("common.expenses")}</span>
              <div className="summary-card-content">
                <p>${summary.total_expenses.toFixed(2)}</p>
                <small className="summary-card-note">{t("dashboard.expenseNote")}</small>
              </div>
            </div>

            <div className="summary-card balance-card">
              <span className="card-label">{t("common.balance")}</span>
              <div className="summary-card-content">
                <p>${summary.balance.toFixed(2)}</p>
                <small className="summary-card-note">{t("dashboard.balanceNote")}</small>
              </div>
            </div>
          </div>
          <div className="budget-section-actions">
            <button className="secondary-button" onClick={() => navigate("/analytics")}>
              {t("dashboard.openDetailedAnalytics")}
            </button>
          </div>
        </div>

        {simulatorData && (
          <div className="dashboard-card">
            <div className="section-header">
              <h2>{t("dashboard.futureOutlook")}</h2>
              <p>{t("dashboard.futureOutlookDetail")}</p>
            </div>

            <div className="summary-grid">
              <div className="summary-card balance-card">
                <span className="card-label">{t("dashboard.startingBalance")}</span>
                <p>${simulatorData.starting_balance.toFixed(2)}</p>
              </div>

              <div className="summary-card income-card">
                <span className="card-label">{t("dashboard.monthlyNet")}</span>
                <p>${simulatorData.monthly_net_change.toFixed(2)}</p>
              </div>

              <div className="summary-card top-card">
                <span className="card-label">{t("dashboard.threeMonthImpact")}</span>
                <p>${simulatorData.projected_change_amount.toFixed(2)}</p>
              </div>

              <div className="summary-card expense-card">
                <span className="card-label">{t("dashboard.projectedBalance")}</span>
                <p>${simulatorData.projected_end_balance.toFixed(2)}</p>
              </div>
            </div>

            <p className="budget-forecast-banner">{simulatorNarrative}</p>

            <div className="budget-section-actions">
              <button
                className="secondary-button"
                onClick={() => navigate("/simulator")}
              >
                {t("dashboard.openFullSimulator")}
              </button>
            </div>
          </div>
        )}

        <div className="dashboard-card premium-promo-card">
          <div>
            <p className="eyebrow-text">{t("dashboard.premiumEyebrow")}</p>
            <h2>{t("dashboard.premiumTitle")}</h2>
            <p>{t("dashboard.premiumDetail")}</p>
          </div>
          <div className="premium-feature-grid">
            <span>{t("dashboard.statementBatch")}</span>
            <span>{t("dashboard.trendPacks")}</span>
            <span>{t("dashboard.simulatorScenarios")}</span>
            <span>{t("dashboard.categoryControls")}</span>
          </div>
          <div className="budget-section-actions">
            <button className="premium-header-button" onClick={() => navigate("/profile#plans")}>
              {t("dashboard.seePlans")}
            </button>
            <button className="secondary-button" onClick={() => navigate("/simulator")}>
              {t("dashboard.previewSimulator")}
            </button>
          </div>
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <h2>{t("dashboard.budgetHealth")}</h2>
            <p>{t("dashboard.budgetHealthDetail", { month: currentBudgetMonth })}</p>
          </div>

          {!hasBudgets ? (
            <div className="empty-state">
              <p>{t("dashboard.noBudgets")}</p>
              <button
                className="secondary-button"
                onClick={() => navigate(`/budgets?month=${currentBudgetMonth}`)}
              >
                {t("dashboard.createBudgets")}
              </button>
            </div>
          ) : (
            <>
              <div className="summary-grid">
                <div className="summary-card income-card">
                  <span className="card-label">{t("dashboard.budgeted")}</span>
                  <p>${budgetSummary.total_budgeted.toFixed(2)}</p>
                </div>

                <div className="summary-card expense-card">
                  <span className="card-label">{t("dashboard.spent")}</span>
                  <p>${budgetSummary.total_spent.toFixed(2)}</p>
                </div>

                <div className="summary-card balance-card">
                  <span className="card-label">{t("dashboard.remaining")}</span>
                  <p>${budgetSummary.total_remaining.toFixed(2)}</p>
                </div>

                <div className="summary-card top-card">
                  <span className="card-label">{t("dashboard.watchlist")}</span>
                  <p>
                    {t("dashboard.overAtRisk", {
                      over: budgetSummary.over_budget_count,
                      risk: budgetSummary.at_risk_count,
                    })}
                  </p>
                </div>
              </div>

              <p className="budget-forecast-banner">{buildBudgetForecastSummary(budgetSummary, t)}</p>
            </>
          )}
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>{t("dashboard.addTransactionTitle")}</h2>
            <p>{t("dashboard.addTransactionDetail")}</p>
          </div>

          <p className="budget-inline-note">
            {selectedAccountId === ALL_ACCOUNTS_VALUE
              ? t("dashboard.addFormAllAccounts")
              : t("dashboard.addFormSelectedAccount")}
          </p>

          <form className="transaction-form" onSubmit={handleAddTransaction}>
            <input
              type="number"
              step="0.01"
              placeholder={t("common.amount")}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <input
              type="text"
              placeholder={t("common.category")}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
            <input
              type="text"
              placeholder={t("common.description")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            <select
              value={transactionAccountId}
              onChange={(e) => setTransactionAccountId(e.target.value)}
              disabled={accounts.length === 0}
            >
              <option value="" disabled>
                {accounts.length === 0 ? t("common.loadingAccounts") : t("common.selectAccount")}
              </option>
              {accounts.map((account) => (
                <option key={account.id} value={String(account.id)}>
                  {formatAccountLabel(account, t)}
                </option>
              ))}
            </select>
            <select value={transactionType} onChange={(e) => setTransactionType(e.target.value)}>
              <option value="expense">{t("common.expense")}</option>
              <option value="income">{t("common.income")}</option>
            </select>

            <button type="button" className="suggest-button" onClick={suggestCategory} disabled={suggestingCategory}>
              {suggestingCategory ? t("transactionForm.suggesting") : t("transactionForm.suggestCategory")}
            </button>

            <button type="submit" disabled={submitting || accounts.length === 0}>
              {accounts.length === 0
                ? t("dashboard.loadingAccountsAction")
                : submitting
                ? t("dashboard.adding")
                : t("transactionForm.add")}
            </button>
          </form>

          {formError && <p className="error-text">{formError}</p>}
          {formSuccess && <p className="success-text">{formSuccess}</p>}

          {suggestion && (
            <div className="suggestion-box">
              <h3>{t("transactionForm.suggestedCategory")}</h3>
              <p>
                <strong>{formatCategoryLabel(suggestion.category, t)}</strong>
              </p>
              <p>{t("common.confidence")}: {suggestion.confidence}%</p>
              <p>{suggestion.reason}</p>
            </div>
          )}
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>{t("dashboard.recentFiltersTitle")}</h2>
            <p>{t("dashboard.recentFiltersDetail")}</p>
          </div>

          <div className="filter-bar">
            <div>
              <label>{t("common.type")}</label>
              <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <option value="">{t("common.all")}</option>
                <option value="income">{t("common.income")}</option>
                <option value="expense">{t("common.expense")}</option>
              </select>
            </div>

            <div>
              <label>{t("common.month")}</label>
              <select value={monthFilter} onChange={(e) => setMonthFilter(e.target.value)}>
                <option value="">{t("common.all")}</option>
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
              <h2>{t("dashboard.recentTransactionsTitle")}</h2>
              <p>{t("dashboard.recentTransactionsDetail")}</p>
            </div>

            {filteredRecentTransactions.length === 0 ? (
              <div className="empty-state">
                <p>{t("dashboard.noRecentTransactions")}</p>
              </div>
            ) : (
              <div className="transaction-list">
                {filteredRecentTransactions.map((transaction) => (
                  <div key={transaction.id} className="transaction-item">
                    <div>
                      <strong>{transaction.description}</strong>
                      <p>
                        {formatCategoryLabel(transaction.category, t)} | {transaction.type === "income" ? t("common.income").toLowerCase() : t("common.expense").toLowerCase()} | {transaction.date}
                      </p>
                    </div>
                    <div className="transaction-right">
                      <strong
                        className={
                          transaction.type === "income" ? "income-text" : "expense-text"
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
              <h2>{t("dashboard.expenseCategoriesTitle")}</h2>
              <p>{t("dashboard.expenseCategoriesDetail")}</p>
            </div>

            {topCategories.length === 0 ? (
              <div className="empty-state">
                <p>{t("dashboard.noExpenseCategories")}</p>
              </div>
            ) : (
              <div className="category-list">
                {topCategories.map((item) => (
                  <div key={item.category} className="category-item">
                    <span>{formatCategoryLabel(item.category, t)}</span>
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

