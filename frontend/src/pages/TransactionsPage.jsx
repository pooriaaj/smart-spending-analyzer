import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import PageHeader from "../components/PageHeader";
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
  setSelectedAccountId as persistSelectedAccountId,
} from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import { formatCategoryLabel } from "../utils/displayLabels";

const getCurrentMonthStart = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
};

const TRANSACTIONS_PER_PAGE = 12;

const AMOUNT_RANGE_OPTIONS = [
  { value: "0-10", label: "$0-$10", min: 0, max: 10 },
  { value: "10-50", label: "$10-$50", min: 10, max: 50 },
  { value: "50-100", label: "$50-$100", min: 50, max: 100 },
  { value: "100-200", label: "$100-$200", min: 100, max: 200 },
  { value: "200-500", label: "$200-$500", min: 200, max: 500 },
  { value: "500-1000", label: "$500-$1,000", min: 500, max: 1000 },
  { value: "1000-2500", label: "$1,000-$2,500", min: 1000, max: 2500 },
  { value: "2500-5000", label: "$2,500-$5,000", min: 2500, max: 5000 },
  { value: "5000-10000", label: "$5,000-$10,000", min: 5000, max: 10000 },
  { value: "10000-plus", labelKey: "transactions.overAmount", amount: "10,000", min: 10000, max: null, minExclusive: true },
];

const DEFAULT_TRANSACTION_PAGE_META = {
  total: 0,
  scopeTotal: 0,
  page: 1,
  pageSize: TRANSACTIONS_PER_PAGE,
  totalPages: 1,
  availableMonths: [],
  availableCategories: [],
};

const buildPaginationItems = (currentPage, totalPages) => {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  let windowStart = Math.max(2, currentPage - 1);
  let windowEnd = Math.min(totalPages - 1, currentPage + 1);

  if (currentPage <= 3) {
    windowStart = 2;
    windowEnd = 4;
  }

  if (currentPage >= totalPages - 2) {
    windowStart = totalPages - 3;
    windowEnd = totalPages - 1;
  }

  const items = [1];

  if (windowStart > 2) {
    items.push("start-ellipsis");
  }

  for (let page = windowStart; page <= windowEnd; page += 1) {
    items.push(page);
  }

  if (windowEnd < totalPages - 1) {
    items.push("end-ellipsis");
  }

  items.push(totalPages);
  return items;
};

function TransactionsPage() {
  const { t } = useLanguage();
  const [transactions, setTransactions] = useState([]);
  const [transactionPageMeta, setTransactionPageMeta] = useState(DEFAULT_TRANSACTION_PAGE_META);
  const [typeFilter, setTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [amountRangeFilter, setAmountRangeFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [loading, setLoading] = useState(true);
  const [scopeNotice, setScopeNotice] = useState("");
  const [freshStartDate, setFreshStartDate] = useState(getCurrentMonthStart());
  const [freshStartConfirm, setFreshStartConfirm] = useState("");
  const [freshStartLoading, setFreshStartLoading] = useState(false);
  const [freshStartMessage, setFreshStartMessage] = useState("");
  const [freshStartError, setFreshStartError] = useState("");

  const [bulkSuggestions, setBulkSuggestions] = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkApplying, setBulkApplying] = useState(false);
  const [learningCandidates, setLearningCandidates] = useState([]);
  const [learningSummary, setLearningSummary] = useState(null);
  const [learningLoading, setLearningLoading] = useState(false);
  const [learningApplyingKey, setLearningApplyingKey] = useState("");
  const [learningCategoryEdits, setLearningCategoryEdits] = useState({});
  const [normalizingCategories, setNormalizingCategories] = useState(false);
  const [amountRepairCandidates, setAmountRepairCandidates] = useState([]);
  const [amountRepairLoading, setAmountRepairLoading] = useState(false);
  const [amountRepairApplying, setAmountRepairApplying] = useState(false);
  const [bulkMessage, setBulkMessage] = useState("");

  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({
    amount: "",
    category: "",
    description: "",
    date: "",
    type: "expense",
    account_id: "",
  });

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);

  const getSuggestionStrength = (confidence) => {
    if (confidence >= 0.95) {
      return { label: t("transactions.learned"), className: "bulk-confidence-pill bulk-confidence-pill-memory" };
    }
    if (confidence >= 0.85) {
      return { label: t("transactions.strongRule"), className: "bulk-confidence-pill bulk-confidence-pill-rule" };
    }
    return { label: t("transactions.review"), className: "bulk-confidence-pill bulk-confidence-pill-review" };
  };

  useEffect(() => {
    setTypeFilter(searchParams.get("type") || "");
    setMonthFilter(searchParams.get("month") || "");
    const categoryParam = searchParams.get("category") || "";
    setCategoryFilter(categoryParam);
    setSearchFilter(searchParams.get("description") || "");
    setAmountRangeFilter(searchParams.get("amountRange") || "");
  }, [searchParams]);

  const fetchTransactions = useCallback(async () => {
    try {
      const selectedAmountRange = AMOUNT_RANGE_OPTIONS.find(
        (option) => option.value === amountRangeFilter
      );
      const transactionParams = {
        account_id: normalizedAccountId,
        type: typeFilter || undefined,
        month: monthFilter || undefined,
        category: categoryFilter || undefined,
        description: searchFilter || undefined,
        amount_min: selectedAmountRange?.min,
        amount_max: selectedAmountRange?.max,
        amount_min_exclusive: selectedAmountRange?.minExclusive || undefined,
        page: currentPage,
        page_size: TRANSACTIONS_PER_PAGE,
      };
      const hasActiveFilters = Boolean(
        typeFilter ||
          monthFilter ||
          categoryFilter ||
          searchFilter ||
          amountRangeFilter
      );

      let [transactionsResponse, amountRepairsResponse, learningSummaryResponse] = await Promise.all([
        api.get("/transactions/page", {
          params: transactionParams,
        }),
        api
          .get("/transactions/amount-repairs/preview", {
            params: {
              account_id: normalizedAccountId,
            },
          })
          .catch(() => null),
        api
          .get("/transactions/categorize/learning-summary", {
            params: {
              account_id: normalizedAccountId,
            },
          })
          .catch(() => null),
      ]);

      if (
        normalizedAccountId &&
        !hasActiveFilters &&
        Number(transactionsResponse.data?.scope_total || 0) === 0
      ) {
        const [allTransactionsResponse, allAmountRepairsResponse, allLearningSummaryResponse] = await Promise.all([
          api.get("/transactions/page", {
            params: {
              page: currentPage,
              page_size: TRANSACTIONS_PER_PAGE,
            },
          }),
          api.get("/transactions/amount-repairs/preview").catch(() => null),
          api.get("/transactions/categorize/learning-summary").catch(() => null),
        ]);

        if (Number(allTransactionsResponse.data?.scope_total || 0) > 0) {
          transactionsResponse = allTransactionsResponse;
          amountRepairsResponse = allAmountRepairsResponse;
          learningSummaryResponse = allLearningSummaryResponse;
          persistSelectedAccountId(ALL_ACCOUNTS_VALUE);
          setSelectedAccountId(ALL_ACCOUNTS_VALUE);
          setScopeNotice(t("transactions.switchedAllAccountsNotice"));
        } else {
          setScopeNotice("");
        }
      } else {
        setScopeNotice("");
      }

      const pagePayload = transactionsResponse.data || {};
      setTransactions(pagePayload.items || []);
      setTransactionPageMeta({
        total: Number(pagePayload.total || 0),
        scopeTotal: Number(pagePayload.scope_total || 0),
        page: Number(pagePayload.page || 1),
        pageSize: Number(pagePayload.page_size || TRANSACTIONS_PER_PAGE),
        totalPages: Number(pagePayload.total_pages || 1),
        availableMonths: pagePayload.available_months || [],
        availableCategories: pagePayload.available_categories || [],
      });
      if (pagePayload.page && Number(pagePayload.page) !== currentPage) {
        setCurrentPage(Number(pagePayload.page));
      }
      setAmountRepairCandidates(amountRepairsResponse?.data?.candidates || []);
      setLearningSummary(learningSummaryResponse?.data || null);
    } catch (error) {
      handleApiAuthError(error, navigate);
    } finally {
      setLoading(false);
    }
  }, [
    amountRangeFilter,
    categoryFilter,
    currentPage,
    monthFilter,
    navigate,
    normalizedAccountId,
    searchFilter,
    t,
    typeFilter,
  ]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  const availableMonths = transactionPageMeta.availableMonths;
  const availableCategories = transactionPageMeta.availableCategories;
  const filteredTransactionTotal = transactionPageMeta.total;
  const scopeTransactionTotal = transactionPageMeta.scopeTotal;
  const totalPages = Math.max(1, transactionPageMeta.totalPages);
  const activePage = Math.min(transactionPageMeta.page || currentPage, totalPages);
  const pageStartIndex =
    filteredTransactionTotal === 0
      ? 0
      : (activePage - 1) * transactionPageMeta.pageSize;
  const pageEndIndex =
    filteredTransactionTotal === 0
      ? 0
      : Math.min(pageStartIndex + transactions.length, filteredTransactionTotal);
  const paginatedTransactions = transactions;
  const paginationItems = useMemo(
    () => buildPaginationItems(activePage, totalPages),
    [activePage, totalPages]
  );
  const learningLevel = learningSummary?.confidence_level || "empty";
  const learningLevelLabel =
    {
      high: t("transactions.learningHealthHigh"),
      medium: t("transactions.learningHealthMedium"),
      low: t("transactions.learningHealthLow"),
      empty: t("transactions.learningHealthEmpty"),
    }[learningLevel] || t("transactions.learningHealthEmpty");
  const formatLearningSource = (source) =>
    ({
      manual_create: t("transactions.learningSourceManualCreate"),
      manual_edit: t("transactions.learningSourceManualEdit"),
      import_review: t("transactions.learningSourceImportReview"),
      learning_apply: t("transactions.learningSourceGroupApply"),
    }[source] || t("transactions.learningSourceConfirmed"));

  useEffect(() => {
    setCurrentPage(1);
  }, [
    typeFilter,
    monthFilter,
    categoryFilter,
    searchFilter,
    amountRangeFilter,
    selectedAccountId,
  ]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const clearFilters = () => {
    setTypeFilter("");
    setMonthFilter("");
    setCategoryFilter("");
    setSearchFilter("");
    setAmountRangeFilter("");
    setCurrentPage(1);
  };

  const handleDelete = async (transactionId) => {
    try {
      await api.delete(`/transactions/${transactionId}`);
      await fetchTransactions();
    } catch (error) {
      handleApiAuthError(error, navigate);
    }
  };

  const startEdit = (transaction) => {
    setEditingId(transaction.id);
    setEditForm({
      amount: transaction.amount,
      category: transaction.category,
      description: transaction.description,
      date: transaction.date,
      type: transaction.type,
      account_id: transaction.account_id || "",
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({
      amount: "",
      category: "",
      description: "",
      date: "",
      type: "expense",
      account_id: "",
    });
  };

  const saveEdit = async (transactionId) => {
    try {
      await api.put(`/transactions/${transactionId}`, {
        amount: Number(editForm.amount),
        category: editForm.category,
        description: editForm.description,
        date: editForm.date,
        type: editForm.type,
        account_id: Number(editForm.account_id),
      });

      cancelEdit();
      await fetchTransactions();
    } catch (error) {
      handleApiAuthError(error, navigate);
    }
  };

  const handleBulkAnalyze = async () => {
    try {
      setBulkLoading(true);
      setBulkMessage("");
      const response = await api.get("/transactions/categorize/bulk-preview", {
        params: {
          account_id: normalizedAccountId,
        },
      });
      setBulkSuggestions(response.data.suggestions || []);
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage(t("transactions.bulkAnalyzeFailed"));
      }
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkApply = async () => {
    if (bulkSuggestions.length === 0) return;

    try {
      setBulkApplying(true);
      setBulkMessage("");

      const response = await api.post("/transactions/categorize/bulk-apply", {
        transaction_ids: bulkSuggestions.map((item) => item.transaction_id),
      });

      setBulkMessage(
        t("transactions.bulkApplySuccess", {
          count: response.data.updated_count,
          plural: response.data.updated_count === 1 ? "" : "s",
        })
      );
      setBulkSuggestions([]);
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage(t("transactions.bulkApplyFailed"));
      }
    } finally {
      setBulkApplying(false);
    }
  };

  const handleFindLearningCandidates = async () => {
    try {
      setLearningLoading(true);
      setBulkMessage("");
      const response = await api.get("/transactions/categorize/learning-candidates", {
        params: {
          account_id: normalizedAccountId,
        },
      });
      const candidates = response.data?.candidates || [];
      setLearningCandidates(candidates);
      setLearningCategoryEdits(
        candidates.reduce((drafts, item) => {
          drafts[`${item.merchant_key}:${item.type}`] = item.suggested_category || item.current_category || "";
          return drafts;
        }, {})
      );
      if (candidates.length === 0) {
        setBulkMessage(t("transactions.noLearningCandidates"));
      }
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage(t("transactions.learningAnalyzeFailed"));
      }
    } finally {
      setLearningLoading(false);
    }
  };

  const handleApplyLearningCandidate = async (candidate) => {
    const candidateKey = `${candidate.merchant_key}:${candidate.type}`;
    const category = (learningCategoryEdits[candidateKey] || candidate.suggested_category || "").trim();
    if (!category) return;

    try {
      setLearningApplyingKey(candidateKey);
      setBulkMessage("");
      const response = await api.post("/transactions/categorize/learning-apply", {
        merchant_key: candidate.merchant_key,
        type: candidate.type,
        category,
        account_id: normalizedAccountId || null,
      });

      setBulkMessage(
        t("transactions.learningApplySuccess", {
          matched: response.data?.matched_count || 0,
          updated: response.data?.updated_count || 0,
          category: formatCategoryLabel(category, t),
        })
      );
      setLearningCandidates((prev) =>
        prev.filter((item) => `${item.merchant_key}:${item.type}` !== candidateKey)
      );
      setBulkSuggestions([]);
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage(t("transactions.learningApplyFailed"));
      }
    } finally {
      setLearningApplyingKey("");
    }
  };

  const handleNormalizeCategories = async () => {
    try {
      setNormalizingCategories(true);
      setBulkMessage("");

      const response = await api.post("/transactions/normalize-categories", null, {
        params: {
          account_id: normalizedAccountId,
        },
      });

      const updatedCount = response.data?.updated_count || 0;
      const memoryCreated = response.data?.memory_entries_created || 0;
      const memoryUpdated = response.data?.memory_entries_updated || 0;

      setBulkMessage(
        t("transactions.normalizeSuccess", {
          count: updatedCount,
          categoryPlural: updatedCount === 1 ? "" : "s",
          memoryCount: memoryCreated + memoryUpdated,
          memoryPlural: memoryCreated + memoryUpdated === 1 ? "" : "s",
        })
      );
      setBulkSuggestions([]);
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage(t("transactions.normalizeFailed"));
      }
    } finally {
      setNormalizingCategories(false);
    }
  };

  const handleFindAmountRepairs = async () => {
    try {
      setAmountRepairLoading(true);
      setBulkMessage("");
      const response = await api.get("/transactions/amount-repairs/preview", {
        params: {
          account_id: normalizedAccountId,
        },
      });
      const candidates = response.data?.candidates || [];
      setAmountRepairCandidates(candidates);
      if (candidates.length === 0) {
        setBulkMessage(t("transactions.amountRepairNone"));
      }
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage(t("transactions.amountRepairFailed"));
      }
    } finally {
      setAmountRepairLoading(false);
    }
  };

  const handleApplyAmountRepairs = async () => {
    if (amountRepairCandidates.length === 0) return;

    try {
      setAmountRepairApplying(true);
      setBulkMessage("");
      const response = await api.post("/transactions/amount-repairs/apply", {
        transaction_ids: amountRepairCandidates.map((item) => item.transaction_id),
        account_id: normalizedAccountId || null,
      });
      setBulkMessage(
        t("transactions.amountRepairApplied", {
          count: response.data?.updated_count || 0,
          plural: (response.data?.updated_count || 0) === 1 ? "" : "s",
        })
      );
      setAmountRepairCandidates([]);
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage(t("transactions.amountRepairApplyFailed"));
      }
    } finally {
      setAmountRepairApplying(false);
    }
  };

  const handleFreshStart = async () => {
    if (freshStartConfirm.trim().toUpperCase() !== "START FRESH") {
      setFreshStartError(t("transactions.freshStartConfirmError"));
      return;
    }

    try {
      setFreshStartLoading(true);
      setFreshStartMessage("");
      setFreshStartError("");

      const response = await api.post("/transactions/fresh-start", {
        keep_from: freshStartDate,
        account_id: normalizedAccountId || null,
        delete_all: false,
      });

      setFreshStartMessage(response.data?.message || t("transactions.freshStartComplete"));
      setFreshStartConfirm("");
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setFreshStartError(error?.response?.data?.detail || t("transactions.freshStartFailed"));
      }
    } finally {
      setFreshStartLoading(false);
    }
  };

  const renderTransactionPagination = (positionClass = "") => {
    if (totalPages <= 1) return null;

    return (
      <nav className={`transaction-pagination ${positionClass}`} aria-label={t("transactions.transactionPages")}>
        <button
          type="button"
          className="pagination-button"
          onClick={() => setCurrentPage(Math.max(1, activePage - 1))}
          disabled={activePage === 1}
        >
          {t("common.previous")}
        </button>

        <div className="pagination-pages">
          {paginationItems.map((item, index) =>
            typeof item === "number" ? (
              <button
                type="button"
                key={item}
                className={`pagination-button pagination-number ${activePage === item ? "pagination-button-active" : ""}`}
                onClick={() => setCurrentPage(item)}
                aria-current={activePage === item ? "page" : undefined}
              >
                {item}
              </button>
            ) : (
              <span key={`${item}-${index}`} className="pagination-ellipsis" aria-hidden="true">
                ...
              </span>
            )
          )}
        </div>

        <button
          type="button"
          className="pagination-button"
          onClick={() => setCurrentPage(Math.min(totalPages, activePage + 1))}
          disabled={activePage === totalPages}
        >
          {t("common.next")}
        </button>
      </nav>
    );
  };

  if (loading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>{t("transactions.loadingTitle")}</h2>
            <p>{t("transactions.loadingDetail")}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <PageHeader
          icon="TX"
          titleKey="common.transactions"
          subtitleKey="headers.transactionsSubtitle"
          actions={(
            <button className="secondary-button" onClick={() => navigate("/import")}>
              {t("transactions.reconcileStatement")}
            </button>
          )}
        />

        <div className="dashboard-card product-guide-card">
          <div className="section-header">
            <h2>{t("transactions.howTitle")}</h2>
            <p>{t("transactions.howDetail")}</p>
          </div>

          <div className="feature-guide-grid">
            <div className="feature-guide-item">
              <span className="feature-step">{t("transactions.daily")}</span>
              <h3>{t("transactions.dailyTitle")}</h3>
              <p>{t("transactions.dailyDetail")}</p>
            </div>

            <div className="feature-guide-item">
              <span className="feature-step">{t("transactions.month")}</span>
              <h3>{t("transactions.monthTitle")}</h3>
              <p>{t("transactions.monthDetail")}</p>
            </div>

            <div className="feature-guide-item">
              <span className="feature-step">{t("transactions.learn")}</span>
              <h3>{t("transactions.learnTitle")}</h3>
              <p>{t("transactions.learnDetail")}</p>
            </div>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>{t("dashboard.accountView")}</h2>
            <p>{t("transactions.accountViewDetail")}</p>
          </div>
          <AccountSelector value={selectedAccountId} onChange={setSelectedAccountId} allowAll={true} />
          {scopeNotice && <div className="bulk-message-box">{scopeNotice}</div>}
        </div>

        <div className="filter-card fresh-start-card">
          <div className="section-header">
            <h2>{t("transactions.freshStart")}</h2>
            <p>{t("transactions.freshStartDetail")}</p>
          </div>

          <div className="fresh-start-grid">
            <div>
              <label htmlFor="fresh-start-date">{t("transactions.keepFrom")}</label>
              <input
                id="fresh-start-date"
                type="date"
                value={freshStartDate}
                onChange={(event) => setFreshStartDate(event.target.value)}
              />
              <p className="budget-inline-note">
                {t("transactions.freshStartDeleteNote")}
              </p>
            </div>

            <div>
              <label htmlFor="fresh-start-confirm">{t("transactions.confirmation")}</label>
              <input
                id="fresh-start-confirm"
                type="text"
                value={freshStartConfirm}
                onChange={(event) => setFreshStartConfirm(event.target.value)}
                placeholder={t("transactions.typeStartFresh")}
              />
              <p className="budget-inline-note">
                {t("transactions.freshStartCarefulNote")}
              </p>
            </div>
          </div>

          <div className="smart-actions-row">
            <button
              type="button"
              className="delete-button"
              onClick={handleFreshStart}
              disabled={freshStartLoading || !freshStartDate}
            >
              {freshStartLoading ? t("transactions.cleaning") : t("transactions.deleteOldHistory")}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => navigate("/import")}
            >
              {t("transactions.reconcileThisMonth")}
            </button>
          </div>

          {freshStartMessage && <div className="bulk-message-box">{freshStartMessage}</div>}
          {freshStartError && <p className="error-text">{freshStartError}</p>}
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>{t("transactions.smartCategorization")}</h2>
            <p>{t("transactions.smartCategorizationDetail")}</p>
          </div>

          {learningSummary && (
            <div className="learning-health-panel">
              <div className="learning-health-head">
                <div>
                  <span className="learning-health-eyebrow">
                    {t("transactions.learningHealthTitle")}
                  </span>
                  <h3>{learningLevelLabel}</h3>
                  <p>
                    {t("transactions.learningHealthDetail")}
                  </p>
                </div>
                <span className={`learning-health-pill learning-health-${learningLevel}`}>
                  {Math.round(Number(learningSummary.confidence_score || 0) * 100)}%
                </span>
              </div>

              <div className="learning-health-grid">
                <div className="learning-health-card">
                  <span>{t("transactions.learningTracked")}</span>
                  <strong>{learningSummary.transaction_count}</strong>
                </div>
                <div className="learning-health-card">
                  <span>{t("transactions.learningNeedsReview")}</span>
                  <strong>{learningSummary.uncategorized_count}</strong>
                  <small>
                    {t("transactions.learningGroups", {
                      count: learningSummary.learning_candidate_count,
                    })}
                  </small>
                </div>
                <div className="learning-health-card">
                  <span>{t("transactions.learningPersonalMemory")}</span>
                  <strong>{learningSummary.merchant_profile_count}</strong>
                  <small>
                    {t("transactions.learningKeywordRules", {
                      count: learningSummary.personal_memory_count,
                    })}
                  </small>
                </div>
                <div className="learning-health-card">
                  <span>{t("transactions.learningEvents")}</span>
                  <strong>{learningSummary.learning_event_count}</strong>
                  <small>{t("transactions.learningEventsDetail")}</small>
                </div>
                <div className="learning-health-card">
                  <span>{t("transactions.learningCommunity")}</span>
                  <strong>
                    {learningSummary.community_learning_enabled
                      ? t("transactions.learningOn")
                      : t("transactions.learningOff")}
                  </strong>
                  <small>
                    {t("transactions.learningCommunityPatterns", {
                      count: learningSummary.community_pattern_count,
                    })}
                  </small>
                </div>
              </div>

              {(learningSummary.recent_learning_events || []).length > 0 && (
                <div className="learning-events-list">
                  <h4>{t("transactions.recentLessons")}</h4>
                  {learningSummary.recent_learning_events.map((event, index) => (
                    <div
                      key={`${event.merchant_key}-${event.created_at}-${index}`}
                      className="learning-event-row"
                    >
                      <div>
                        <strong>{event.display_name}</strong>
                        <span>
                          {formatCategoryLabel(event.category, t)}{" - "}
                          {formatLearningSource(event.signal_source)}
                        </span>
                      </div>
                      <span className="learning-event-count">
                        {t("transactions.learningAffected", {
                          count: event.affected_count,
                        })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="smart-actions-row">
            <button
              type="button"
              className="smart-action-button"
              onClick={handleBulkAnalyze}
              disabled={bulkLoading}
            >
              {bulkLoading ? t("transactions.analyzing") : t("transactions.analyzeUncategorized")}
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={handleFindLearningCandidates}
              disabled={learningLoading}
            >
              {learningLoading
                ? t("transactions.findingLearningGroups")
                : t("transactions.findLearningGroups")}
            </button>

            <button
              type="button"
              className="smart-apply-button"
              onClick={handleBulkApply}
              disabled={bulkApplying || bulkSuggestions.length === 0}
            >
              {bulkApplying ? t("transactions.applying") : t("transactions.applySuggestedCategories")}
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={handleNormalizeCategories}
              disabled={normalizingCategories}
            >
              {normalizingCategories
                ? t("transactions.normalizing")
                : t("transactions.normalizeExistingCategories")}
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={handleFindAmountRepairs}
              disabled={amountRepairLoading}
            >
              {amountRepairLoading
                ? t("transactions.checkingAmounts")
                : t("transactions.findSuspiciousAmounts")}
            </button>

            <button
              type="button"
              className="smart-apply-button"
              onClick={handleApplyAmountRepairs}
              disabled={amountRepairApplying || amountRepairCandidates.length === 0}
            >
              {amountRepairApplying
                ? t("transactions.repairingAmounts")
                : t("transactions.applyAmountRepairs")}
            </button>
          </div>

          {bulkMessage && <div className="bulk-message-box">{bulkMessage}</div>}

          {learningCandidates.length > 0 && (
            <div className="bulk-suggestions-list">
              {learningCandidates.map((item) => {
                const candidateKey = `${item.merchant_key}:${item.type}`;
                const draftCategory =
                  learningCategoryEdits[candidateKey] ?? item.suggested_category ?? item.current_category ?? "";

                return (
                  <div key={candidateKey} className="bulk-suggestion-card">
                    <div className="bulk-suggestion-top">
                      <div>
                        <h3>{item.display_name}</h3>
                        <p>
                          {t("transactions.learningGroupSummary", {
                            count: item.transaction_count,
                            plural: item.transaction_count === 1 ? "" : "s",
                            total: Number(item.total_amount || 0).toFixed(2),
                          })}
                        </p>
                      </div>
                      <div className="bulk-suggestion-badges">
                        <span className="bulk-confidence-pill bulk-confidence-pill-review">
                          {t("transactions.teachMemory")}
                        </span>
                        <span className="bulk-confidence-pill">
                          {Math.round(Number(item.confidence || 0) * 100)}%
                        </span>
                      </div>
                    </div>

                    <p className="bulk-suggestion-meta">
                      {t("common.current")}:{" "}
                      <strong>{formatCategoryLabel(item.current_category, t)}</strong>{" "}
                      {"->"} {t("common.suggested")}:{" "}
                      <strong>{formatCategoryLabel(item.suggested_category, t)}</strong>
                    </p>
                    <p className="bulk-suggestion-meta">{item.reason}</p>
                    {item.example_descriptions?.length > 0 && (
                      <p className="bulk-suggestion-meta">
                        {t("transactions.examples")}: {item.example_descriptions.join(" | ")}
                      </p>
                    )}

                    <div className="filter-bar compact-filter-bar">
                      <div>
                        <label>{t("transactions.correctCategory")}</label>
                        <input
                          type="text"
                          value={draftCategory}
                          onChange={(event) =>
                            setLearningCategoryEdits((prev) => ({
                              ...prev,
                              [candidateKey]: event.target.value,
                            }))
                          }
                          placeholder={t("transactions.correctCategoryPlaceholder")}
                        />
                      </div>
                      <button
                        type="button"
                        className="smart-apply-button"
                        onClick={() => handleApplyLearningCandidate(item)}
                        disabled={learningApplyingKey === candidateKey || !draftCategory.trim()}
                      >
                        {learningApplyingKey === candidateKey
                          ? t("transactions.teaching")
                          : t("transactions.applyToSimilar")}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {amountRepairCandidates.length > 0 && (
            <div className="bulk-suggestions-list">
              {amountRepairCandidates.map((item) => (
                <div key={item.transaction_id} className="bulk-suggestion-card">
                  <div className="bulk-suggestion-top">
                    <div>
                      <h3>{item.description}</h3>
                      <p>
                        {t("transactions.amountRepairChange", {
                          current: Number(item.current_amount || 0).toFixed(2),
                          suggested: Number(item.suggested_amount || 0).toFixed(2),
                        })}
                      </p>
                    </div>
                    <div className="bulk-suggestion-badges">
                      <span className="bulk-confidence-pill bulk-confidence-pill-review">
                        {t("transactions.review")}
                      </span>
                      <span className="bulk-confidence-pill">
                        {Math.round(Number(item.confidence || 0) * 100)}%
                      </span>
                    </div>
                  </div>
                  <p className="bulk-suggestion-meta">{item.reason}</p>
                </div>
              ))}
            </div>
          )}

          {bulkSuggestions.length > 0 && (
            <div className="bulk-suggestions-list">
              {bulkSuggestions.map((item) => {
                const suggestionStrength = getSuggestionStrength(item.confidence);

                return (
                  <div key={item.transaction_id} className="bulk-suggestion-card">
                    <div className="bulk-suggestion-top">
                      <div>
                        <h3>{item.description}</h3>
                        <p>
                          {t("common.current")}: <strong>{formatCategoryLabel(item.current_category, t)}</strong> {"->"} {t("common.suggested")}: <strong>{formatCategoryLabel(item.suggested_category, t)}</strong>
                        </p>
                      </div>

                      <div className="bulk-suggestion-badges">
                        <span className={suggestionStrength.className}>
                          {suggestionStrength.label}
                        </span>
                        <span className="bulk-confidence-pill">
                          {Math.round(item.confidence * 100)}%
                        </span>
                      </div>
                    </div>

                    <p className="bulk-suggestion-meta">
                      {t("common.type")}:{" "}
                      {item.type === "income" ? t("common.income") : t("common.expense")}
                    </p>
                    {item.matched_keyword && (
                      <p className="bulk-suggestion-meta">
                        {t("transactions.matchedKeyword")}: <strong>{item.matched_keyword}</strong>
                      </p>
                    )}
                    <p className="bulk-suggestion-meta">
                      {t("transactions.suggestionReasonGeneric")}
                    </p>
                  </div>
                );
              })}
            </div>
          )}

          {!bulkLoading &&
            learningCandidates.length === 0 &&
            bulkSuggestions.length === 0 &&
            amountRepairCandidates.length === 0 &&
            !bulkMessage && (
            <div className="empty-state">
              <p>{t("transactions.noBulkSuggestions")}</p>
            </div>
          )}
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>{t("transactions.transactionFilters")}</h2>
            <p>
              {t("transactions.showingTransactions", {
                filtered: filteredTransactionTotal,
                total: scopeTransactionTotal,
                plural: scopeTransactionTotal === 1 ? "" : "s",
              })}
            </p>
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
                  <option key={month} value={month}>{month}</option>
                ))}
              </select>
            </div>

            <div>
              <label>{t("common.category")}</label>
              <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                <option value="">{t("common.all")}</option>
                {availableCategories.map((category) => (
                  <option key={category} value={category}>{formatCategoryLabel(category, t)}</option>
                ))}
              </select>
            </div>

            <div>
              <label>{t("transactions.amountRange")}</label>
              <select
                value={amountRangeFilter}
                onChange={(e) => setAmountRangeFilter(e.target.value)}
              >
                <option value="">{t("transactions.allAmounts")}</option>
                {AMOUNT_RANGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.labelKey ? t(option.labelKey, { amount: option.amount }) : option.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label>{t("common.description")}</label>
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder={t("transactions.descriptionSearch")}
              />
            </div>
          </div>

          <div className="smart-actions-row recurring-filter-actions">
            {(typeFilter ||
              monthFilter ||
              categoryFilter ||
              amountRangeFilter ||
              searchFilter) && (
              <button type="button" className="secondary-button" onClick={clearFilters}>
                {t("common.clearFilters")}
              </button>
            )}
          </div>

          {searchFilter && (
            <p className="budget-inline-note recurring-filter-note">
              {t("transactions.descriptionFilterNote", { term: searchFilter })}
            </p>
          )}
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <h2>{t("transactions.transactionTable")}</h2>
            <p>{t("transactions.tableDetail")}</p>
          </div>

          {filteredTransactionTotal === 0 ? (
            <div className="empty-state">
              <p>
                {scopeTransactionTotal === 0
                  ? t("transactions.noTransactions")
                  : t("transactions.filtersHidingTransactions")}
              </p>
              {scopeTransactionTotal === 0 ? (
                <button className="secondary-button" onClick={() => navigate("/dashboard")}>
                  {t("transactions.addToday")}
                </button>
              ) : (
                <button className="secondary-button" onClick={clearFilters}>
                  {t("common.clearFilters")}
                </button>
              )}
            </div>
          ) : (
            <div className="transaction-table-panel">
              <div className="transaction-table-toolbar">
                <div>
                  <span className="transaction-page-kicker">
                    {totalPages > 1
                      ? t("common.pageOf", { page: activePage, total: totalPages })
                      : t("common.allTransactions")}
                  </span>
                  <p className="transaction-page-summary">
                    {t("transactions.pageSummary", {
                      start: pageStartIndex + 1,
                      end: pageEndIndex,
                      total: filteredTransactionTotal,
                      plural: filteredTransactionTotal === 1 ? "" : "s",
                    })}
                  </p>
                </div>

                {renderTransactionPagination("transaction-pagination-top")}
              </div>

              <div className="transactions-table-wrapper">
                <table className="transactions-table">
                  <thead>
                    <tr>
                      <th>{t("common.date")}</th>
                      <th>{t("common.type")}</th>
                      <th>{t("common.category")}</th>
                      <th>{t("common.description")}</th>
                      <th>{t("common.amount")}</th>
                      <th>{t("common.account")}</th>
                      <th>{t("common.actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedTransactions.map((transaction) => {
                      const isEditing = editingId === transaction.id;

                      return (
                        <tr key={transaction.id}>
                          <td>
                            {isEditing ? (
                              <input type="date" value={editForm.date} onChange={(e) => setEditForm({ ...editForm, date: e.target.value })} />
                            ) : transaction.date}
                          </td>

                          <td>
                            {isEditing ? (
                              <select value={editForm.type} onChange={(e) => setEditForm({ ...editForm, type: e.target.value })}>
                                <option value="income">{t("common.income")}</option>
                                <option value="expense">{t("common.expense")}</option>
                              </select>
                            ) : transaction.type}
                          </td>

                          <td>
                            {isEditing ? (
                              <input type="text" value={editForm.category} onChange={(e) => setEditForm({ ...editForm, category: e.target.value })} />
                            ) : formatCategoryLabel(transaction.category, t)}
                          </td>

                          <td>
                            {isEditing ? (
                              <input
                                type="text"
                                value={editForm.description}
                                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                              />
                            ) : transaction.description}
                          </td>

                          <td className={!isEditing ? (transaction.type === "income" ? "income-text" : "expense-text") : ""}>
                            {isEditing ? (
                              <input type="number" step="0.01" value={editForm.amount} onChange={(e) => setEditForm({ ...editForm, amount: e.target.value })} />
                            ) : (
                              <>{transaction.type === "income" ? "+" : "-"}${transaction.amount.toFixed(2)}</>
                            )}
                          </td>

                          <td>
                            {isEditing ? (
                              <input
                                type="number"
                                value={editForm.account_id}
                                onChange={(e) => setEditForm({ ...editForm, account_id: e.target.value })}
                              />
                            ) : transaction.account_id || t("common.unassigned")}
                          </td>

                          <td>
                            <div className="transaction-actions-inline">
                              {isEditing ? (
                                <>
                                  <button className="edit-button" onClick={() => saveEdit(transaction.id)}>
                                    {t("common.save")}
                                  </button>
                                  <button className="secondary-button" onClick={cancelEdit}>
                                    {t("common.cancel")}
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button className="edit-button" onClick={() => startEdit(transaction)}>
                                    {t("common.edit")}
                                  </button>
                                  <button className="delete-button" onClick={() => handleDelete(transaction.id)}>
                                    {t("common.delete")}
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {renderTransactionPagination("transaction-pagination-bottom")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default TransactionsPage;
