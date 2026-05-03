const CATEGORY_KEY_BY_NORMALIZED = {
  cafe: "cafe",
  coffee: "cafe",
  "car maintenance": "carMaintenance",
  car_maintenance: "carMaintenance",
  debt: "debt",
  education: "education",
  entertainment: "entertainment",
  fees: "fees",
  gas: "gas",
  gift: "gifts",
  gifts: "gifts",
  grocery: "groceries",
  groceries: "groceries",
  healthcare: "healthcare",
  health: "healthcare",
  housing: "housing",
  income: "income",
  insurance: "insurance",
  internet: "internet",
  misc: "other",
  miscellaneous: "other",
  other: "other",
  personal: "personal",
  pets: "pets",
  pharmacy: "pharmacy",
  phone: "phone",
  rent: "rent",
  restaurant: "restaurant",
  restaurants: "restaurant",
  salary: "salary",
  savings: "savings",
  shopping: "shopping",
  smoking: "smoking",
  smokes: "smoking",
  subscription: "subscriptions",
  subscriptions: "subscriptions",
  taxes: "taxes",
  transfer: "transfer",
  transportation: "transport",
  transport: "transport",
  travel: "travel",
  uncategorized: "other",
  unknown: "other",
  utilities: "utilities",
  utility: "utilities",
};

const ACCOUNT_TYPE_KEY_BY_NORMALIZED = {
  cash: "cash",
  checking: "checking",
  chequing: "checking",
  credit: "credit",
  creditcard: "credit",
  "credit card": "credit",
  other: "other",
  saving: "savings",
  savings: "savings",
};

function normalizeLookupValue(value = "") {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[_-]+/g, " ")
    .replace(/[^a-zA-Z0-9 ]+/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

export function humanizeLabel(value = "", fallback = "Other") {
  const cleaned = String(value || fallback).replace(/_/g, " ").trim();
  if (!cleaned) return fallback;

  return cleaned
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function translateIfAvailable(t, key) {
  if (!t) return "";
  const translated = t(key);
  return translated === key ? "" : translated;
}

export function formatCategoryLabel(value = "", t) {
  const normalized = normalizeLookupValue(value);
  const fallback = translateIfAvailable(t, "categories.other") || "Other";
  if (!normalized) return fallback;

  const categoryKey = CATEGORY_KEY_BY_NORMALIZED[normalized];
  if (categoryKey) {
    return translateIfAvailable(t, `categories.${categoryKey}`) || humanizeLabel(value, fallback);
  }

  return humanizeLabel(value, fallback);
}

export function formatAccountType(type = "", t) {
  const normalized = normalizeLookupValue(type);
  const accountTypeKey = ACCOUNT_TYPE_KEY_BY_NORMALIZED[normalized] || "other";
  return translateIfAvailable(t, `accountTypes.${accountTypeKey}`) || humanizeLabel(type, "Other");
}

export function formatAccountName(name = "", t) {
  const normalized = normalizeLookupValue(name);
  if (normalized === "main account") {
    return translateIfAvailable(t, "accounts.defaultMainAccount") || name;
  }

  if (normalized === "all accounts" || normalized === "all accounts combined") {
    return translateIfAvailable(t, "common.allAccounts") || name;
  }

  return name || translateIfAvailable(t, "common.account") || "Account";
}

export function formatAccountLabel(account, t) {
  if (!account) return "";
  const name = formatAccountName(account.name, t);
  const type = formatAccountType(account.type, t);
  return type ? `${name} (${type})` : name;
}

export function formatScopeLabel(label = "", t) {
  const normalized = normalizeLookupValue(label);
  if (!normalized) return "";
  if (normalized === "all accounts" || normalized === "all accounts combined") {
    return translateIfAvailable(t, "common.allAccounts") || label;
  }

  const mainAccountMatch = String(label).match(/^Main Account\s*\(([^)]+)\)$/i);
  if (mainAccountMatch) {
    return `${formatAccountName("Main Account", t)} (${formatAccountType(mainAccountMatch[1], t)})`;
  }

  return label;
}

export function formatConfidenceLevel(level = "", t) {
  const normalized = normalizeLookupValue(level);
  if (normalized === "high") return translateIfAvailable(t, "confidenceLevels.high") || level;
  if (normalized === "medium") return translateIfAvailable(t, "confidenceLevels.medium") || level;
  if (normalized === "low") return translateIfAvailable(t, "confidenceLevels.low") || level;
  return level;
}

export function formatRecurringReviewReason(item = {}, t) {
  const latestChangePercent = Number(item.latest_change_percent);
  const annualizedAmount = Number(item.annualized_amount || 0);
  const reviewPriority = normalizeLookupValue(item.review_priority);

  if (Number.isFinite(latestChangePercent) && latestChangePercent >= 8) {
    return t("recurringReasons.highChange", {
      change: latestChangePercent.toFixed(0),
    });
  }

  if (annualizedAmount >= 500 || reviewPriority === "high") {
    return t("recurringReasons.highAnnual");
  }

  if (annualizedAmount >= 250 || reviewPriority === "medium") {
    return t("recurringReasons.medium");
  }

  return t("recurringReasons.low");
}
