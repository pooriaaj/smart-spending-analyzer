import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { IconCloudUpload } from "@tabler/icons-react";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import PageHeader from "../components/PageHeader";
import { ALL_ACCOUNTS_VALUE } from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import { getApiErrorMessage, getApiSuccessMessage } from "../utils/errorUtils";

const ALLOWED_TRANSACTION_TYPES = new Set(["expense", "income"]);
const RECEIPT_IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "webp"]);
const todayIsoDate = () => new Date().toISOString().slice(0, 10);
const MERCHANT_ALIAS_PATTERNS = [
  [/sqdc\d*/i, "sqdc"],
  [/orange\s+mart/i, "orange mart"],
  [/hazelview\s+prop/i, "hazelview prop"],
  [/apple\.?com\/?bill/i, "apple com bill"],
  [/tim\s*hortons?/i, "tim hortons"],
  [/mcdonald'?s?/i, "mcdonalds"],
  [/supermarche\s+pa/i, "supermarche pa"],
  [/pharmaprix/i, "pharmaprix"],
  [/depanneur\s+macka/i, "depanneur macka"],
  [/concordiau|concordia\s+u/i, "concordia university"],
  [/stm\s+angrignon|(?:^|\s)stm(?:\s|$)/i, "stm"],
  [/smoke\s+king/i, "smoke king"],
];
const AMOUNT_SENSITIVE_PREVIEW_MERCHANTS = new Set([
  "amazon",
  "amazon marketplace",
  "apple",
  "apple com bill",
  "bell",
  "costco",
  "dollarama",
  "google",
  "orange mart",
  "paypal",
  "rogers",
  "shoppers drug mart",
  "walmart",
]);
const MERCHANT_NOISE_WORDS = new Set([
  "achat",
  "amount",
  "balance",
  "card",
  "carte",
  "contactless",
  "de",
  "debit",
  "interac",
  "ligne",
  "mtl",
  "online",
  "paiem",
  "payment",
  "periodic",
  "periodiq",
  "purchase",
  "regl",
  "source",
  "tf",
  "virement",
]);

const isValidIsoDate = (value) => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }

  const parsed = new Date(`${value}T00:00:00`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
};

const isUsableCategoryName = (value = "") => {
  const normalized = String(value || "").trim().toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
  if (!normalized) return false;
  if (["other", "misc", "uncategorized", "unknown"].includes(normalized)) return true;

  return normalized.replace(/[^a-z0-9]+/g, "").length >= 2;
};

const validatePreviewRow = (row, t) => {
  const hasCategory = Boolean(row.category?.trim());
  const categoryTooShort = hasCategory && !isUsableCategoryName(row.category);
  const fieldIssues = {
    date: !isValidIsoDate(row.date),
    description: !row.description?.trim(),
    amount: !Number.isFinite(Number(row.amount)) || Number(row.amount) <= 0,
    type: !ALLOWED_TRANSACTION_TYPES.has(row.type),
    category: !hasCategory || categoryTooShort,
  };

  const messages = [];

  if (fieldIssues.date) messages.push(t("import.fixDate"));
  if (fieldIssues.description) messages.push(t("import.addDescription"));
  if (fieldIssues.amount) messages.push(t("import.amountGreaterThanZero"));
  if (fieldIssues.type) messages.push(t("import.chooseIncomeExpense"));
  if (!hasCategory) messages.push(t("import.addCategory"));
  if (categoryTooShort) messages.push(t("import.useFullCategoryName"));

  return {
    fieldIssues,
    messages,
  };
};

const validateReceiptDraft = (draft, t) => {
  const fieldIssues = {
    amount: !Number.isFinite(Number(draft?.amount)) || Number(draft?.amount) <= 0,
    category: !draft?.category?.trim(),
    description: !draft?.description?.trim(),
    date: !isValidIsoDate(draft?.date || ""),
    type: !ALLOWED_TRANSACTION_TYPES.has(draft?.type),
  };

  const messages = [];

  if (fieldIssues.amount) messages.push(t("import.amountGreaterThanZero"));
  if (fieldIssues.category) messages.push(t("import.addCategory"));
  if (fieldIssues.description) messages.push(t("import.addDescription"));
  if (fieldIssues.date) messages.push(t("import.fixDate"));
  if (fieldIssues.type) messages.push(t("import.chooseIncomeExpense"));

  return {
    fieldIssues,
    messages,
  };
};

const buildManualPreviewRow = (fallbackDate, t) => ({
  date: fallbackDate || todayIsoDate(),
  description: "",
  amount: "",
  type: "expense",
  category: "other",
  source_line: t("import.manualSourceLine"),
  category_review_required: false,
  category_review_reason: null,
  is_duplicate: false,
  duplicate_reason: null,
});

const normalizeMerchantText = (value = "") =>
  String(value || "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\b\d+[a-z]*\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const normalizePreviewAmount = (amount) => {
  const normalizedAmount = Math.abs(Number(amount));
  return Number.isFinite(normalizedAmount) && normalizedAmount > 0 ? normalizedAmount : null;
};

const getPreviewAmountBucket = (amount) => {
  const normalizedAmount = normalizePreviewAmount(amount);
  if (normalizedAmount === null) return "";

  if (normalizedAmount < 20) return String(Math.max(1, Math.round(normalizedAmount / 5) * 5));
  if (normalizedAmount < 100) return String(Math.round(normalizedAmount / 10) * 10);
  if (normalizedAmount < 500) return String(Math.round(normalizedAmount / 25) * 25);
  return String(Math.round(normalizedAmount / 100) * 100);
};

const buildPreviewSimilarityKey = (row, merchantKey) => {
  const baseKey = `${row.type || "expense"}:${merchantKey}`;
  if (!AMOUNT_SENSITIVE_PREVIEW_MERCHANTS.has(merchantKey)) {
    return baseKey;
  }

  const amountBucket = getPreviewAmountBucket(row.amount);
  return amountBucket ? `${baseKey}:amount-${amountBucket}` : baseKey;
};

const getPreviewSimilarityKey = (row) => {
  const candidateText = `${row.description || ""} ${row.source_line || ""}`;
  for (const [pattern, alias] of MERCHANT_ALIAS_PATTERNS) {
    if (pattern.test(candidateText)) {
      return buildPreviewSimilarityKey(row, alias);
    }
  }

  const tokens = normalizeMerchantText(candidateText)
    .split(" ")
    .filter((token) => token.length >= 3 && !MERCHANT_NOISE_WORDS.has(token));

  if (tokens.length === 0) return "";
  return buildPreviewSimilarityKey(row, tokens.slice(0, 2).join(" "));
};

const getSimilarityDisplayName = (similarityKey = "") => {
  const [, merchant = similarityKey] = similarityKey.split(":");
  return merchant
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
};

const getPreviewRowConfidence = (row) => {
  const confidence = Number(row?.confidence);
  if (!Number.isFinite(confidence) || confidence <= 0) {
    return null;
  }
  return Math.max(0, Math.min(confidence, 1));
};

const formatConfidencePercent = (confidence, t) =>
  confidence == null ? t("common.notScored") : `${Math.round(confidence * 100)}%`;

const formatPreviewReason = (reason, t, fallbackKey) => {
  if (!reason) return null;

  const lowered = String(reason).toLowerCase();

  if (lowered.includes("learned category memory")) {
    return t("import.reasonLearnedMemory");
  }

  if (
    lowered.includes("merchant/category rule") ||
    lowered.includes("normalized merchant") ||
    lowered.includes("built-in category rule")
  ) {
    return t("import.reasonCategoryRule");
  }

  if (lowered.includes("income rule") || lowered.includes("deposit rule")) {
    return t("import.reasonIncomeRule");
  }

  if (lowered.includes("no learned memory") || lowered.includes("no stronger rule")) {
    return t("import.reasonNeedsTeaching");
  }

  if (lowered.includes("already written") || lowered.includes("duplicate")) {
    return t("import.reasonAlreadyWritten");
  }

  if (lowered.includes("confidence")) {
    return t("import.reasonConfidenceReview");
  }

  return t(fallbackKey);
};

const getPreviewCategoryConfidence = (row) => {
  const confidence = Number(row?.category_confidence);
  if (!Number.isFinite(confidence) || confidence <= 0) {
    return null;
  }
  return Math.max(0, Math.min(confidence, 1));
};

const isCategoryReviewRequired = (row) => Boolean(row?.category_review_required);

const getFileExtension = (fileName = "") => fileName.split(".").pop()?.toLowerCase() || "";

const isReceiptImageFile = (file) => RECEIPT_IMAGE_EXTENSIONS.has(getFileExtension(file.name));

const formatSelectedFilesLabel = (files, t) => {
  if (files.length === 0) {
    return "";
  }
  if (files.length === 1) {
    return files[0].name;
  }

  const visibleNames = files.slice(0, 3).map((file) => file.name).join(", ");
  const remainingCount = files.length - 3;
  return t("import.filesSelected", {
    count: files.length,
    names: visibleNames,
    more: remainingCount > 0 ? t("import.moreFiles", { count: remainingCount }) : "",
  });
};

const buildSafeUploadDiagnostics = (error, files, uploadPath) => ({
  uploadPath,
  status: error?.response?.status || null,
  requestId:
    error?.response?.data?.request_id ||
    error?.response?.headers?.["x-request-id"] ||
    error?.response?.headers?.["X-Request-ID"] ||
    null,
  stage: error?.response?.data?.stage || null,
  fileCount: files.length,
  files: files.map((file) => ({
    extension: getFileExtension(file.name) || "unknown",
    type: file.type || "unknown",
    size: file.size,
  })),
});

const formatDiagnosticFileSize = (size) => {
  const numericSize = Number(size);
  if (!Number.isFinite(numericSize) || numericSize < 0) {
    return "unknown size";
  }

  if (numericSize < 1024) {
    return `${numericSize} B`;
  }

  return `${(numericSize / 1024).toFixed(1)} KB`;
};

const formatDiagnosticValue = (value, t) => {
  if (value === null || value === undefined || value === "") {
    return t("import.diagnosticUnknown");
  }

  return String(value);
};

const formatDiagnosticFile = (file, index) =>
  `${index + 1}. ${String(file.extension || "unknown").toUpperCase()} · ${
    file.type || "unknown type"
  } · ${formatDiagnosticFileSize(file.size)}`;

const buildSafeUploadDiagnosticsText = (diagnostics) => {
  if (!diagnostics) {
    return "";
  }

  return [
    "Zero2Asset import diagnostics",
    `Upload path: ${diagnostics.uploadPath || "unknown"}`,
    `HTTP status: ${diagnostics.status || "unknown"}`,
    `Request ID: ${diagnostics.requestId || "unknown"}`,
    `Import stage: ${diagnostics.stage || "unknown"}`,
    `File count: ${diagnostics.fileCount || 0}`,
    "Files:",
    ...(diagnostics.files || []).map(formatDiagnosticFile),
  ].join("\n");
};

const logImportUploadError = (diagnostics) => {
  console.error("Import upload failed", diagnostics);
};

function ImportPage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const fileInputRef = useRef(null);

  const [selectedAccountId, setSelectedAccountId] = useState(ALL_ACCOUNTS_VALUE);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [importResult, setImportResult] = useState(null);
  const [previewRows, setPreviewRows] = useState([]);
  const [receiptDraft, setReceiptDraft] = useState(null);
  const [error, setError] = useState("");
  const [uploadDiagnostics, setUploadDiagnostics] = useState(null);
  const [diagnosticsCopied, setDiagnosticsCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirmingPreview, setConfirmingPreview] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [previewFilter, setPreviewFilter] = useState("all");
  const [previewGroupCategoryDrafts, setPreviewGroupCategoryDrafts] = useState({});
  const manualSourceLine = t("import.manualSourceLine");

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);
  const normalizedError = error.trim().toLowerCase();
  const importErrorGuidance = (() => {
    if (normalizedError.includes("upgrade to premium")) {
      return {
        title: t("import.premiumBatchTitle"),
        items: [
          t("import.premiumBatchItem1"),
          t("import.premiumBatchItem2"),
          t("import.premiumBatchItem3"),
        ],
      };
    }

    if (
      normalizedError.includes("no selectable text") ||
      normalizedError.includes("image-only or scanned") ||
      normalizedError.includes("tesseract was not found")
    ) {
      return {
        title: t("import.tryNextTitle"),
        items: [
          t("import.ocrGuidance1"),
          t("import.ocrGuidance2"),
          t("import.ocrGuidance3"),
          t("import.ocrGuidance4"),
        ],
      };
    }

    if (normalizedError.includes("no transaction rows were recognized")) {
      return {
        title: t("import.tryNextTitle"),
        items: [
          t("import.parserGuidance1"),
          t("import.parserGuidance2"),
          t("import.parserGuidance3"),
        ],
      };
    }

    if (
      normalizedError.includes("receipt ocr is not enabled yet") ||
      normalizedError.includes("valid openai_api_key")
    ) {
      return {
        title: t("import.tryNextTitle"),
        items: [
          t("import.receiptGuidance1"),
          t("import.receiptGuidance2"),
          t("import.receiptGuidance3"),
        ],
      };
    }

    return null;
  })();
  const skippedImportRowCount = importResult?.import_summary?.invalid_rows_skipped ?? 0;
  const skippedImportRowDetails = importResult?.import_summary?.invalid_row_details || [];
  const detectedPreviewRows = importResult?.status === "table_review" ? importResult.preview_rows || [] : [];
  const removedPreviewCount = Math.max(detectedPreviewRows.length - previewRows.length, 0);
  const previewRowValidations = previewRows.map((row) => validatePreviewRow(row, t));
  const previewRowItems = previewRows.map((row, index) => {
    const confidence = getPreviewRowConfidence(row);
    const categoryConfidence = getPreviewCategoryConfidence(row);
    const categoryReviewRequired = isCategoryReviewRequired(row);
    const categoryReason = formatPreviewReason(
      row.category_review_reason || row.category_reason,
      t,
      "import.reasonCategoryReview"
    ) ||
      (categoryConfidence != null && categoryConfidence < 0.75
        ? t("import.lowCategoryConfidenceReason")
        : null);
    const confidenceReason = formatPreviewReason(
      row.review_reason,
      t,
      "import.reasonConfidenceReview"
    ) ||
      (confidence != null && confidence < 0.75
        ? t("import.lowParserConfidenceReason")
        : categoryReason);

    return {
      row,
      index,
      validation: previewRowValidations[index],
      confidence,
      categoryConfidence,
      categoryReason,
      categoryReviewRequired,
      confidenceReason,
      duplicateReason:
        row.is_duplicate && row.duplicate_reason
          ? formatPreviewReason(row.duplicate_reason, t, "import.reasonAlreadyWritten")
          : null,
    };
  });
  const previewLearningGroups = Object.values(
    previewRowItems.reduce((groups, item) => {
      const { row, index, duplicateReason, validation, categoryReviewRequired } = item;
      const similarityKey = getPreviewSimilarityKey(row);
      if (!similarityKey || duplicateReason || validation.messages.length > 0) {
        return groups;
      }

      if (!groups[similarityKey]) {
        const amountValue = normalizePreviewAmount(row.amount);
        groups[similarityKey] = {
          key: similarityKey,
          displayName: getSimilarityDisplayName(similarityKey),
          type: row.type || "expense",
          isAmountSensitive: similarityKey.includes(":amount-"),
          rowIndexes: [],
          examples: [],
          categories: {},
          needsReviewCount: 0,
          totalAmount: 0,
          amountMin: amountValue,
          amountMax: amountValue,
        };
      }

      const group = groups[similarityKey];
      const amountValue = normalizePreviewAmount(row.amount);
      const category = String(row.category || "other").trim() || "other";
      group.rowIndexes.push(index);
      group.categories[category] = (group.categories[category] || 0) + 1;
      group.totalAmount += Math.abs(Number(row.amount) || 0);
      if (amountValue !== null) {
        group.amountMin = group.amountMin === null ? amountValue : Math.min(group.amountMin, amountValue);
        group.amountMax = group.amountMax === null ? amountValue : Math.max(group.amountMax, amountValue);
      }
      if (categoryReviewRequired || category.toLowerCase() === "other") {
        group.needsReviewCount += 1;
      }
      if (row.description && !group.examples.includes(row.description) && group.examples.length < 3) {
        group.examples.push(row.description);
      }

      return groups;
    }, {})
  )
    .map((group) => {
      const categoryEntries = Object.entries(group.categories).sort((a, b) => b[1] - a[1]);
      const nonOtherCategory = categoryEntries.find(([category]) => category.toLowerCase() !== "other");
      return {
        ...group,
        count: group.rowIndexes.length,
        suggestedCategory: (nonOtherCategory || categoryEntries[0] || ["other"])[0],
        hasMixedCategories: categoryEntries.length > 1,
      };
    })
    .filter(
      (group) =>
        group.count >= 2 &&
        (group.needsReviewCount > 0 || group.hasMixedCategories)
    )
    .sort((a, b) => b.needsReviewCount - a.needsReviewCount || b.count - a.count);
  const invalidPreviewRowCount = previewRowValidations.filter(
    (validation) => validation.messages.length > 0
  ).length;
  const duplicatePreviewRowCount = previewRowItems.filter((item) => item.duplicateReason).length;
  const matchedPreviewRowCount = previewRowItems.filter(
    (item) => item.row.reconciliation_status === "matched"
  ).length;
  const categoryReviewRowCount = previewRowItems.filter(
    (item) => item.categoryReviewRequired && !item.duplicateReason
  ).length;
  const importReadyPreviewRowCount = previewRowItems.filter(
    ({ duplicateReason, validation, categoryReviewRequired }) =>
      !duplicateReason && validation.messages.length === 0 && !categoryReviewRequired
  ).length;
  const confidencePreviewRowCount = previewRowItems.filter(
    (item) => item.confidenceReason
  ).length;
  const manualPreviewRowCount = previewRows.filter(
    (row) => row.source_line === manualSourceLine || row.source_line === "Added manually during review."
  ).length;
  const previewImportDisabled =
    confirmingPreview || importReadyPreviewRowCount === 0 || invalidPreviewRowCount > 0;
  const receiptDraftValidation = validateReceiptDraft(receiptDraft, t);
  const filteredPreviewRows = previewRowItems.filter(
    ({ duplicateReason, validation, confidenceReason, categoryReviewRequired }) => {
      if (previewFilter === "missing") {
        return !duplicateReason && validation.messages.length === 0 && !categoryReviewRequired;
      }
      if (previewFilter === "needs_review") {
        return validation.messages.length > 0 || categoryReviewRequired;
      }
      if (previewFilter === "duplicates") {
        return Boolean(duplicateReason);
      }
      if (previewFilter === "confidence") {
        return Boolean(confidenceReason || categoryReviewRequired);
      }
      return true;
    }
  );

  const clearAll = () => {
    setSelectedFileName("");
    setImportResult(null);
    setPreviewRows([]);
    setPreviewGroupCategoryDrafts({});
    setReceiptDraft(null);
    setError("");
    setUploadDiagnostics(null);
    setDiagnosticsCopied(false);
    setPreviewFilter("all");
  };

  const handleChooseFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileUpload = async (event) => {
    const selectedFiles = Array.from(event.target.files || []);
    if (!selectedFiles.length) return;

    if (!normalizedAccountId) {
      setError(t("import.accountRequired"));
      setUploadDiagnostics(null);
      setDiagnosticsCopied(false);
      event.target.value = "";
      return;
    }

    if (selectedFiles.length > 1 && selectedFiles.some(isReceiptImageFile)) {
      setSelectedFileName(formatSelectedFilesLabel(selectedFiles, t));
      setImportResult(null);
      setPreviewRows([]);
      setReceiptDraft(null);
      setError(t("import.receiptBatchError"));
      setUploadDiagnostics(null);
      setDiagnosticsCopied(false);
      event.target.value = "";
      return;
    }

    setSelectedFileName(formatSelectedFilesLabel(selectedFiles, t));
    setImportResult(null);
    setPreviewRows([]);
    setPreviewGroupCategoryDrafts({});
    setReceiptDraft(null);
    setError("");
    setUploadDiagnostics(null);
    setDiagnosticsCopied(false);
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
      setUploadDiagnostics(null);
      setDiagnosticsCopied(false);

      if (data.status === "table_review") {
        setPreviewRows(data.preview_rows || []);
        setPreviewFilter("all");
      }

      if (data.status === "draft_review") {
        setReceiptDraft(data.draft_transaction || null);
      }
    } catch (uploadError) {
      if (!handleApiAuthError(uploadError, navigate)) {
        const diagnostics = buildSafeUploadDiagnostics(uploadError, selectedFiles, uploadPath);
        logImportUploadError(diagnostics);
        setUploadDiagnostics(diagnostics);
        setDiagnosticsCopied(false);
        setError(getApiErrorMessage(uploadError, t("import.importFallbackFailed")));
      }
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  };

  const handlePreviewRowChange = (index, field, value) => {
    setPreviewRows((prev) => {
      const normalizedValue = field === "amount" ? (value === "" ? "" : Number(value)) : value;

      return prev.map((row, rowIndex) => {
        if (rowIndex !== index) {
          return row;
        }

        return {
          ...row,
          [field]: normalizedValue,
          ...(field === "category"
            ? {
                category_review_required: true,
                category_review_reason: t("import.categoryEditedReason"),
                category_source: "user_editing",
                category_reason: t("import.categoryEditedReason"),
              }
            : {}),
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
        };
      });
    });
  };

  const handleCopyUploadDiagnostics = async () => {
    if (!uploadDiagnostics || !navigator.clipboard?.writeText) {
      return;
    }

    try {
      await navigator.clipboard.writeText(buildSafeUploadDiagnosticsText(uploadDiagnostics));
      setDiagnosticsCopied(true);
    } catch {
      setDiagnosticsCopied(false);
    }
  };

  const handleApprovePreviewCategory = (index) => {
    setPreviewRows((prev) => {
      const reviewedRow = prev[index];
      const reviewedCategory = reviewedRow?.category?.trim();

      if (!reviewedRow || !reviewedCategory) {
        return prev;
      }

      const similarityKey = getPreviewSimilarityKey(reviewedRow);

      return prev.map((row, rowIndex) => {
        const shouldApplyToSimilar =
          similarityKey &&
          rowIndex !== index &&
          getPreviewSimilarityKey(row) === similarityKey;

        if (rowIndex !== index && !shouldApplyToSimilar) {
          return row;
        }

        return {
          ...row,
          category: reviewedCategory,
          category_review_required: false,
          category_review_reason: null,
          category_confidence: Math.max(Number(row.category_confidence || 0), 0.9),
          category_source: shouldApplyToSimilar ? "user_review_similar" : "user_review",
          category_reason: shouldApplyToSimilar
            ? t("import.categoryAppliedToSimilarReason")
            : t("import.categoryApprovedReason"),
        };
      });
    });
  };

  const handleApplyPreviewLearningGroup = (group) => {
    const reviewedCategory = (
      previewGroupCategoryDrafts[group.key] ||
      group.suggestedCategory ||
      ""
    ).trim();
    if (!reviewedCategory) return;

    const groupIndexes = new Set(group.rowIndexes);
    setPreviewRows((prev) =>
      prev.map((row, rowIndex) => {
        if (!groupIndexes.has(rowIndex)) {
          return row;
        }

        return {
          ...row,
          category: reviewedCategory,
          category_review_required: false,
          category_review_reason: null,
          category_confidence: Math.max(Number(row.category_confidence || 0), 0.92),
          category_source: "user_group_review",
          category_reason: t("import.groupCategoryAppliedReason", {
            merchant: group.displayName,
          }),
        };
      })
    );
    setPreviewGroupCategoryDrafts((prev) => ({
      ...prev,
      [group.key]: reviewedCategory,
    }));
  };

  const handleRemovePreviewRow = (index) => {
    setPreviewRows((prev) => prev.filter((_, rowIndex) => rowIndex !== index));
  };

  const handleRestorePreviewRows = () => {
    setPreviewRows(detectedPreviewRows);
    setPreviewGroupCategoryDrafts({});
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

    setPreviewRows((prev) => [...prev, buildManualPreviewRow(fallbackDate, t)]);
    setPreviewFilter("all");
  };

  const handleConfirmPreviewImport = async () => {
    const rowsToImport = previewRowItems
      .filter(
        ({ duplicateReason, validation, categoryReviewRequired }) =>
          !duplicateReason && validation.messages.length === 0 && !categoryReviewRequired
      )
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
        message: getApiSuccessMessage(response.data, t("import.completed")),
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
        setError(getApiErrorMessage(confirmError, t("import.confirmPreviewFailed")));
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
        message: t("import.receiptSaved"),
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
        setError(getApiErrorMessage(saveError, t("import.saveReceiptFailed")));
      }
    } finally {
      setSavingDraft(false);
    }
  };

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <PageHeader
          icon={IconCloudUpload}
          titleKey="common.smartImport"
          subtitleKey="headers.importSubtitle"
        />

        <div className="filter-card">
          <div className="section-header">
            <h2>{t("import.destination")}</h2>
            <p>{t("import.destinationDetail")}</p>
          </div>

          <AccountSelector
            value={selectedAccountId}
            onChange={setSelectedAccountId}
            allowAll={false}
            label={t("common.targetAccount")}
            persistSelection={false}
          />
        </div>

        <div className="dashboard-card large-card">
          <div className="section-header">
            <h2>{t("import.uploadFiles")}</h2>
            <p>{t("import.uploadFilesDetail")}</p>
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
                <h3>{t("common.smartImport")}</h3>
                <p>{t("import.selectStatement")}</p>
              </div>

              <button
                type="button"
                className="import-upload-button"
                onClick={handleChooseFile}
                disabled={loading}
              >
                {loading ? t("import.processing") : t("import.chooseFiles")}
              </button>
            </div>

            <div className="import-upload-meta">
              <span className="import-file-label">{t("import.selectedFiles")}</span>
              <span className="import-file-name">{selectedFileName || t("import.noFiles")}</span>
            </div>

            {loading && (
              <div className="import-info-box">
                <strong>{t("import.processingUpload")}</strong>
                <p>{t("import.processingDetail")}</p>
              </div>
            )}

            {error && (
              <div className="import-error">
                <div className="import-message-header">
                  <div>
                    <h3>{t("import.importFailed")}</h3>
                    <p>{error}</p>
                  </div>
                  <button
                    type="button"
                    className="dismiss-message-button dismiss-error-button"
                    onClick={clearAll}
                  >
                    {t("import.dismiss")}
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

                {uploadDiagnostics && (
                  <div className="import-error-diagnostics">
                    <div className="import-message-header">
                      <div>
                        <strong>{t("import.diagnosticTitle")}</strong>
                        <p>{t("import.diagnosticDetail")}</p>
                      </div>
                      <button
                        type="button"
                        className="dismiss-message-button import-diagnostics-copy-button"
                        onClick={handleCopyUploadDiagnostics}
                      >
                        {diagnosticsCopied
                          ? t("import.diagnosticCopied")
                          : t("import.diagnosticCopy")}
                      </button>
                    </div>

                    <dl className="import-diagnostics-grid">
                      <div>
                        <dt>{t("import.diagnosticStatus")}</dt>
                        <dd>{formatDiagnosticValue(uploadDiagnostics.status, t)}</dd>
                      </div>
                      <div>
                        <dt>{t("import.diagnosticRequestId")}</dt>
                        <dd>{formatDiagnosticValue(uploadDiagnostics.requestId, t)}</dd>
                      </div>
                      <div>
                        <dt>{t("import.diagnosticStage")}</dt>
                        <dd>{formatDiagnosticValue(uploadDiagnostics.stage, t)}</dd>
                      </div>
                      <div>
                        <dt>{t("import.diagnosticUploadPath")}</dt>
                        <dd>{formatDiagnosticValue(uploadDiagnostics.uploadPath, t)}</dd>
                      </div>
                    </dl>

                    <div className="import-diagnostics-files">
                      <span>{t("import.diagnosticFiles")}</span>
                      <ul>
                        {uploadDiagnostics.files.map((file, index) => (
                          <li key={`upload-diagnostic-file-${index}`}>
                            {formatDiagnosticFile(file, index)}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            )}

            {importResult && importResult.status === "completed" && (
              <div className="import-success">
                <div className="import-message-header">
                  <div>
                    <h3>{t("import.completed")}</h3>
                    <p>{importResult.message}</p>
                  </div>
                  <button type="button" className="dismiss-message-button" onClick={clearAll}>
                    {t("import.clear")}
                  </button>
                </div>

                {importResult.import_summary && (
                  <div className="import-stats-grid">
                    <div className="import-stat-card">
                      <span className="import-stat-label">{t("import.imported")}</span>
                      <strong>{importResult.import_summary.imported ?? 0}</strong>
                    </div>

                    <div className="import-stat-card">
                      <span className="import-stat-label">{t("import.duplicatesSkipped")}</span>
                      <strong>{importResult.import_summary.duplicates_skipped ?? 0}</strong>
                    </div>

                    <div className="import-stat-card">
                      <span className="import-stat-label">{t("import.invalidRowsSkipped")}</span>
                      <strong>{importResult.import_summary.invalid_rows_skipped ?? 0}</strong>
                    </div>
                  </div>
                )}

                {importResult.notes?.length > 0 && (
                  <div className="receipt-preview-box">
                    <strong>{t("common.notes")}</strong>
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
                    onClick={() => navigate("/analytics")}
                  >
                    {t("common.viewAnalytics")}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => navigate("/transactions")}
                  >
                    {t("common.reviewTransactions")}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {importResult?.status === "draft_review" && receiptDraft && (
          <div className="dashboard-card large-card">
            <div className="section-header">
              <h2>{t("import.reviewReceiptDraft")}</h2>
              <p>{t("import.reviewReceiptDraftDetail")}</p>
            </div>

            <div className="transaction-form">
              <input
                type="number"
                step="0.01"
                className={receiptDraftValidation.fieldIssues.amount ? "import-invalid-input" : ""}
                value={receiptDraft.amount ?? ""}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, amount: e.target.value })}
                placeholder={t("common.amount")}
              />

              <input
                type="text"
                className={receiptDraftValidation.fieldIssues.category ? "import-invalid-input" : ""}
                value={receiptDraft.category}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, category: e.target.value })}
                placeholder={t("common.category")}
              />

              <input
                type="text"
                className={receiptDraftValidation.fieldIssues.description ? "import-invalid-input" : ""}
                value={receiptDraft.description}
                onChange={(e) => setReceiptDraft({ ...receiptDraft, description: e.target.value })}
                placeholder={t("common.description")}
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
                <option value="expense">{t("common.expense")}</option>
                <option value="income">{t("common.income")}</option>
              </select>

              <button
                type="button"
                onClick={handleSaveReceiptDraft}
                disabled={savingDraft || receiptDraftValidation.messages.length > 0}
              >
                {savingDraft ? t("common.saving") : t("import.saveTransaction")}
              </button>
            </div>

            {receiptDraftValidation.messages.length > 0 && (
              <div className="import-validation-box">
                <strong>{t("import.receiptNeedsFixes")}</strong>
                <p>{t("import.beforeSavingFix", { issues: receiptDraftValidation.messages.join(", ") })}</p>
              </div>
            )}

            {receiptDraft.raw_text_preview && (
              <div className="receipt-preview-box">
                <strong>{t("import.ocrTextPreview")}</strong>
                <p>{receiptDraft.raw_text_preview}</p>
              </div>
            )}

            {receiptDraft.notes?.length > 0 && (
              <div className="receipt-preview-box">
                <strong>{t("common.notes")}</strong>
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
              <h2>{t("import.reviewStatementRows")}</h2>
              <p>{t("import.reviewStatementRowsDetail")}</p>
            </div>

            <div className="import-preview-toolbar">
              <div className="import-preview-summary">
                <strong>
                  {t("import.rowsSelected", {
                    count: previewRows.length,
                    plural: previewRows.length === 1 ? "" : "s",
                  })}
                </strong>
                <p>
                  {invalidPreviewRowCount > 0
                    ? t("import.summaryInvalid", {
                        count: invalidPreviewRowCount,
                        plural: invalidPreviewRowCount === 1 ? "" : "s",
                      })
                    : categoryReviewRowCount > 0
                    ? t("import.summaryCategoryReview", {
                        reviewCount: categoryReviewRowCount,
                        reviewPlural: categoryReviewRowCount === 1 ? "" : "s",
                        readyCount: importReadyPreviewRowCount,
                        readyPlural: importReadyPreviewRowCount === 1 ? "" : "s",
                      })
                    : matchedPreviewRowCount > 0
                    ? t("import.summaryMatched", {
                        matchedCount: matchedPreviewRowCount,
                        matchedPlural: matchedPreviewRowCount === 1 ? "" : "s",
                        readyCount: importReadyPreviewRowCount,
                        readyPlural: importReadyPreviewRowCount === 1 ? "" : "s",
                      })
                    : confidencePreviewRowCount > 0
                    ? t("import.summaryConfidence", {
                        count: confidencePreviewRowCount,
                        plural: confidencePreviewRowCount === 1 ? "" : "s",
                      })
                    : removedPreviewCount > 0
                    ? t("import.summaryRemoved", {
                        count: removedPreviewCount,
                        plural: removedPreviewCount === 1 ? "" : "s",
                      })
                    : manualPreviewRowCount > 0
                    ? t("import.summaryManual", {
                        count: manualPreviewRowCount,
                        plural: manualPreviewRowCount === 1 ? "" : "s",
                      })
                    : t("import.summaryDefault")}
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
                    ? t("common.importing")
                    : t("import.importReadyRowsCount", { count: importReadyPreviewRowCount })}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={handleAddManualPreviewRow}
                  disabled={confirmingPreview}
                >
                  {t("common.addManualRow")}
                </button>
                {invalidPreviewRowCount > 0 && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleRemoveNeedsReviewRows}
                    disabled={confirmingPreview}
                  >
                    {t("import.removeNeedsReview")}
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
                      {t("import.removeAlreadyWritten")}
                    </button>
                  )}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleRestorePreviewRows}
                    disabled={confirmingPreview}
                  >
                    {t("common.restoreDetectedRows")}
                  </button>
                  </>
                )}
              </div>
            </div>

            <div className="import-preview-stats-grid">
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">{t("common.ready")}</span>
                <strong>{importReadyPreviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">{t("common.needsReview")}</span>
                <strong>{invalidPreviewRowCount + categoryReviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">{t("common.categoryReview")}</span>
                <strong>{categoryReviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">{t("common.alreadyWritten")}</span>
                <strong>{matchedPreviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">{t("common.confidence")}</span>
                <strong>{confidencePreviewRowCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">{t("common.removed")}</span>
                <strong>{removedPreviewCount}</strong>
              </div>
              <div className="import-preview-stat-card">
                <span className="import-preview-stat-label">{t("common.manual")}</span>
                <strong>{manualPreviewRowCount}</strong>
              </div>
            </div>

            <div className="import-preview-filters" role="tablist" aria-label={t("import.previewFilters")}>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "all" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("all")}
              >
                {t("import.allRows", { count: previewRows.length })}
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "missing" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("missing")}
              >
                {t("import.readyRows", { count: importReadyPreviewRowCount })}
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "needs_review" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("needs_review")}
              >
                {t("import.needsReviewRows", { count: invalidPreviewRowCount + categoryReviewRowCount })}
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "duplicates" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("duplicates")}
              >
                {t("import.alreadyWrittenRows", { count: duplicatePreviewRowCount })}
              </button>
              <button
                type="button"
                className={`import-filter-chip ${previewFilter === "confidence" ? "import-filter-chip-active" : ""}`}
                onClick={() => setPreviewFilter("confidence")}
              >
                {t("import.confidenceCheckRows", { count: confidencePreviewRowCount })}
              </button>
            </div>

            {skippedImportRowCount > 0 && (
              <div className="import-validation-box">
                <strong>
                  {t("import.sourceRowsSkipped", {
                    count: skippedImportRowCount,
                    plural: skippedImportRowCount === 1 ? "" : "s",
                  })}
                </strong>
                <p>{t("import.sourceRowsSkippedDetail")}</p>
                {skippedImportRowDetails.length > 0 && (
                  <ul className="assistant-list import-skipped-row-list">
                    {skippedImportRowDetails.map((item, index) => (
                      <li key={`skipped-import-row-${index}`}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {invalidPreviewRowCount > 0 && (
              <div className="import-validation-box">
                <strong>
                  {t("import.rowsNeedFixes", {
                    count: invalidPreviewRowCount,
                    plural: invalidPreviewRowCount === 1 ? "" : "s",
                  })}
                </strong>
                <p>{t("import.reviewHighlightedFields")}</p>
              </div>
            )}

            {duplicatePreviewRowCount > 0 && (
              <div className="import-duplicate-box">
                <strong>
                  {t("import.duplicatesFound", {
                    count: matchedPreviewRowCount || duplicatePreviewRowCount,
                    plural: (matchedPreviewRowCount || duplicatePreviewRowCount) === 1 ? "" : "s",
                  })}
                </strong>
                <p>{t("import.duplicatesDetail")}</p>
              </div>
            )}

            {confidencePreviewRowCount > 0 && (
              <div className="import-confidence-box">
                <strong>
                  {t("import.confidenceChecks", {
                    count: confidencePreviewRowCount,
                    plural: confidencePreviewRowCount === 1 ? "" : "s",
                  })}
                </strong>
                <p>{t("import.confidenceChecksDetail")}</p>
              </div>
            )}

            {previewLearningGroups.length > 0 && (
              <div className="import-learning-panel">
                <div className="section-header">
                  <h3>{t("import.reviewSimilarGroupsTitle")}</h3>
                  <p>{t("import.reviewSimilarGroupsDetail")}</p>
                </div>

                <div className="import-learning-grid">
                  {previewLearningGroups.map((group) => {
                    const draftCategory =
                      previewGroupCategoryDrafts[group.key] ?? group.suggestedCategory ?? "";

                    return (
                      <div key={group.key} className="import-learning-card">
                        <div>
                          <span className="import-source-label">
                            {group.type === "income" ? t("common.income") : t("common.expense")}
                          </span>
                          <h4>{group.displayName}</h4>
                          <p>
                            {t("import.similarGroupSummary", {
                              count: group.count,
                              plural: group.count === 1 ? "" : "s",
                              amount: group.totalAmount.toFixed(2),
                            })}
                          </p>
                          {group.isAmountSensitive && group.amountMin !== null && (
                            <p className="import-learning-examples">
                              {t("import.amountSensitiveGroup", {
                                min: group.amountMin.toFixed(2),
                                max: group.amountMax.toFixed(2),
                              })}
                            </p>
                          )}
                          {group.examples.length > 0 && (
                            <p className="import-learning-examples">
                              {t("import.examples")}: {group.examples.join(" | ")}
                            </p>
                          )}
                        </div>

                        <div className="import-learning-controls">
                          <label>{t("import.correctCategory")}</label>
                          <input
                            type="text"
                            value={draftCategory}
                            onChange={(event) =>
                              setPreviewGroupCategoryDrafts((prev) => ({
                                ...prev,
                                [group.key]: event.target.value,
                              }))
                            }
                            placeholder={t("import.correctCategoryPlaceholder")}
                          />
                          <button
                            type="button"
                            className="smart-apply-button"
                            onClick={() => handleApplyPreviewLearningGroup(group)}
                            disabled={confirmingPreview || !draftCategory.trim()}
                          >
                            {t("import.applyToSimilarRows")}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {previewRows.length > 0 && filteredPreviewRows.length > 0 ? (
              <div className="transactions-table-wrapper">
                <table className="transactions-table">
                  <thead>
                    <tr>
                      <th>{t("common.date")}</th>
                      <th>{t("common.description")}</th>
                      <th>{t("common.amount")}</th>
                      <th>{t("common.type")}</th>
                      <th>{t("common.category")}</th>
                      <th>{t("common.actions")}</th>
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
                        categoryReviewRequired,
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
                                  <span className="import-source-label">{t("import.parsedFrom")}</span>
                                  <code>{row.source_line}</code>
                                </div>
                              )}
                              {confidence != null && (
                                <div className="import-confidence-row">
                                  <span>{t("common.parserConfidence")}</span>
                                  <strong>{formatConfidencePercent(confidence, t)}</strong>
                                </div>
                              )}
                              {categoryConfidence != null && (
                                <div className="import-confidence-row">
                                  <span>{t("common.categoryConfidence")}</span>
                                  <strong>{formatConfidencePercent(categoryConfidence, t)}</strong>
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
                              {validation.messages.length > 0 && (
                                <div className="import-row-issues">
                                  {t("import.needsReviewInline", { issues: validation.messages.join(", ") })}
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
                                <option value="expense">{t("common.expense")}</option>
                                <option value="income">{t("common.income")}</option>
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
                                {t("common.remove")}
                              </button>
                              {categoryReviewRequired && validation.messages.length === 0 && !duplicateReason && (
                                <button
                                  type="button"
                                  className="import-remove-row-button"
                                  onClick={() => handleApprovePreviewCategory(index)}
                                  disabled={confirmingPreview || !row.category?.trim()}
                                >
                                  {t("common.approveCategory")}
                                </button>
                              )}
                              {(row.source_line === manualSourceLine || row.source_line === "Added manually during review.") && (
                                <span className="import-row-status import-row-status-manual">{t("common.manualRow")}</span>
                              )}
                              {duplicateReason && (
                                <span className="import-row-status import-row-status-duplicate">
                                  {row.reconciliation_status === "matched"
                                    ? t("import.alreadyWrittenStatus")
                                    : t("common.duplicate")}
                                </span>
                              )}
                              {confidenceReason && (
                                <span className="import-row-status import-row-status-confidence">
                                  {categoryReviewRequired ? t("import.reviewCategory") : t("import.checkParser")}
                                </span>
                              )}
                              {validation.messages.length > 0 && (
                                <span className="import-row-status import-row-status-warning">{t("common.needsReview")}</span>
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
                <p>{t("import.noRowsMatch")}</p>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setPreviewFilter("all")}
                >
                  {t("common.showAllRows")}
                </button>
              </div>
            ) : (
              <div className="empty-state import-preview-empty">
                <p>{t("import.noRowsSelected")}</p>
                <div className="import-preview-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleAddManualPreviewRow}
                    disabled={confirmingPreview}
                  >
                    {t("common.addManualRow")}
                  </button>
                  {detectedPreviewRows.length > 0 && (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={handleRestorePreviewRows}
                      disabled={confirmingPreview}
                    >
                      {t("common.restoreDetectedRows")}
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
                {confirmingPreview ? t("common.importing") : t("common.importReadyRows")}
              </button>
            </div>

            {importResult.notes?.length > 0 && (
              <div className="receipt-preview-box">
                <strong>{t("common.notes")}</strong>
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
