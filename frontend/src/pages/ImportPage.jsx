import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import { ALL_ACCOUNTS_VALUE } from "../services/accountStorage";

const ALLOWED_TRANSACTION_TYPES = new Set(["expense", "income"]);

const isValidIsoDate = (value) => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }

  const parsed = new Date(`${value}T00:00:00`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
};

const validatePreviewRow = (row) => {
  const fieldIssues = {
    date: !isValidIsoDate(row.date),
    description: !row.description?.trim(),
    amount: !Number.isFinite(Number(row.amount)) || Number(row.amount) <= 0,
    type: !ALLOWED_TRANSACTION_TYPES.has(row.type),
    category: !row.category?.trim(),
  };

  const messages = [];

  if (fieldIssues.date) messages.push("fix the date");
  if (fieldIssues.description) messages.push("add a description");
  if (fieldIssues.amount) messages.push("enter an amount greater than 0");
  if (fieldIssues.type) messages.push("choose income or expense");
  if (fieldIssues.category) messages.push("add a category");

  return {
    fieldIssues,
    messages,
  };
};

function ImportPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [selectedAccountId, setSelectedAccountId] = useState(ALL_ACCOUNTS_VALUE);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [importResult, setImportResult] = useState(null);
  const [previewRows, setPreviewRows] = useState([]);
  const [receiptDraft, setReceiptDraft] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirmingPreview, setConfirmingPreview] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);
  const detectedPreviewRows = importResult?.status === "table_review" ? importResult.preview_rows || [] : [];
  const removedPreviewCount = Math.max(detectedPreviewRows.length - previewRows.length, 0);
  const previewRowValidations = previewRows.map((row) => validatePreviewRow(row));
  const invalidPreviewRowCount = previewRowValidations.filter(
    (validation) => validation.messages.length > 0
  ).length;

  const clearAll = () => {
    setSelectedFileName("");
    setImportResult(null);
    setPreviewRows([]);
    setReceiptDraft(null);
    setError("");
  };

  const handleChooseFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!normalizedAccountId) {
      setError("Please select a specific account before importing a file.");
      return;
    }

    setSelectedFileName(file.name);
    setImportResult(null);
    setPreviewRows([]);
    setReceiptDraft(null);
    setError("");
    setLoading(true);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("account_id", String(normalizedAccountId));

    try {
      const response = await api.post("/transactions/import/file", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      const data = response.data;
      setImportResult(data);

      if (data.status === "table_review") {
        setPreviewRows(data.preview_rows || []);
      }

      if (data.status === "draft_review") {
        setReceiptDraft(data.draft_transaction || null);
      }
    } catch (uploadError) {
      if (!handleApiAuthError(uploadError, navigate)) {
        setError(uploadError?.response?.data?.detail || "Import failed.");
      }
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  };

  const handlePreviewRowChange = (index, field, value) => {
    setPreviewRows((prev) =>
      prev.map((row, rowIndex) =>
        rowIndex === index
          ? {
              ...row,
              [field]: field === "amount" ? (value === "" ? "" : Number(value)) : value,
            }
          : row
      )
    );
  };

  const handleRemovePreviewRow = (index) => {
    setPreviewRows((prev) => prev.filter((_, rowIndex) => rowIndex !== index));
  };

  const handleRestorePreviewRows = () => {
    setPreviewRows(detectedPreviewRows);
  };

  const handleConfirmPreviewImport = async () => {
    if (!normalizedAccountId || previewRows.length === 0) return;

    try {
      setConfirmingPreview(true);
      const response = await api.post("/transactions/import/confirm-preview", {
        account_id: normalizedAccountId,
        rows: previewRows,
      });

      setImportResult({
        detected_type: "pdf_statement",
        status: "completed",
        message: response.data.message,
        import_summary: {
          imported: response.data.imported || 0,
          duplicates_skipped: response.data.duplicates_skipped || 0,
          invalid_rows_skipped: response.data.invalid_rows_skipped || 0,
        },
        notes: [],
      });
      setPreviewRows([]);
    } catch (confirmError) {
      if (!handleApiAuthError(confirmError, navigate)) {
        setError(confirmError?.response?.data?.detail || "Failed to confirm preview import.");
      }
    } finally {
      setConfirmingPreview(false);
    }
  };

  const handleSaveReceiptDraft = async () => {
    if (!receiptDraft || !normalizedAccountId) return;

    try {
      setSavingDraft(true);
      await api.post("/transactions/", {
        amount: Number(receiptDraft.amount),
        category: receiptDraft.category,
        description: receiptDraft.description,
        date: receiptDraft.date,
        type: receiptDraft.type,
        account_id: normalizedAccountId,
      });

      setImportResult({
        detected_type: "receipt_image",
        status: "completed",
        message: "Scanned receipt transaction saved successfully.",
        import_summary: {
          imported: 1,
          duplicates_skipped: 0,
          invalid_rows_skipped: 0,
        },
        notes: receiptDraft.notes || [],
      });
      setReceiptDraft(null);
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setError(saveError?.response?.data?.detail || "Failed to save scanned receipt.");
      }
    } finally {
      setSavingDraft(false);
    }
  };

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">Smart Spending Analyzer</p>
            <h1>Smart Import</h1>
            <p className="hero-subtitle">
              Upload one file and the app will detect whether it is a CSV statement, PDF statement, or receipt image.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/transactions")}>
              Back to Transactions
            </button>
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              Dashboard
            </button>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Import Destination</h2>
            <p>Select the account where imported transactions should go.</p>
          </div>

          <AccountSelector onChange={setSelectedAccountId} allowAll={false} label="Target Account" />
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>Upload File</h2>
            <p>
              Supported files: CSV statements, PDF statements, and receipt images (JPG, PNG, WEBP).
            </p>
          </div>

          <div className="import-upload-card">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.pdf,.jpg,.jpeg,.png,.webp"
              onChange={handleFileUpload}
              disabled={loading}
              className="hidden-file-input"
            />

            <div className="import-upload-top">
              <div>
                <h3>Smart Import</h3>
                <p>The app automatically detects the file type and starts the right workflow.</p>
              </div>

              <button
                type="button"
                className="import-upload-button"
                onClick={handleChooseFile}
                disabled={loading}
              >
                {loading ? "Processing..." : "Choose File"}
              </button>
            </div>

            <div className="import-upload-meta">
              <span className="import-file-label">Selected file:</span>
              <span className="import-file-name">{selectedFileName || "No file selected yet"}</span>
            </div>

            {loading && (
              <div className="import-info-box">
                <strong>Processing file...</strong>
                <p>Detecting file type and running the correct import pipeline.</p>
              </div>
            )}

            {error && (
              <div className="import-error">
                <div className="import-message-header">
                  <div>
                    <h3>Import failed</h3>
                    <p>{error}</p>
                  </div>
                  <button
                    type="button"
                    className="dismiss-message-button dismiss-error-button"
                    onClick={clearAll}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}

            {importResult && importResult.status === "completed" && (
              <div className="import-success">
                <div className="import-message-header">
                  <div>
                    <h3>Import completed</h3>
                    <p>{importResult.message}</p>
                  </div>
                  <button type="button" className="dismiss-message-button" onClick={clearAll}>
                    Clear
                  </button>
                </div>

                {importResult.import_summary && (
                  <div className="import-stats-grid">
                    <div className="import-stat-card">
                      <span className="import-stat-label">Imported</span>
                      <strong>{importResult.import_summary.imported ?? 0}</strong>
                    </div>

                    <div className="import-stat-card">
                      <span className="import-stat-label">Duplicates skipped</span>
                      <strong>{importResult.import_summary.duplicates_skipped ?? 0}</strong>
                    </div>

                    <div className="import-stat-card">
                      <span className="import-stat-label">Invalid rows skipped</span>
                      <strong>{importResult.import_summary.invalid_rows_skipped ?? 0}</strong>
                    </div>
                  </div>
                )}

                {importResult.notes?.length > 0 && (
                  <div className="receipt-preview-box">
                    <strong>Notes</strong>
                    <ul className="assistant-list">
                      {importResult.notes.map((item, index) => (
                        <li key={`import-note-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {importResult?.status === "draft_review" && receiptDraft && (
          <div className="dashboard-card large-card">
            <div className="section-header">
              <h2>Review Receipt Draft</h2>
              <p>Review the extracted transaction before saving it.</p>
            </div>

            <div className="transaction-form">
              <input
                type="number"
                step="0.01"
                value={receiptDraft.amount ?? ""}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, amount: e.target.value })}
                placeholder="Amount"
              />

              <input
                type="text"
                value={receiptDraft.category}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, category: e.target.value })}
                placeholder="Category"
              />

              <input
                type="text"
                value={receiptDraft.description}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, description: e.target.value })}
                placeholder="Description"
              />

              <input
                type="date"
                value={receiptDraft.date || ""}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, date: e.target.value })}
              />

              <select
                value={receiptDraft.type}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, type: e.target.value })}
              >
                <option value="expense">Expense</option>
                <option value="income">Income</option>
              </select>

              <button type="button" onClick={handleSaveReceiptDraft} disabled={savingDraft}>
                {savingDraft ? "Saving..." : "Save Transaction"}
              </button>
            </div>

            {receiptDraft.notes?.length > 0 && (
              <div className="receipt-preview-box">
                <strong>Notes</strong>
                <ul className="assistant-list">
                  {receiptDraft.notes.map((item, index) => (
                    <li key={`draft-note-${index}`}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {importResult?.status === "table_review" && (
          <div className="dashboard-card large-card">
            <div className="section-header">
              <h2>Review PDF Statement Rows</h2>
              <p>Review detected rows, remove anything incorrect, then import the final list.</p>
            </div>

            <div className="import-preview-toolbar">
              <div className="import-preview-summary">
                <strong>{previewRows.length} row{previewRows.length === 1 ? "" : "s"} ready to import</strong>
                <p>
                  {invalidPreviewRowCount > 0
                    ? `${invalidPreviewRowCount} row${invalidPreviewRowCount === 1 ? "" : "s"} still need attention before you can import.`
                    : removedPreviewCount > 0
                    ? `${removedPreviewCount} removed row${removedPreviewCount === 1 ? "" : "s"} will be skipped when you confirm.`
                    : "Remove any bad detections before importing, or edit the values directly in the table."}
                </p>
              </div>

              {removedPreviewCount > 0 && (
                <div className="import-preview-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleRestorePreviewRows}
                    disabled={confirmingPreview}
                  >
                    Restore Detected Rows
                  </button>
                </div>
              )}
            </div>

            {invalidPreviewRowCount > 0 && (
              <div className="import-validation-box">
                <strong>
                  {invalidPreviewRowCount} row{invalidPreviewRowCount === 1 ? "" : "s"} need fixes
                </strong>
                <p>Review the highlighted fields before confirming import. Invalid rows are blocked on the client now.</p>
              </div>
            )}

            {previewRows.length > 0 ? (
              <div className="transactions-table-wrapper">
                <table className="transactions-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Description</th>
                      <th>Amount</th>
                      <th>Type</th>
                      <th>Category</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, index) => {
                      const validation = previewRowValidations[index];

                      return (
                        <tr key={`preview-row-${index}`}>
                          <td>
                            <input
                              type="date"
                              className={validation.fieldIssues.date ? "import-invalid-input" : ""}
                              value={row.date}
                              onChange={(e) => handlePreviewRowChange(index, "date", e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              className={validation.fieldIssues.description ? "import-invalid-input" : ""}
                              value={row.description}
                              onChange={(e) => handlePreviewRowChange(index, "description", e.target.value)}
                            />
                            {row.source_line && (
                              <div className="import-source-line">
                                <span className="import-source-label">Parsed From</span>
                                <code>{row.source_line}</code>
                              </div>
                            )}
                            {validation.messages.length > 0 && (
                              <div className="import-row-issues">
                                Needs review: {validation.messages.join(", ")}.
                              </div>
                            )}
                          </td>
                          <td>
                            <input
                              type="number"
                              step="0.01"
                              className={validation.fieldIssues.amount ? "import-invalid-input" : ""}
                              value={row.amount}
                              onChange={(e) => handlePreviewRowChange(index, "amount", e.target.value)}
                            />
                          </td>
                          <td>
                            <select
                              className={validation.fieldIssues.type ? "import-invalid-input" : ""}
                              value={row.type}
                              onChange={(e) => handlePreviewRowChange(index, "type", e.target.value)}
                            >
                              <option value="expense">Expense</option>
                              <option value="income">Income</option>
                            </select>
                          </td>
                          <td>
                            <input
                              type="text"
                              className={validation.fieldIssues.category ? "import-invalid-input" : ""}
                              value={row.category}
                              onChange={(e) => handlePreviewRowChange(index, "category", e.target.value)}
                            />
                          </td>
                          <td className="import-actions-cell">
                            <button
                              type="button"
                              className="import-remove-row-button"
                              onClick={() => handleRemovePreviewRow(index)}
                              disabled={confirmingPreview}
                            >
                              Remove
                            </button>
                            {validation.messages.length > 0 && (
                              <span className="import-row-status import-row-status-warning">Needs review</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state import-preview-empty">
                <p>No rows are currently selected for import.</p>
                {detectedPreviewRows.length > 0 && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleRestorePreviewRows}
                    disabled={confirmingPreview}
                  >
                    Restore Detected Rows
                  </button>
                )}
              </div>
            )}

            <div className="smart-actions-row">
              <button
                type="button"
                className="smart-apply-button"
                onClick={handleConfirmPreviewImport}
                disabled={confirmingPreview || previewRows.length === 0 || invalidPreviewRowCount > 0}
              >
                {confirmingPreview ? "Importing..." : "Confirm Import"}
              </button>
            </div>

            {importResult.notes?.length > 0 && (
              <div className="receipt-preview-box">
                <strong>Notes</strong>
                <ul className="assistant-list">
                  {importResult.notes.map((item, index) => (
                    <li key={`preview-note-${index}`}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default ImportPage;
