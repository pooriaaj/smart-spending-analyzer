import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";

function TransactionsPage() {
  const [transactions, setTransactions] = useState([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState("");

  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const fetchTransactions = async () => {
    try {
      const response = await api.get("/transactions/");
      setTransactions(response.data);
    } catch (error) {
      console.error("Failed to load transactions:", error);
      localStorage.removeItem("token");
      navigate("/", { replace: true });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, []);

  const availableMonths = useMemo(() => {
    const months = new Set(
      transactions.map((transaction) =>
        new Date(transaction.date).toISOString().slice(0, 7)
      )
    );

    return Array.from(months).sort().reverse();
  }, [transactions]);

  const filteredTransactions = useMemo(() => {
    return transactions
      .filter((transaction) => {
        if (typeFilter && transaction.type !== typeFilter) {
          return false;
        }

        if (monthFilter) {
          const transactionMonth = new Date(transaction.date)
            .toISOString()
            .slice(0, 7);

          if (transactionMonth !== monthFilter) {
            return false;
          }
        }

        return true;
      })
      .sort((a, b) => new Date(b.date) - new Date(a.date));
  }, [transactions, typeFilter, monthFilter]);

  const handleDelete = async (transactionId) => {
    try {
      await api.delete(`/transactions/${transactionId}`);
      fetchTransactions();
    } catch (error) {
      console.error("Failed to delete transaction:", error);
    }
  };

  const handleChooseFile = () => {
    fileInputRef.current?.click();
  };

  const handleDismissImportMessage = () => {
    setImportResult(null);
    setImportError("");
  };

  const handleCsvUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setSelectedFileName(file.name);
    setImportResult(null);
    setImportError("");
    setIsUploading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await api.post("/transactions/import/csv", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      setImportResult(response.data);
      await fetchTransactions();
    } catch (err) {
      setImportError(err.response?.data?.detail || "CSV import failed");
    } finally {
      setIsUploading(false);
      e.target.value = "";
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
              Browse, filter, manage, and import your full transaction history.
            </p>
          </div>

          <div className="header-actions">
            <button
              className="secondary-button"
              onClick={() => navigate("/dashboard")}
            >
              Back to Dashboard
            </button>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Import Transactions</h2>
            <p>
              Upload a bank-style CSV file to import transactions automatically.
            </p>
          </div>

          <div className="import-upload-card">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleCsvUpload}
              disabled={isUploading}
              className="hidden-file-input"
            />

            <div className="import-upload-top">
              <div>
                <h3>CSV Import</h3>
                <p>
                  Required columns: <strong>date, description, amount, type, category</strong>
                </p>
              </div>

              <button
                type="button"
                className="import-upload-button"
                onClick={handleChooseFile}
                disabled={isUploading}
              >
                {isUploading ? "Uploading..." : "Choose CSV File"}
              </button>
            </div>

            <div className="import-upload-meta">
              <span className="import-file-label">Selected file:</span>
              <span className="import-file-name">
                {selectedFileName || "No file selected yet"}
              </span>
            </div>

            <p className="import-helper-text">
              Re-uploading the same CSV will skip duplicate rows automatically.
            </p>

            {isUploading && (
              <div className="import-info-box">
                <strong>Processing file...</strong>
                <p>Your CSV is being uploaded and validated.</p>
              </div>
            )}

            {importResult && (
              <div className="import-success">
                <div className="import-message-header">
                  <div>
                    <h3>Import completed</h3>
                    <p>{importResult.message}</p>
                  </div>

                  <button
                    type="button"
                    className="dismiss-message-button"
                    onClick={handleDismissImportMessage}
                  >
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
                    onClick={handleDismissImportMessage}
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
            <h2>Transaction Filters</h2>
            <p>Filter the full transaction table by type and month.</p>
          </div>

          <div className="filter-bar">
            <div>
              <label>Type</label>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
              >
                <option value="">All</option>
                <option value="income">Income</option>
                <option value="expense">Expense</option>
              </select>
            </div>

            <div>
              <label>Month</label>
              <select
                value={monthFilter}
                onChange={(e) => setMonthFilter(e.target.value)}
              >
                <option value="">All</option>
                {availableMonths.map((month) => (
                  <option key={month} value={month}>
                    {month}
                  </option>
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
            <div className="empty-state">
              <p>No transactions found.</p>
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
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransactions.map((transaction) => (
                    <tr key={transaction.id}>
                      <td>{transaction.date}</td>
                      <td>{transaction.type}</td>
                      <td>{transaction.category}</td>
                      <td>{transaction.description}</td>
                      <td
                        className={
                          transaction.type === "income"
                            ? "income-text"
                            : "expense-text"
                        }
                      >
                        {transaction.type === "income" ? "+" : "-"}$
                        {transaction.amount.toFixed(2)}
                      </td>
                      <td>
                        <button
                          className="delete-button"
                          onClick={() => handleDelete(transaction.id)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
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