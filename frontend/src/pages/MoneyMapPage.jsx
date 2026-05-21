import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
  setSelectedAccountId as persistSelectedAccountId,
} from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import {
  formatCategoryLabel,
  formatConfidenceLevel,
  formatRecurringReviewReason,
} from "../utils/displayLabels";

function formatMoney(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function getConfidenceClass(level) {
  if (level === "High") return "money-map-confidence-high";
  if (level === "Medium") return "money-map-confidence-medium";
  return "money-map-confidence-low";
}

const MONEY_MAP_ACTION_KEYS = {
  "Upload a statement": ["actionUploadStatement", "actionUploadStatementDetail"],
  "Add one transaction manually": ["actionAddManual", "actionAddManualDetail"],
  "Review category guesses": ["actionReviewCategories", "actionReviewCategoriesDetail"],
  "Upload more history": ["actionUploadMoreHistory", "actionUploadMoreHistoryDetail"],
  "Simulate recurring cuts": ["actionSimulateRecurringCuts", "actionSimulateRecurringCutsDetail"],
  "Build starter budgets": ["actionBuildBudgets", "actionBuildBudgetsDetail"],
  "Teach merchant groups": ["actionTeachMerchantGroups", "actionTeachMerchantGroupsDetail"],
};

function formatMoneyMapNarrative(moneyMap, t) {
  if (!moneyMap || Number(moneyMap.transaction_count || 0) <= 0) {
    return t("moneyMap.narrativeEmpty");
  }

  const topCategory = (moneyMap.top_categories || [])[0]?.category;
  const recurringCount = (moneyMap.recurring_highlights || []).length;
  const reviewCount = Number(moneyMap.uncategorized_count || 0);
  const transactionCount = Number(moneyMap.transaction_count || 0);

  return t("moneyMap.narrativeReady", {
    level: formatConfidenceLevel(moneyMap.confidence_level, t).toLowerCase(),
    transactions: transactionCount,
    transactionPlural: transactionCount === 1 ? "" : "s",
    months: Number(moneyMap.month_count || 0),
    monthPlural: Number(moneyMap.month_count || 0) === 1 ? "" : "s",
    category: topCategory ? formatCategoryLabel(topCategory, t) : formatCategoryLabel("other", t),
    recurring: recurringCount,
    reviews: reviewCount,
  });
}

function formatMoneyMapAction(action, t) {
  const [labelKey, detailKey] = MONEY_MAP_ACTION_KEYS[action.label] || [];
  return {
    label: labelKey ? t(`moneyMap.${labelKey}`) : action.label,
    detail: detailKey ? t(`moneyMap.${detailKey}`) : action.detail,
  };
}

function formatLearningSignal(signal, moneyMap, t) {
  if (signal.label === "History depth") {
    const monthCount = Number(moneyMap?.month_count || 0);
    return {
      label: t("moneyMap.signalHistoryDepth"),
      value: t("moneyMap.signalHistoryDepthValue", {
        count: monthCount,
        plural: monthCount === 1 ? "" : "s",
      }),
      detail: t("moneyMap.signalHistoryDepthDetail"),
    };
  }

  if (signal.label === "Learned merchants") {
    return {
      label: t("moneyMap.signalLearnedMerchants"),
      value: String(moneyMap?.learned_merchant_count || 0),
      detail: t("moneyMap.signalLearnedMerchantsDetail"),
    };
  }

  if (signal.label === "Category review") {
    return {
      label: t("moneyMap.signalCategoryReview"),
      value: String(moneyMap?.uncategorized_count || 0),
      detail: t("moneyMap.signalCategoryReviewDetail"),
    };
  }

  return signal;
}

function MoneyMapPage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [moneyMap, setMoneyMap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);

  const loadMoneyMap = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const response = await api.get("/analytics/money-map", {
        params: {
          account_id: normalizedAccountId,
        },
      });
      setMoneyMap(response.data);
    } catch (loadError) {
      if (!handleApiAuthError(loadError, navigate)) {
        setError(t("moneyMapMessages.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [navigate, normalizedAccountId, t]);

  useEffect(() => {
    persistSelectedAccountId(String(selectedAccountId || ALL_ACCOUNTS_VALUE));
  }, [selectedAccountId]);

  useEffect(() => {
    loadMoneyMap();
  }, [loadMoneyMap]);

  const topCategoryTotal = useMemo(
    () => (moneyMap?.top_categories || []).reduce((sum, item) => sum + Number(item.total || 0), 0),
    [moneyMap]
  );

  const handleAction = (action) => {
    if (!action?.page) return;
    const routeMap = {
      import: "/import",
      dashboard: "/dashboard",
      transactions: "/transactions",
      budgets: "/budgets",
      simulator: "/simulator",
      analytics: "/analytics",
      assistant: "/assistant",
    };
    navigate(routeMap[action.page] || "/dashboard");
  };

  if (loading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>{t("moneyMap.loadingTitle")}</h2>
            <p>{t("moneyMap.loadingDetail")}</p>
          </div>
        </div>
      </div>
    );
  }

  const summary = moneyMap?.summary || {
    total_income: 0,
    total_expenses: 0,
    balance: 0,
  };
  const isEmpty = moneyMap?.status === "empty";

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero money-map-hero">
          <div>
            <p className="eyebrow-text">{t("headers.moneyMapEyebrow")}</p>
            <h1>{t("common.moneyMap")}</h1>
            <p className="hero-subtitle">
              {t("headers.moneyMapSubtitle")}
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/import")}>
              {t("common.uploadStatement")}
            </button>
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              {t("common.dashboard")}
            </button>
            <button className="secondary-button" onClick={() => navigate("/simulator")}>
              {t("common.simulator")}
            </button>
            <button className="secondary-button" onClick={() => navigate("/assistant")}>
              {t("common.assistant")}
            </button>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>{t("moneyMap.scopeTitle")}</h2>
            <p>{t("moneyMap.scopeDetail")}</p>
          </div>
          <AccountSelector value={selectedAccountId} onChange={setSelectedAccountId} allowAll={true} />
        </div>

        {error && <p className="error-text">{error}</p>}

        <div className="dashboard-card money-map-command-card">
          <div className="money-map-command-top">
            <div>
              <span className={`money-map-confidence-pill ${getConfidenceClass(moneyMap?.confidence_level)}`}>
                {moneyMap?.confidence_level
                  ? t("moneyMap.confidencePill", {
                      level: formatConfidenceLevel(moneyMap.confidence_level, t),
                    })
                  : t("moneyMap.lowConfidence")}
              </span>
              <h2>{isEmpty ? t("moneyMap.startStatement") : t("moneyMap.learnedModel")}</h2>
              <p>{formatMoneyMapNarrative(moneyMap, t)}</p>
            </div>
            <div className="money-map-score-ring">
              <strong>{formatPercent(moneyMap?.confidence_score)}</strong>
              <span>{t("moneyMap.modelConfidence")}</span>
            </div>
          </div>

          <div className="money-map-action-grid">
            {(moneyMap?.actions || []).map((action) => {
              const formattedAction = formatMoneyMapAction(action, t);

              return (
                <button
                  key={`${action.page}-${action.label}`}
                  type="button"
                  className={`money-map-action-card money-map-action-${action.priority}`}
                  onClick={() => handleAction(action)}
                >
                  <strong>{formattedAction.label}</strong>
                  <span>{formattedAction.detail}</span>
                </button>
              );
            })}
          </div>
        </div>

        {isEmpty ? (
          <div className="dashboard-card large-card money-map-empty-card">
            <div>
              <p className="eyebrow-text">{t("moneyMap.dayZero")}</p>
              <h2>{t("moneyMap.dayZeroTitle")}</h2>
              <p>{t("moneyMap.dayZeroDetail")}</p>
            </div>
            <div className="money-map-empty-steps">
              <div>
                <span>1</span>
                <strong>{t("moneyMap.importStatement")}</strong>
                <p>{t("moneyMap.importStatementDetail")}</p>
              </div>
              <div>
                <span>2</span>
                <strong>{t("moneyMap.teachCategories")}</strong>
                <p>{t("moneyMap.teachCategoriesDetail")}</p>
              </div>
              <div>
                <span>3</span>
                <strong>{t("moneyMap.unlockPlanning")}</strong>
                <p>{t("moneyMap.unlockPlanningDetail")}</p>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="summary-grid">
              <div className="summary-card income-card">
                <span className="card-label">{t("common.income")}</span>
                <p>{formatMoney(summary.total_income)}</p>
              </div>
              <div className="summary-card expense-card">
                <span className="card-label">{t("common.expenses")}</span>
                <p>{formatMoney(summary.total_expenses)}</p>
              </div>
              <div className="summary-card balance-card">
                <span className="card-label">{t("common.balance")}</span>
                <p>{formatMoney(summary.balance)}</p>
              </div>
              <div className="summary-card top-card">
                <span className="card-label">{t("moneyMap.learnedMerchants")}</span>
                <p>{moneyMap?.learned_merchant_count || 0}</p>
              </div>
            </div>

            <div className="dashboard-card">
              <div className="section-header">
                <div>
                  <h2>{t("moneyMap.learningSignals")}</h2>
                  <p>{t("moneyMap.learningSignalsDetail")}</p>
                </div>
              </div>
              <div className="money-map-signal-grid">
                {(moneyMap?.learning_signals || []).map((signal) => {
                  const formattedSignal = formatLearningSignal(signal, moneyMap, t);

                  return (
                    <div
                      key={signal.label}
                      className={`money-map-signal-card money-map-signal-${signal.severity}`}
                    >
                      <span>{formattedSignal.label}</span>
                      <strong>{formattedSignal.value}</strong>
                      <p>{formattedSignal.detail}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="chart-grid">
              <div className="dashboard-card large-card">
                <div className="section-header">
                  <h2>{t("moneyMap.topSpendingDrivers")}</h2>
                  <p>{t("moneyMap.topSpendingDriversDetail")}</p>
                </div>

                {(moneyMap?.top_categories || []).length === 0 ? (
                  <div className="empty-state">
                    <p>{t("moneyMap.noMappedCategories")}</p>
                  </div>
                ) : (
                  <div className="money-map-category-list">
                    {moneyMap.top_categories.map((item) => (
                      <div key={item.category} className="money-map-category-row">
                        <div>
                          <strong>{formatCategoryLabel(item.category, t)}</strong>
                          <span>{item.share_percent.toFixed(1)}% {t("moneyMap.mappedSpend")}</span>
                        </div>
                        <p>{formatMoney(item.total)}</p>
                        <div className="money-map-category-track">
                          <div
                            className="money-map-category-fill"
                            style={{
                              width: `${
                                topCategoryTotal > 0
                                  ? Math.min((Number(item.total) / topCategoryTotal) * 100, 100)
                                  : 0
                              }%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="dashboard-card large-card">
                <div className="section-header">
                  <h2>{t("moneyMap.recurringSignals")}</h2>
                  <p>{t("moneyMap.recurringSignalsDetail")}</p>
                </div>

                {(moneyMap?.recurring_highlights || []).length === 0 ? (
                  <div className="empty-state">
                    <p>{t("moneyMap.recurringEmpty")}</p>
                  </div>
                ) : (
                  <div className="budget-insight-list">
                    {moneyMap.recurring_highlights.map((item) => (
                      <div key={`${item.description}-${item.average_amount}`} className="budget-insight-item">
                        <div className="budget-insight-top">
                          <span className="budget-insight-badge budget-insight-badge-watch">
                            {item.review_priority}
                          </span>
                          <strong>{item.description}</strong>
                        </div>
                        <p className="budget-insight-title">
                          {formatMoney(item.average_amount)} {t("moneyMap.monthlyAverage")}
                        </p>
                        <p className="budget-inline-note">
                          {formatCategoryLabel(item.category, t)} | {formatMoney(item.annualized_amount)} {t("moneyMap.perYear")}.
                          {item.review_reason ? ` ${formatRecurringReviewReason(item, t)}` : ""}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="dashboard-card">
              <div className="section-header">
                <div>
                  <h2>{t("moneyMap.categoryReviewQueue")}</h2>
                  <p>{t("moneyMap.categoryReviewQueueDetail")}</p>
                </div>
                <button className="secondary-button" onClick={() => navigate("/transactions")}>
                  {t("moneyMap.openTransactions")}
                </button>
              </div>

              {(moneyMap?.category_suggestions || []).length === 0 ? (
                <div className="empty-state">
                  <p>{t("moneyMap.noCategoryReviewItems")}</p>
                </div>
              ) : (
                <div className="money-map-suggestion-grid">
                  {moneyMap.category_suggestions.map((item) => (
                    <div key={`${item.description}-${item.suggested_category}`} className="money-map-suggestion-card">
                      <span>{item.source.replace("_", " ")}</span>
                      <strong>{item.description}</strong>
                      <p>
                        {t("moneyMap.suggestAtConfidence", {
                          category: formatCategoryLabel(item.suggested_category, t),
                          confidence: formatPercent(item.confidence),
                        })}
                      </p>
                      <small>{t("moneyMap.reviewInTransactions")}</small>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="dashboard-card">
              <div className="section-header">
                <div>
                  <h2>{t("moneyMap.merchantLearningQueue")}</h2>
                  <p>{t("moneyMap.merchantLearningQueueDetail")}</p>
                </div>
                <button className="secondary-button" onClick={() => navigate("/transactions")}>
                  {t("moneyMap.teachInTransactions")}
                </button>
              </div>

              {(moneyMap?.learning_candidates || []).length === 0 ? (
                <div className="empty-state">
                  <p>{t("moneyMap.noMerchantLearningItems")}</p>
                </div>
              ) : (
                <div className="money-map-suggestion-grid">
                  {moneyMap.learning_candidates.map((item) => (
                    <div key={`${item.merchant_key}-${item.type}`} className="money-map-suggestion-card">
                      <span>{item.type === "income" ? t("common.income") : t("common.expense")}</span>
                      <strong>{item.display_name}</strong>
                      <p>
                        {t("moneyMap.groupNeedsTeaching", {
                          count: item.transaction_count,
                          plural: item.transaction_count === 1 ? "" : "s",
                          category: formatCategoryLabel(item.suggested_category, t),
                          amount: formatMoney(item.total_amount),
                        })}
                      </p>
                      <small>{item.example_descriptions?.slice(0, 2).join(" | ")}</small>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default MoneyMapPage;
