import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId } from "../services/accountStorage";

const getCurrentMonthStart = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
};

const normalizeTextForMatching = (value = "") =>
  value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

const normalizeRecurringDescription = (value = "") => {
  let normalized = normalizeTextForMatching(value);
  if (!normalized) return "";

  normalized = normalized.replace(
    /\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b/g,
    " "
  );
  normalized = normalized.replace(/\b\d+\b/g, " ");
  return normalized.replace(/\s+/g, " ").trim();
};

function TransactionsPage() {
  const [transactions, setTransactions] = useState([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [recurringOnlyFilter, setRecurringOnlyFilter] = useState(false);
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [loading, setLoading] = useState(true);
  const [recurringPatterns, setRecurringPatterns] = useState([]);
  const [freshStartDate, setFreshStartDate] = useState(getCurrentMonthStart());
  const [freshStartConfirm, setFreshStartConfirm] = useState("");
  const [freshStartLoading, setFreshStartLoading] = useState(false);
  const [freshStartMessage, setFreshStartMessage] = useState("");
  const [freshStartError, setFreshStartError] = useState("");

  const [bulkSuggestions, setBulkSuggestions] = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkApplying, setBulkApplying] = useState(false);
  const [normalizingCategories, setNormalizingCategories] = useState(false);
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
      return { label: "Learned", className: "bulk-confidence-pill bulk-confidence-pill-memory" };
    }
    if (confidence >= 0.85) {
      return { label: "Strong rule", className: "bulk-confidence-pill bulk-confidence-pill-rule" };
    }
    return { label: "Review", className: "bulk-confidence-pill bulk-confidence-pill-review" };
  };

  useEffect(() => {
    setTypeFilter(searchParams.get("type") || "");
    setMonthFilter(searchParams.get("month") || "");
    setCategoryFilter(searchParams.get("category") || "");
    setSearchFilter(searchParams.get("description") || "");
    setRecurringOnlyFilter(searchParams.get("section") === "recurring");
  }, [searchParams]);

  const fetchTransactions = async () => {
    try {
      const [transactionsResponse, recurringResponse] = await Promise.all([
        api.get("/transactions/", {
          params: {
            account_id: normalizedAccountId,
          },
        }),
        api
          .get("/analytics/recurring-transactions", {
            params: {
              account_id: normalizedAccountId,
            },
          })
          .catch(() => null),
      ]);
      setTransactions(transactionsResponse.data);
      setRecurringPatterns(recurringResponse?.data?.items || []);
    } catch (error) {
      handleApiAuthError(error, navigate);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, [selectedAccountId]);

  const availableMonths = useMemo(() => {
    const months = new Set(
      transactions.map((transaction) => new Date(transaction.date).toISOString().slice(0, 7))
    );
    return Array.from(months).sort().reverse();
  }, [transactions]);

  const availableCategories = useMemo(() => {
    return Array.from(new Set(transactions.map((transaction) => transaction.category))).sort();
  }, [transactions]);

  const recurringDescriptionKeys = useMemo(
    () =>
      new Set(
        recurringPatterns
          .map((item) => normalizeRecurringDescription(item.description))
          .filter(Boolean)
      ),
    [recurringPatterns]
  );

  const filteredTransactions = useMemo(() => {
    return transactions
      .filter((transaction) => {
        const transactionMonth = new Date(transaction.date).toISOString().slice(0, 7);
        const normalizedDescription = normalizeTextForMatching(transaction.description);
        const recurringDescription = normalizeRecurringDescription(transaction.description);
        const normalizedSearch = normalizeTextForMatching(searchFilter);
        const recurringSearch = normalizeRecurringDescription(searchFilter);

        if (typeFilter && transaction.type !== typeFilter) return false;
        if (monthFilter && transactionMonth !== monthFilter) return false;
        if (categoryFilter && transaction.category !== categoryFilter) return false;
        if (
          searchFilter &&
          !normalizedDescription.includes(normalizedSearch) &&
          recurringDescription !== recurringSearch
        ) {
          return false;
        }
        if (recurringOnlyFilter && !recurringDescriptionKeys.has(recurringDescription)) return false;

        return true;
      })
      .sort((a, b) => new Date(b.date) - new Date(a.date));
  }, [
    transactions,
    typeFilter,
    monthFilter,
    categoryFilter,
    searchFilter,
    recurringOnlyFilter,
    recurringDescriptionKeys,
  ]);

  const applyRecurringFilter = (item) => {
    setSearchFilter(item.description || "");
    setRecurringOnlyFilter(true);
    setTypeFilter(item.type || "expense");
    setCategoryFilter(item.category || "");
  };

  const clearFilters = () => {
    setTypeFilter("");
    setMonthFilter("");
    setCategoryFilter("");
    setSearchFilter("");
    setRecurringOnlyFilter(false);
  };

  const getRecurringPriorityClass = (priority) => {
    if (priority === "high") return "budget-status budget-status-over";
    if (priority === "medium") return "budget-status budget-status-risk";
    return "budget-status budget-status-on-track";
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
      account_id: transaction.account_id,
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
        setBulkMessage("Failed to analyze transactions.");
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

      setBulkMessage(`Applied suggested categories to ${response.data.updated_count} transaction(s).`);
      setBulkSuggestions([]);
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage("Failed to apply suggested categories.");
      }
    } finally {
      setBulkApplying(false);
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
        `Normalized ${updatedCount} transaction categor${updatedCount === 1 ? "y" : "ies"} and refreshed ${memoryCreated + memoryUpdated} saved memory pattern${memoryCreated + memoryUpdated === 1 ? "" : "s"}.`
      );
      setBulkSuggestions([]);
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setBulkMessage("Failed to normalize existing categories.");
      }
    } finally {
      setNormalizingCategories(false);
    }
  };

  const handleFreshStart = async () => {
    if (freshStartConfirm.trim().toUpperCase() !== "START FRESH") {
      setFreshStartError('Type "START FRESH" to confirm this cleanup.');
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

      setFreshStartMessage(response.data?.message || "Fresh start complete.");
      setFreshStartConfirm("");
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setFreshStartError(error?.response?.data?.detail || "Failed to clean old history.");
      }
    } finally {
      setFreshStartLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-wrapper">
          <div className="status-card">
            <h2>Loading transactions...</h2>
            <p>Please wait while your transaction history is being prepared.</p>
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
            <h1>All Transactions</h1>
            <p className="hero-subtitle">
              Browse, filter, manage, and improve your transaction history.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              Back to Dashboard
            </button>
            <button className="secondary-button" onClick={() => navigate("/import")}>
              Smart Import
            </button>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Account View</h2>
            <p>Select all accounts or focus on one account.</p>
          </div>
          <AccountSelector onChange={setSelectedAccountId} allowAll={true} />
        </div>

        <div className="filter-card fresh-start-card">
          <div className="section-header">
            <h2>Fresh Start</h2>
            <p>
              Remove old statement history and keep the transactions from your new spending life.
              This is built for your new workflow: write daily transactions, then reconcile the month-end bank statement.
            </p>
          </div>

          <div className="fresh-start-grid">
            <div>
              <label htmlFor="fresh-start-date">Keep transactions from</label>
              <input
                id="fresh-start-date"
                type="date"
                value={freshStartDate}
                onChange={(event) => setFreshStartDate(event.target.value)}
              />
              <p className="budget-inline-note">
                Everything before this date in the selected account view will be deleted.
              </p>
            </div>

            <div>
              <label htmlFor="fresh-start-confirm">Confirmation</label>
              <input
                id="fresh-start-confirm"
                type="text"
                value={freshStartConfirm}
                onChange={(event) => setFreshStartConfirm(event.target.value)}
                placeholder='Type "START FRESH"'
              />
              <p className="budget-inline-note">
                This cannot tell old manual rows from old imported rows, so choose the date carefully.
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
              {freshStartLoading ? "Cleaning..." : "Delete Old History"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => navigate("/import")}
            >
              Reconcile This Month
            </button>
          </div>

          {freshStartMessage && <div className="bulk-message-box">{freshStartMessage}</div>}
          {freshStartError && <p className="error-text">{freshStartError}</p>}
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Repeating Money Patterns</h2>
            <p>Repeated expenses and income detected from your written transaction history in this scope.</p>
          </div>

          {recurringPatterns.length === 0 ? (
            <div className="empty-state">
              <p>No strong repeating income or expense patterns were detected yet.</p>
            </div>
          ) : (
            <div className="recurring-charges-grid">
              {recurringPatterns.map((item) => (
                <div key={`${item.description}-${item.latest_date}`} className="recurring-charge-card">
                  <div className="recurring-charge-top">
                    <div>
                      <h3>{item.description}</h3>
                      <p>{item.type === "income" ? "Income" : "Expense"} | {item.category}</p>
                    </div>
                    <div className="recurring-charge-badges">
                      <span className={getRecurringPriorityClass(item.review_priority)}>
                        {item.review_priority === "high"
                          ? "Review first"
                          : item.review_priority === "medium"
                            ? "Worth reviewing"
                            : "Stable"}
                      </span>
                      <span className="budget-status budget-status-risk">
                        {Math.round(Number(item.confidence || 0) * 100)}% match
                      </span>
                    </div>
                  </div>

                  <div className="recurring-charge-metrics">
                    <div>
                      <span>Average</span>
                      <strong>${Number(item.average_amount || 0).toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>Annualized</span>
                      <strong>${Number(item.annualized_amount || 0).toFixed(2)}</strong>
                    </div>
                    <div>
                      <span>Occurrences</span>
                      <strong>{item.occurrences}</strong>
                    </div>
                  </div>

                  <p className="budget-inline-note">
                    Latest {item.type === "income" ? "income" : "expense"}: ${Number(item.latest_amount || 0).toFixed(2)} on {item.latest_date}
                  </p>
                  {item.next_expected_date && (
                    <p className="budget-inline-note">
                      Next expected around {item.next_expected_date}
                    </p>
                  )}
                  {item.latest_change_percent != null && (
                    <p className="budget-inline-note">
                      Latest change: {item.latest_change_percent > 0 ? "+" : ""}
                      {Number(item.latest_change_percent).toFixed(1)}% vs usual amount
                    </p>
                  )}
                  {item.review_reason && (
                    <p className="recurring-charge-reason">{item.review_reason}</p>
                  )}
                  <div className="recurring-charge-actions">
                    <button
                      type="button"
                      className="secondary-button recurring-charge-action"
                      onClick={() => applyRecurringFilter(item)}
                    >
                      Show matching transactions
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Smart Categorization</h2>
            <p>Analyze uncategorized rows and clean up legacy category labels so future suggestions stay consistent.</p>
          </div>

          <div className="smart-actions-row">
            <button
              type="button"
              className="smart-action-button"
              onClick={handleBulkAnalyze}
              disabled={bulkLoading}
            >
              {bulkLoading ? "Analyzing..." : "Analyze Uncategorized Transactions"}
            </button>

            <button
              type="button"
              className="smart-apply-button"
              onClick={handleBulkApply}
              disabled={bulkApplying || bulkSuggestions.length === 0}
            >
              {bulkApplying ? "Applying..." : "Apply Suggested Categories"}
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={handleNormalizeCategories}
              disabled={normalizingCategories}
            >
              {normalizingCategories ? "Normalizing..." : "Normalize Existing Categories"}
            </button>
          </div>

          {bulkMessage && <div className="bulk-message-box">{bulkMessage}</div>}

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
                          Current: <strong>{item.current_category}</strong> {"->"} Suggested: <strong>{item.suggested_category}</strong>
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

                    <p className="bulk-suggestion-meta">Type: {item.type}</p>
                    {item.matched_keyword && (
                      <p className="bulk-suggestion-meta">
                        Matched keyword: <strong>{item.matched_keyword}</strong>
                      </p>
                    )}
                    <p className="bulk-suggestion-meta">{item.reason}</p>
                  </div>
                );
              })}
            </div>
          )}

          {!bulkLoading && bulkSuggestions.length === 0 && !bulkMessage && (
            <div className="empty-state">
              <p>No bulk suggestions yet. Run analysis to scan uncategorized rows.</p>
            </div>
          )}
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Transaction Filters</h2>
            <p>
              Showing {filteredTransactions.length} of {transactions.length} transaction
              {transactions.length === 1 ? "" : "s"} in this account view.
            </p>
          </div>

          <div className="filter-bar">
            <div>
              <label>Type</label>
              <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <option value="">All</option>
                <option value="income">Income</option>
                <option value="expense">Expense</option>
              </select>
            </div>

            <div>
              <label>Month</label>
              <select value={monthFilter} onChange={(e) => setMonthFilter(e.target.value)}>
                <option value="">All</option>
                {availableMonths.map((month) => (
                  <option key={month} value={month}>{month}</option>
                ))}
              </select>
            </div>

            <div>
              <label>Category</label>
              <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                <option value="">All</option>
                {availableCategories.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
            </div>

            <div>
              <label>Description</label>
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Search merchant or note"
              />
            </div>
          </div>

          <div className="smart-actions-row recurring-filter-actions">
            <button
              type="button"
              className={recurringOnlyFilter ? "smart-action-button" : "secondary-button"}
              onClick={() => setRecurringOnlyFilter((current) => !current)}
            >
              {recurringOnlyFilter ? "Showing Recurring Matches" : "Only Recurring Matches"}
            </button>

            {(typeFilter || monthFilter || categoryFilter || searchFilter || recurringOnlyFilter) && (
              <button type="button" className="secondary-button" onClick={clearFilters}>
                Clear Filters
              </button>
            )}
          </div>

          {(searchFilter || recurringOnlyFilter) && (
            <p className="budget-inline-note recurring-filter-note">
              {recurringOnlyFilter
                ? `Showing likely repeating money patterns${searchFilter ? ` matching "${searchFilter}".` : "."}`
                : `Filtering descriptions for "${searchFilter}".`}
            </p>
          )}
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <h2>Transaction Table</h2>
            <p>Your daily written transactions and any missing statement rows you chose to import.</p>
          </div>

          {filteredTransactions.length === 0 ? (
            <div className="empty-state">
              <p>
                {transactions.length === 0
                  ? "No transactions found in this account view yet."
                  : "Transactions exist, but the current filters are hiding them."}
              </p>
              {transactions.length === 0 ? (
                <button className="secondary-button" onClick={() => navigate("/dashboard")}>
                  Add Today&apos;s Transaction
                </button>
              ) : (
                <button className="secondary-button" onClick={clearFilters}>
                  Clear Filters
                </button>
              )}
            </div>
          ) : (
            <div className="transactions-table-wrapper">
              <table className="transactions-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Category</th>
                    <th>Description</th>
                    <th>Amount</th>
                    <th>Account ID</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransactions.map((transaction) => {
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
                              <option value="income">Income</option>
                              <option value="expense">Expense</option>
                            </select>
                          ) : transaction.type}
                        </td>

                        <td>
                          {isEditing ? (
                            <input type="text" value={editForm.category} onChange={(e) => setEditForm({ ...editForm, category: e.target.value })} />
                          ) : transaction.category}
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
                          ) : transaction.account_id}
                        </td>

                        <td>
                          <div className="transaction-actions-inline">
                            {isEditing ? (
                              <>
                                <button className="edit-button" onClick={() => saveEdit(transaction.id)}>
                                  Save
                                </button>
                                <button className="secondary-button" onClick={cancelEdit}>
                                  Cancel
                                </button>
                              </>
                            ) : (
                              <>
                                <button className="edit-button" onClick={() => startEdit(transaction)}>
                                  Edit
                                </button>
                                <button className="delete-button" onClick={() => handleDelete(transaction.id)}>
                                  Delete
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
          )}
        </div>
      </div>
    </div>
  );
}

export default TransactionsPage;
