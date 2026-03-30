import { useEffect, useMemo, useState } from "react";
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

    return Array.from(months).sort();
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

  const handleCsvUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

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
            <p>Upload a bank-style CSV file to import transactions automatically.</p>
          </div>

          <div style={{ marginTop: "12px" }}>
            <input
              type="file"
              accept=".csv"
              onChange={handleCsvUpload}
              disabled={isUploading}
            />
          </div>

          {isUploading && (
            <div
              style={{
                marginTop: "16px",
                padding: "14px 16px",
                borderRadius: "12px",
                backgroundColor: "#eff6ff",
                border: "1px solid #bfdbfe",
                color: "#1d4ed8",
              }}
            >
              Uploading and processing CSV...
            </div>
          )}

          {importResult && (
            <div
              style={{
                marginTop: "16px",
                padding: "16px",
                borderRadius: "14px",
                backgroundColor: "#ecfdf5",
                border: "1px solid #a7f3d0",
                color: "#065f46",
              }}
            >
              <h3 style={{ marginTop: 0, marginBottom: "10px" }}>
                Import Result
              </h3>
              <p style={{ margin: "6px 0" }}>{importResult.message}</p>
              <p style={{ margin: "6px 0" }}>
                Imported: <strong>{importResult.imported ?? 0}</strong>
              </p>
              <p style={{ margin: "6px 0" }}>
                Duplicates skipped:{" "}
                <strong>{importResult.duplicates_skipped ?? 0}</strong>
              </p>
              <p style={{ margin: "6px 0" }}>
                Invalid rows skipped:{" "}
                <strong>{importResult.invalid_rows_skipped ?? 0}</strong>
              </p>
            </div>
          )}

          {importError && (
            <div
              style={{
                marginTop: "16px",
                padding: "16px",
                borderRadius: "14px",
                backgroundColor: "#fef2f2",
                border: "1px solid #fecaca",
                color: "#991b1b",
              }}
            >
              <h3 style={{ marginTop: 0, marginBottom: "10px" }}>
                Import Error
              </h3>
              <p style={{ margin: 0 }}>{importError}</p>
            </div>
          )}
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