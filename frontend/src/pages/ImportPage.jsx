import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import { ALL_ACCOUNTS_VALUE } from "../services/accountStorage";

const ALLOWED_TRANSACTION_TYPES = new Set(["expense", "income"]);
const FREE_BATCH_IMPORT_FILE_LIMIT = 6;
const RECEIPT_IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "webp"]);
const todayIsoDate = () => new Date().toISOString().slice(0, 10);

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

const validateReceiptDraft = (draft) => {
  const fieldIssues = {
    amount: !Number.isFinite(Number(draft?.amount)) || Number(draft?.amount) <= 0,
    category: !draft?.category?.trim(),
    description: !draft?.description?.trim(),
    date: !isValidIsoDate(draft?.date || ""),
    type: !ALLOWED_TRANSACTION_TYPES.has(draft?.type),
  };

  const messages = [];

  if (fieldIssues.amount) messages.push("enter an amount greater than 0");
  if (fieldIssues.category) messages.push("add a category");
  if (fieldIssues.description) messages.push("add a description");
  if (fieldIssues.date) messages.push("fix the date");
  if (fieldIssues.type) messages.push("choose income or expense");

  return {
    fieldIssues,
    messages,
  };
};

const buildManualPreviewRow = (fallbackDate) => ({
  date: fallbackDate || todayIsoDate(),
  description: "",
  amount: "",
  type: "expense",
  category: "other",
  source_line: "Added manually during review.",
  is_duplicate: false,
  duplicate_reason: null,
});

const buildPreviewDuplicateKey = (row, validation) => {
  if (validation.messages.length > 0) {
    return null;
  }

  return JSON.stringify({
    date: row.date,
    description: row.description.trim().toLowerCase(),
    amount: Number(row.amount).toFixed(2),
    type: row.type.trim().toLowerCase(),
    category: row.category.trim().toLowerCase(),
  });
};

const getPreviewRowConfidence = (row) => {
  const confidence = Number(row?.confidence);
  if (!Number.isFinite(confidence) || confidence <= 0) {
    return null;
  }
  return Math.max(0, Math.min(confidence, 1));
};

const formatConfidencePercent = (confidence) =>
  confidence == null ? "Not scored" : `${Math.round(confidence * 100)}%`;

const getPreviewCategoryConfidence = (row) => {
  const confidence = Number(row?.category_confidence);
  if (!Number.isFinite(confidence) || confidence <= 0) {
    return null;
  }
  return Math.max(0, Math.min(confidence, 1));
};

const getFileExtension = (fileName = "") => fileName.split(".").pop()?.toLowerCase() || "";

const isReceiptImageFile = (file) => RECEIPT_IMAGE_EXTENSIONS.has(getFileExtension(file.name));

const formatSelectedFilesLabel = (files) => {
  if (files.length === 0) {
    return "";
  }
  if (files.length === 1) {
    return files[0].name;
  }

  const visibleNames = files.slice(0, 3).map((file) => file.name).join(", ");
  const remainingCount = files.length - 3;
  return `${files.length} files selected: ${visibleNames}${remainingCount > 0 ? `, +${remainingCount} more` : ""}`;
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
  const [previewFilter, setPreviewFilter] = useState("all");

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);
  const normalizedError = error.trim().toLowerCase();
  const importErrorGuidance = (() => {
    if (normalizedError.includes("upgrade to premium")) {
      return {
        title: "Premium batch import",
        items: [
          `Free users can import ${FREE_BATCH_IMPORT_FILE_LIMIT} statement files per batch.`,
          "Split larger uploads into smaller batches for now, or upgrade when Premium billing is enabled.",
          "Premium will unlock larger statement batches for faster setup and deeper history building.",
        ],
      };
    }

    if (
      normalizedError.includes("no selectable text") ||
      normalizedError.includes("image-only or scanned")
    ) {
      return {
        title: "What to try next",
        items: [
          "The backend now tries free local OCR first for scanned or screenshot-style PDFs.",
          "If it still fails, the backend server needs Tesseract OCR installed, or OpenAI vision OCR can be enabled as a stronger paid fallback.",
          "Original downloadable statement PDFs still import more reliably than camera scans or screenshot-to-PDF exports.",
        ],
      };
    }

    if (normalizedError.includes("no transaction rows were recognized")) {
      return {
        title: "What to try next",
        items: [
          "This file had readable text, but the row layout did not match a supported parser pattern yet.",
          "If your bank offers another PDF layout or a CSV export, try that version first.",
          "Keep this statement available for future parser tuning if the same bank format keeps failing.",
        ],
      };
    }

    if (
      normalizedError.includes("receipt ocr is not enabled yet") ||
      normalizedError.includes("valid openai_api_key")
    ) {
      return {
        title: "What to try next",
        items: [
          "Add a valid OPENAI_API_KEY in the backend environment to enable receipt scanning.",
          "Use CSV or PDF statement import for statements, or add receipt transactions manually until OCR is enabled.",
          "Once OCR is enabled, the app will return a draft transaction for review before saving.",
        ],
      };
    }

    return null;
  })();
  const detectedPreviewRows = importResult?.status === "table_review" ? importResult.preview_rows || [] : [];
  const removedPreviewCount = Math.max(detectedPreviewRows.length - previewRows.length, 0);
  const previewRowValidations = previewRows.map((row) => validatePreviewRow(row));
  const previewDuplicateCounts = previewRows.reduce((counts, row, index) => {
    const duplicateKey = buildPreviewDuplicateKey(row, previewRowValidations[index]);
    if (!duplicateKey) {
      return counts;
    }

    return {
      ...counts,
      [duplicateKey]: (counts[duplicateKey] || 0) + 1,
    };
  }, {});
  const previewRowItems = previewRows.map((row, index) => {
    const confidence = getPreviewRowConfidence(row);
    const categoryConfidence = getPreviewCategoryConfidence(row);
    const categoryReason =
      row.category_reason ||
      (categoryConfidence != null && categoryConfidence < 0.75
        ? "Category confidence is low; verify this label before importing."
        : null);
    const confidenceReason =
      row.review_reason ||
      (confidence != null && confidence < 0.75
        ? "Parser confidence is low; verify this row before importing."
        : categoryReason);

    return {
      row,
      index,
      validation: previewRowValidations[index],
      confidence,
      categoryConfidence,
      categoryReason,
      confidenceReason,
      duplicateReason:
        row.is_duplicate && row.duplicate_reason
          ? row.duplicate_reason
          : (() => {
              const duplicateKey = buildPreviewDuplicateKey(row, previewRowValidations[index]);
              if (duplicateKey && previewDuplicateCounts[duplicateKey] > 1) {
                return "Duplicate of another row in this preview.";
              }
              return null;
            })(),
    };
  });
  const invalidPreviewRowCount = previewRowValidations.filter(
    (validation) => validation.messages.length > 0
  ).length;
  const duplicatePreviewRowCount = previewRowItems.filter((item) => item.duplicateReason).length;
  const matchedPreviewRowCount = previewRowItems.filter(
    (item) => item.row.reconciliation_status === "matched"
  ).length;
  const missingPreviewRowCount = previewRowItems.filter(
    ({ duplicateReason, validation }) => !duplicateReason && validation.messages.length === 0
  ).length;
  const repeatingPreviewRowCount = previewRowItems.filter(
    (item) => item.row.is_repeating_pattern
  ).length;
  const confidencePreviewRowCount = previewRowItems.filter(
    (item) => item.confidenceReason
  ).length;
  const manualPreviewRowCount = previewRows.filter(
    (row) => row.source_line === "Added manually during review."
  ).length;
  const previewImportDisabled =
    confirmingPreview || missingPreviewRowCount === 0 || invalidPreviewRowCount > 0;
  const receiptDraftValidation = validateReceiptDraft(receiptDraft);
  const filteredPreviewRows = previewRowItems.filter(
    ({ duplicateReason, validation, confidenceReason, row }) => {
      if (previewFilter === "missing") {
        return !duplicateReason && validation.messages.length === 0;
      }
      if (previewFilter === "needs_review") {
        return validation.messages.length > 0;
      }
      if (previewFilter === "duplicates") {
        return Boolean(duplicateReason);
      }
      if (previewFilter === "repeating") {
        return Boolean(row.is_repeating_pattern);
      }
      if (previewFilter === "confidence") {
        return Boolean(confidenceReason);
      }
      return true;
    }
  );

  const clearAll = () => {
    setSelectedFileName("");
    setImportResult(null);
    setPreviewRows([]);
    setReceiptDraft(null);
    setError("");
    setPreviewFilter("all");
  };

  const handleChooseFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileUpload = async (event) => {
    const selectedFiles = Array.from(event.target.files || []);
    if (!selectedFiles.length) return;

    if (!normalizedAccountId) {
      setError("Please select a specific account before importing a file.");
      event.target.value = "";
      return;
    }

    if (selectedFiles.length > FREE_BATCH_IMPORT_FILE_LIMIT) {
      setSelectedFileName(formatSelectedFilesLabel(selectedFiles));
      setImportResult(null);
      setPreviewRows([]);
      setReceiptDraft(null);
      setError(
        `Free users can upload up to ${FREE_BATCH_IMPORT_FILE_LIMIT} bank statements in one try. Upgrade to Premium to import more at once.`
      );
      event.target.value = "";
      return;
    }

    if (selectedFiles.length > 1 && selectedFiles.some(isReceiptImageFile)) {
      setSelectedFileName(formatSelectedFilesLabel(selectedFiles));
      setImportResult(null);
      setPreviewRows([]);
      setReceiptDraft(null);
      setError("Batch import supports CSV and PDF bank statements. Upload receipt images one at a time.");
      event.target.value = "";
      return;
    }

    setSelectedFileName(formatSelectedFilesLabel(selectedFiles));
    setImportResult(null);
    setPreviewRows([]);
    setReceiptDraft(null);
    setError("");
    setLoading(true);

    const formData = new FormData();
    formData.append("account_id", String(normalizedAccountId));
    const uploadPath =
      selectedFiles.length === 1 ? "/transactions/import/file" : "/transactions/import/files";

    if (selectedFiles.length === 1) {
      formData.append("file", selectedFiles[0]);
    } else {
      selectedFiles.forEach((file) => {
        formData.append("files", file);
      });
    }

    try {
      const response = await api.post(uploadPath, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      const data = response.data;
      setImportResult(data);

      if (data.status === "table_review") {
        setPreviewRows(data.preview_rows || []);
        setPreviewFilter("all");
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
              is_duplicate: false,
              duplicate_reason: null,
              matched_transaction_id: null,
              reconciliation_status: "missing",
              reconciliation_reason: null,
              is_repeating_pattern: false,
              repeating_pattern_type: null,
              repeating_pattern_reason: null,
              repeating_pattern_occurrences: 0,
              repeating_pattern_average_amount: null,
              repeating_pattern_cadence: null,
              repeating_pattern_confidence: null,
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
    setPreviewFilter("all");
  };

  const handleRemoveDuplicatePreviewRows = () => {
    setPreviewRows((prev) =>
      prev.filter((_, index) => !previewRowItems[index]?.duplicateReason)
    );
  };

  const handleRemoveNeedsReviewRows = () => {
    setPreviewRows((prev) =>
      prev.filter((_, index) => previewRowValidations[index]?.messages.length === 0)
    );
  };

  const handleAddManualPreviewRow = () => {
    const fallbackDate =
      previewRows[previewRows.length - 1]?.date ||
      detectedPreviewRows[detectedPreviewRows.length - 1]?.date ||
      todayIsoDate();

    setPreviewRows((prev) => [...prev, buildManualPreviewRow(fallbackDate)]);
    setPreviewFilter("all");
  };

  const handleConfirmPreviewImport = async () => {
    const rowsToImport = previewRowItems
      .filter(({ duplicateReason, validation }) => !duplicateReason && validation.messages.length === 0)
      .map(({ row }) => row);

    if (!normalizedAccountId || rowsToImport.length === 0) return;

    try {
      setConfirmingPreview(true);
      const response = await api.post("/transactions/import/confirm-preview", {
        account_id: normalizedAccountId,
        rows: rowsToImport,
      });

      setImportResult({
        detected_type: importResult?.detected_type || "pdf_statement",
        status: "completed",
        message: response.data.message,
        import_summary: {
          imported: response.data.imported || 0,
          duplicates_skipped:
            (response.data.duplicates_skipped || 0) + Math.max(previewRows.length - rowsToImport.length, 0),
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
              Use daily transactions as your source of truth, then upload the month-end statement to find what you missed.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/transactions")}>
              Back to Transactions
            </button>
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              Dashboard
            </button>
            <button className="secondary-button" onClick={() => navigate("/money-map")}>
              Money Map
            </button>
          </div>
        </div>

        <div className="filter-card">
          <div className="section-header">
            <h2>Import Destination</h2>
            <p>Select the account where imported transactions should go.</p>
          </div>

          <AccountSelector
            value={selectedAccountId}
            onChange={setSelectedAccountId}
            allowAll={false}
            label="Target Account"
            persistSelection={false}
          />
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>Upload Files</h2>
            <p>
              Upload up to {FREE_BATCH_IMPORT_FILE_LIMIT} CSV or PDF bank statements in one try. The app marks rows
              already written and lets you import only the missed transactions.
            </p>
          </div>

          <div className="import-upload-card">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.pdf,.jpg,.jpeg,.png,.webp"
              multiple
              onChange={handleFileUpload}
              disabled={loading}
              className="hidden-file-input"
            />

            <div className="import-upload-top">
              <div>
                <h3>Smart Import</h3>
                <p>
                  Select this month&apos;s statement to reconcile your daily entries. More than{" "}
                  {FREE_BATCH_IMPORT_FILE_LIMIT} files in one batch is a Premium workflow.
                </p>
              </div>

              <button
                type="button"
                className="import-upload-button"
                onClick={handleChooseFile}
                disabled={loading}
              >
                {loading ? "Processing..." : "Choose Files"}
              </button>
            </div>

            <div className="import-upload-meta">
              <span className="import-file-label">Selected files:</span>
              <span className="import-file-name">{selectedFileName || "No files selected yet"}</span>
            </div>

            {loading && (
              <div className="import-info-box">
                <strong>Processing upload...</strong>
                <p>Detecting each file type and running the correct import pipeline.</p>
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

                {importErrorGuidance && (
                  <div className="import-error-guidance">
                    <strong>{importErrorGuidance.title}</strong>
                    <ul className="assistant-list">
                      {importErrorGuidance.items.map((item, index) => (
                        <li key={`import-error-guidance-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
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

                <div className="budget-section-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => navigate("/money-map")}
                  >
                    Open Money Map
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => navigate("/transactions")}
                  >
                    Review Transactions
                  </button>
                </div>
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
                className={receiptDraftValidation.fieldIssues.amount ? "import-invalid-input" : ""}
                value={receiptDraft.amount ?? ""}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, amount: e.target.value })}
                placeholder="Amount"
              />

              <input
                type="text"
                className={receiptDraftValidation.fieldIssues.category ? "import-invalid-input" : ""}
                value={receiptDraft.category}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, category: e.target.value })}
                placeholder="Category"
              />

              <input
                type="text"
                className={receiptDraftValidation.fieldIssues.description ? "import-invalid-input" : ""}
                value={receiptDraft.description}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, description: e.target.value })}
                placeholder="Description"
              />

              <input
                type="date"
                className={receiptDraftValidation.fieldIssues.date ? "import-invalid-input" : ""}
                value={receiptDraft.date || ""}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, date: e.target.value })}
              />

              <select
                className={receiptDraftValidation.fieldIssues.type ? "import-invalid-input" : ""}
                value={receiptDraft.type}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, type: e.target.value })}
              >
                <option value="expense">Expense</option>
                <option value="income">Income</option>
              </select>

              <button
                type="button"
                onClick={handleSaveReceiptDraft}
                disabled={savingDraft || receiptDraftValidation.messages.length > 0}
              >
                {savingDraft ? "Saving..." : "Save Transaction"}
              </button>
            </div>

            {receiptDraftValidation.messages.length > 0 && (
              <div className="import-validation-box">
                <strong>Receipt draft still needs fixes</strong>
                <p>Before saving, please {receiptDraftValidation.messages.join(", ")}.</p>
              </div>
            )}

            {receiptDraft.raw_text_preview && (
              <div className="receipt-preview-box">
                <strong>OCR Text Preview</strong>
                <p>{receiptDraft.raw_text_preview}</p>
              </div>
            )}

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
              <h2>Review Statement Rows</h2>
              <p>Matched rows are already in your app. Missing rows are the ones you may have forgotten to write.</p>
            </div>

            <div className="import-preview-toolbar">
              <div className="import-preview-summary">
                <strong>{previewRows.length} row{previewRows.length === 1 ? "" : "s"} currently selected</strong>
                <p>
                  {invalidPreviewRowCount > 0
                    ? `${invalidPreviewRowCount} row${invalidPreviewRowCount === 1 ? "" : "s"} still need attention before you can import.`
                    : matchedPreviewRowCount > 0
                    ? `${matchedPreviewRowCount} row${matchedPreviewRowCount === 1 ? "" : "s"} already match your written transactions. ${missingPreviewRowCount} missing row${missingPreviewRowCount === 1 ? "" : "s"} can be imported if needed.`
                    : repeatingPreviewRowCount > 0
                    ? `${repeatingPreviewRowCount} row${repeatingPreviewRowCount === 1 ? "" : "s"} look repetitive based on your written history.`
                    : confidencePreviewRowCount > 0
                    ? `${confidencePreviewRowCount} row${confidencePreviewRowCount === 1 ? "" : "s"} should get a quick parser confidence check before importing.`
                    : removedPreviewCount > 0
                    ? `${removedPreviewCount} removed row${removedPreviewCount === 1 ? "" : "s"} will be skipped when you confirm.`
                    : manualPreviewRowCount > 0
                    ? `${manualPreviewRowCount} manual row${manualPreviewRowCount === 1 ? "" : "s"} were added during review.`
                    : "Remove any bad detections before importing, or edit the values directly in the table."}
                </p>
              </div>

              <div className="import-preview-actions">
                <button
                  type="button"
                  className="smart-apply-button import-preview-primary-action"
                  onClick={handleConfirmPreviewImport}
                  disabled={previewImportDisabled}
                >
                  {confirmingPreview
                    ? "Importing..."
                    : `Import Missing Rows (${missingPreviewRowCount})`}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={handleAddManualPreviewRow}
                  disabled={confirmingPreview}
                >
                  Add Manual Row
                </button>
                {invalidPreviewRowCount > 0 && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleRemoveNeedsReviewRows}
                    disabled={confirmingPreview}
                  >
                    Remove Needs Review
                  </button>
                )}
                {(removedPreviewCount > 0 || duplicatePreviewRowCount > 0 || detectedPreviewRows.length > 0) && (
                  <>
                  {duplicatePreviewRowCount > 0 && (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={handleRemoveDuplicatePreviewRows}
                      disabled={confirmingPreview}
                    >
                      Remove Already Written
                    </button>
                  )}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleRestorePreviewRows}
                    disabled={confirmingPreview}
                  >
                    Restore Detected Rows
                  </button>
                  </>
                )}
              </div>
            </div>

            <div className="import-preview-stats-grid">
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">Missing</span>
                <strong>{missingPreviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">Needs Review</span>
                <strong>{invalidPreviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">Already Written</span>
                <strong>{matchedPreviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">Repeating</span>
                <strong>{repeatingPreviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">Confidence</span>
                <strong>{confidencePreviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">Removed</span>
                <strong>{removedPreviewCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">Manual</span>
                <strong>{manualPreviewRowCount}</strong>
              </div>
            </div>

            <div className="import-preview-filters" role="tablist" aria-label="Preview row filters">
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "all" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("all")}
              >
                All ({previewRows.length})
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "missing" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("missing")}
              >
                Missing ({missingPreviewRowCount})
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "needs_review" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("needs_review")}
              >
                Needs Review ({invalidPreviewRowCount})
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "duplicates" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("duplicates")}
              >
                Already Written ({duplicatePreviewRowCount})
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "repeating" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("repeating")}
              >
                Repeating ({repeatingPreviewRowCount})
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "confidence" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("confidence")}
              >
                Confidence Check ({confidencePreviewRowCount})
              </button>
            </div>

            {invalidPreviewRowCount > 0 && (
              <div className="import-validation-box">
                <strong>
                  {invalidPreviewRowCount} row{invalidPreviewRowCount === 1 ? "" : "s"} need fixes
                </strong>
                <p>Review the highlighted fields before confirming import. Invalid rows are blocked on the client now.</p>
              </div>
            )}

            {duplicatePreviewRowCount > 0 && (
              <div className="import-duplicate-box">
                <strong>
                  {matchedPreviewRowCount || duplicatePreviewRowCount} already written or duplicate row{(matchedPreviewRowCount || duplicatePreviewRowCount) === 1 ? "" : "s"}
                </strong>
                <p>
                  These rows matched your written transactions or another row in this preview. Keep them visible for review or remove them; the backend skips them during import.
                </p>
              </div>
            )}

            {confidencePreviewRowCount > 0 && (
              <div className="import-confidence-box">
                <strong>
                  {confidencePreviewRowCount} parser confidence check{confidencePreviewRowCount === 1 ? "" : "s"}
                </strong>
                <p>
                  These rows are still importable, but the parser is telling us to verify the amount or income/expense direction before saving.
                </p>
              </div>
            )}

            {repeatingPreviewRowCount > 0 && (
              <div className="import-info-box">
                <strong>
                  {repeatingPreviewRowCount} repeating money pattern{repeatingPreviewRowCount === 1 ? "" : "s"} detected
                </strong>
                <p>
                  These rows look similar to expenses or income you already wrote before. Use this to confirm monthly habits, subscriptions, payroll, or recurring transfers.
                </p>
              </div>
            )}

            {previewRows.length > 0 && filteredPreviewRows.length > 0 ? (
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
                    {filteredPreviewRows.map(
                      ({
                        row,
                        index,
                        validation,
                        duplicateReason,
                        confidence,
                        categoryConfidence,
                        categoryReason,
                        confidenceReason,
                      }) => {
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
                              {confidence != null && (
                                <div className="import-confidence-row">
                                  <span>Parser confidence</span>
                                  <strong>{formatConfidencePercent(confidence)}</strong>
                                </div>
                              )}
                              {categoryConfidence != null && (
                                <div className="import-confidence-row">
                                  <span>Category confidence</span>
                                  <strong>{formatConfidencePercent(categoryConfidence)}</strong>
                                </div>
                              )}
                              {confidenceReason && (
                                <div className="import-confidence-note">{confidenceReason}</div>
                              )}
                              {categoryReason && categoryReason !== confidenceReason && (
                                <div className="import-confidence-note">{categoryReason}</div>
                              )}
                              {duplicateReason && (
                                <div className="import-duplicate-note">{duplicateReason}</div>
                              )}
                              {row.repeating_pattern_reason && (
                                <div className="import-confidence-note">
                                  {row.repeating_pattern_reason}
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
                              {row.source_line === "Added manually during review." && (
                                <span className="import-row-status import-row-status-manual">Manual row</span>
                              )}
                              {duplicateReason && (
                                <span className="import-row-status import-row-status-duplicate">
                                  {row.reconciliation_status === "matched" ? "Already written" : "Duplicate"}
                                </span>
                              )}
                              {confidenceReason && (
                                <span className="import-row-status import-row-status-confidence">Check parser</span>
                              )}
                              {row.is_repeating_pattern && (
                                <span className="import-row-status import-row-status-confidence">
                                  Repeating {row.repeating_pattern_type}
                                </span>
                              )}
                              {validation.messages.length > 0 && (
                                <span className="import-row-status import-row-status-warning">Needs review</span>
                              )}
                            </td>
                          </tr>
                        );
                      }
                    )}
                  </tbody>
                </table>
              </div>
            ) : previewRows.length > 0 ? (
              <div className="empty-state import-preview-empty">
                <p>No rows match the current filter.</p>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setPreviewFilter("all")}
                >
                  Show All Rows
                </button>
              </div>
            ) : (
              <div className="empty-state import-preview-empty">
                <p>No rows are currently selected for import.</p>
                <div className="import-preview-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleAddManualPreviewRow}
                    disabled={confirmingPreview}
                  >
                    Add Manual Row
                  </button>
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
              </div>
            )}

            <div className="smart-actions-row">
              <button
                type="button"
                className="smart-apply-button"
                onClick={handleConfirmPreviewImport}
                disabled={previewImportDisabled}
              >
                {confirmingPreview ? "Importing..." : "Import Missing Rows"}
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
