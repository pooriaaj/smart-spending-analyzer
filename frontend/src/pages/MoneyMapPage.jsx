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

function formatMoney(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatCategory(value) {
  if (!value) return "Other";
  return String(value)
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function getConfidenceClass(level) {
  if (level === "High") return "money-map-confidence-high";
  if (level === "Medium") return "money-map-confidence-medium";
  return "money-map-confidence-low";
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
        setError("Failed to load your Money Map.");
      }
    } finally {
      setLoading(false);
    }
  }, [navigate, normalizedAccountId]);

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
                {moneyMap?.confidence_level ? `${moneyMap.confidence_level} confidence` : t("moneyMap.lowConfidence")}
              </span>
              <h2>{isEmpty ? t("moneyMap.startStatement") : t("moneyMap.learnedModel")}</h2>
              <p>{moneyMap?.narrative}</p>
            </div>
            <div className="money-map-score-ring">
              <strong>{formatPercent(moneyMap?.confidence_score)}</strong>
              <span>{t("moneyMap.modelConfidence")}</span>
            </div>
          </div>

          <div className="money-map-action-grid">
            {(moneyMap?.actions || []).map((action) => (
              <button
                key={`${action.page}-${action.label}`}
                type="button"
                className={`money-map-action-card money-map-action-${action.priority}`}
                onClick={() => handleAction(action)}
              >
                <strong>{action.label}</strong>
                <span>{action.detail}</span>
              </button>
            ))}
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
                {(moneyMap?.learning_signals || []).map((signal) => (
                  <div
                    key={signal.label}
                    className={`money-map-signal-card money-map-signal-${signal.severity}`}
                  >
                    <span>{signal.label}</span>
                    <strong>{signal.value}</strong>
                    <p>{signal.detail}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="chart-grid">
              <div className="dashboard-card large-card">
                <div className="section-header">
                  <h2>Top Spending Drivers</h2>
                  <p>Highest expense categories learned from the selected scope.</p>
                </div>

                {(moneyMap?.top_categories || []).length === 0 ? (
                  <div className="empty-state">
                    <p>No expense categories are mapped yet.</p>
                  </div>
                ) : (
                  <div className="money-map-category-list">
                    {moneyMap.top_categories.map((item) => (
                      <div key={item.category} className="money-map-category-row">
                        <div>
                          <strong>{formatCategory(item.category)}</strong>
                          <span>{item.share_percent.toFixed(1)}% of mapped spend</span>
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
                  <h2>Recurring Signals</h2>
                  <p>Repeat charges that can become savings scenarios.</p>
                </div>

                {(moneyMap?.recurring_highlights || []).length === 0 ? (
                  <div className="empty-state">
                    <p>Upload two or three months of history to detect recurring charges.</p>
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
                          {formatMoney(item.average_amount)} monthly average
                        </p>
                        <p className="budget-inline-note">
                          {formatCategory(item.category)} | {formatMoney(item.annualized_amount)} per year.
                          {item.review_reason ? ` ${item.review_reason}` : ""}
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
                  <h2>Category Review Queue</h2>
                  <p>Safe suggestions only: low-confidence fallbacks stay out of this list.</p>
                </div>
                <button className="secondary-button" onClick={() => navigate("/transactions")}>
                  Open Transactions
                </button>
              </div>

              {(moneyMap?.category_suggestions || []).length === 0 ? (
                <div className="empty-state">
                  <p>No high-confidence category review items right now.</p>
                </div>
              ) : (
                <div className="money-map-suggestion-grid">
                  {moneyMap.category_suggestions.map((item) => (
                    <div key={`${item.description}-${item.suggested_category}`} className="money-map-suggestion-card">
                      <span>{item.source.replace("_", " ")}</span>
                      <strong>{item.description}</strong>
                      <p>
                        Suggest {formatCategory(item.suggested_category)} at{" "}
                        {formatPercent(item.confidence)} confidence.
                      </p>
                      <small>{item.reason}</small>
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
