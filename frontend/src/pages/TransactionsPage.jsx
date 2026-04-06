import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import { ALL_ACCOUNTS_VALUE } from "../services/accountStorage";

function TransactionsPage() {
  const [transactions, setTransactions] = useState([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState(ALL_ACCOUNTS_VALUE);
  const [loading, setLoading] = useState(true);

  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState("");

  const [bulkSuggestions, setBulkSuggestions] = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkApplying, setBulkApplying] = useState(false);
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

  const fileInputRef = useRef(null);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);

  useEffect(() => {
    setTypeFilter(searchParams.get("type") || "");
    setMonthFilter(searchParams.get("month") || "");
    setCategoryFilter(searchParams.get("category") || "");
  }, [searchParams]);

  const fetchTransactions = async () => {
    try {
      const response = await api.get("/transactions/", {
        params: {
          account_id: normalizedAccountId,
        },
      });
      setTransactions(response.data);
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

  const filteredTransactions = useMemo(() => {
    return transactions
      .filter((transaction) => {
        const transactionMonth = new Date(transaction.date).toISOString().slice(0, 7);

        if (typeFilter && transaction.type !== typeFilter) return false;
        if (monthFilter && transactionMonth !== monthFilter) return false;
        if (categoryFilter && transaction.category !== categoryFilter) return false;

        return true;
      })
      .sort((a, b) => new Date(b.date) - new Date(a.date));
  }, [transactions, typeFilter, monthFilter, categoryFilter]);

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

  const handleChooseFile = () => {
    fileInputRef.current?.click();
  };

  const clearImportMessages = () => {
    setImportResult(null);
    setImportError("");
  };

  const handleStatementUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!normalizedAccountId) {
      setImportError("Please select a specific account before importing a statement.");
      return;
    }

    setSelectedFileName(file.name);
    setImportResult(null);
    setImportError("");
    setIsUploading(true);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("account_id", String(normalizedAccountId));

    try {
      const response = await api.post("/transactions/import/statement", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      setImportResult(response.data);
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setImportError(error.response?.data?.detail || "Statement import failed");
      }
    } finally {
      setIsUploading(false);
      event.target.value = "";
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
              Browse, filter, import monthly statements, and manage transactions by account.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              Back to Dashboard
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

        <div className="filter-card">
          <div className="section-header">
            <h2>Monthly Statement Import</h2>
            <p>
              Upload a statement CSV. The importer reads date, description, amount, income/expense, and categorizes rows automatically.
            </p>
          </div>

          <div className="import-upload-card">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleStatementUpload}
              disabled={isUploading}
              className="hidden-file-input"
            />

            <div className="import-upload-top">
              <div>
                <h3>Statement Import</h3>
                <p>
                  Supported now: <strong>CSV bank/card statements</strong>. You must choose a specific account first.
                </p>
              </div>

              <button
                type="button"
                className="import-upload-button"
                onClick={handleChooseFile}
                disabled={isUploading}
              >
                {isUploading ? "Uploading..." : "Choose Statement CSV"}
              </button>
            </div>

            <div className="import-upload-meta">
              <span className="import-file-label">Selected file:</span>
              <span className="import-file-name">{selectedFileName || "No file selected yet"}</span>
            </div>

            {isUploading && (
              <div className="import-info-box">
                <strong>Processing statement...</strong>
                <p>Your statement is being parsed, categorized, and checked for duplicates.</p>
              </div>
            )}

            {importResult && (
              <div className="import-success">
                <div className="import-message-header">
                  <div>
                    <h3>Import completed</h3>
                    <p>{importResult.message}</p>
                  </div>
                  <button type="button" className="dismiss-message-button" onClick={clearImportMessages}>
                    Dismiss
                  </button>
                </div>

                <div className="import-stats-grid">
                  <div className="import-stat-card">
                    <span className="import-stat-label">Imported</span>
                    <strong>{importResult.imported ?? 0}</strong>
                  </div>
                  <div className="import-stat-card">
                    <span className="import-stat-label">Duplicates skipped</span>
                    <strong>{importResult.duplicates_skipped ?? 0}</strong>
                  </div>
                  <div className="import-stat-card">
                    <span className="import-stat-label">Invalid rows skipped</span>
                    <strong>{importResult.invalid_rows_skipped ?? 0}</strong>
                  </div>
                </div>
              </div>
            )}

            {importError && (
              <div className="import-error">
                <div className="import-message-header">
                  <div>
                    <h3>Import failed</h3>
                    <p>{importError}</p>
                  </div>
                  <button
                    type="button"
                    className="dismiss-message-button dismiss-error-button"
                    onClick={clearImportMessages}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Smart Categorization</h2>
            <p>Analyze transactions still labeled as Other, Misc, Uncategorized, or Unknown.</p>
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
          </div>

          {bulkMessage && <div className="bulk-message-box">{bulkMessage}</div>}

          {bulkSuggestions.length > 0 && (
            <div className="bulk-suggestions-list">
              {bulkSuggestions.map((item) => (
                <div key={item.transaction_id} className="bulk-suggestion-card">
                  <div className="bulk-suggestion-top">
                    <div>
                      <h3>{item.description}</h3>
                      <p>
                        Current: <strong>{item.current_category}</strong> → Suggested: <strong>{item.suggested_category}</strong>
                      </p>
                    </div>

                    <span className="bulk-confidence-pill">
                      {Math.round(item.confidence * 100)}%
                    </span>
                  </div>

                  <p className="bulk-suggestion-meta">Type: {item.type}</p>
                  <p className="bulk-suggestion-meta">{item.reason}</p>
                </div>
              ))}
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
            <p>Filter the full transaction table by type, month, and category.</p>
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
          </div>
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <h2>Transaction Table</h2>
            <p>Detailed records of your income and expense entries.</p>
          </div>

          {filteredTransactions.length === 0 ? (
            <div className="empty-state"><p>No transactions found.</p></div>
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