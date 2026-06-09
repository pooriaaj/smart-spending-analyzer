import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  NativeSelect,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import PageHeader from "../components/PageHeader";
import TransactionForm from "../components/TransactionForm";
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
  setSelectedAccountId as persistSelectedAccountId,
} from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import { formatCategoryLabel } from "../utils/displayLabels";
import { getApiErrorMessage, getApiSuccessMessage } from "../utils/errorUtils";

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

const formatTransactionDate = (dateValue) => {
  const parsed = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return dateValue;
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
};

const formatTransactionAmount = (transaction) => {
  const amount = Number(transaction.amount || 0).toFixed(2);
  return `${transaction.type === "income" ? "+" : "-"}$${amount}`;
};

const getTransactionAccountLabel = (transaction, t) => {
  return (
    transaction.account_name ||
    transaction.account_label ||
    transaction.account?.name ||
    transaction.account_id ||
    t("common.unassigned")
  );
};

function TransactionsPage() {
  const { t } = useLanguage();
  const [transactions, setTransactions] = useState([]);
  const [transactionPageMeta, setTransactionPageMeta] = useState(DEFAULT_TRANSACTION_PAGE_META);
  const [typeFilter, setTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [debouncedSearchFilter, setDebouncedSearchFilter] = useState("");
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

  useEffect(() => {
    setTypeFilter(searchParams.get("type") || "");
    setMonthFilter(searchParams.get("month") || "");
    const categoryParam = searchParams.get("category") || "";
    setCategoryFilter(categoryParam);
    setSearchFilter(searchParams.get("description") || "");
    setAmountRangeFilter(searchParams.get("amountRange") || "");
  }, [searchParams]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedSearchFilter(searchFilter.trim());
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [searchFilter]);

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
        description: debouncedSearchFilter || undefined,
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
          debouncedSearchFilter ||
          amountRangeFilter
      );

      let transactionsResponse = await api.get("/transactions/page", {
        params: transactionParams,
      });

      if (
        normalizedAccountId &&
        !hasActiveFilters &&
        Number(transactionsResponse.data?.scope_total || 0) === 0
      ) {
        const allTransactionsResponse = await api.get("/transactions/page", {
          params: {
            page: currentPage,
            page_size: TRANSACTIONS_PER_PAGE,
          },
        });

        if (Number(allTransactionsResponse.data?.scope_total || 0) > 0) {
          transactionsResponse = allTransactionsResponse;
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
      setLoading(false);
    } catch (error) {
      handleApiAuthError(error, navigate);
    } finally {
      setLoading(false);
    }
  }, [
    amountRangeFilter,
    categoryFilter,
    currentPage,
    debouncedSearchFilter,
    monthFilter,
    navigate,
    normalizedAccountId,
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
    setDebouncedSearchFilter("");
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

      setFreshStartMessage(getApiSuccessMessage(response.data, t("transactions.freshStartComplete")));
      setFreshStartConfirm("");
      await fetchTransactions();
    } catch (error) {
      if (!handleApiAuthError(error, navigate)) {
        setFreshStartError(getApiErrorMessage(error, t("transactions.freshStartFailed")));
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
              {t("common.uploadStatement")}
            </button>
          )}
        />

        <div id="add-transaction">
          <TransactionForm onTransactionCreated={fetchTransactions} />
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

        <Card className="filter-card transaction-filter-card" radius="xl" p={{ base: "md", md: "lg" }}>
          <Stack gap="md">
            <Box>
              <Title order={2} size="h3">{t("transactions.transactionFilters")}</Title>
              <Text size="sm" c="dimmed">
                {t("transactions.showingTransactions", {
                  filtered: filteredTransactionTotal,
                  total: scopeTransactionTotal,
                  plural: scopeTransactionTotal === 1 ? "" : "s",
                })}
              </Text>
            </Box>

            <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }} spacing="md">
              <NativeSelect
                label={t("common.type")}
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                data={[
                  { value: "", label: t("common.all") },
                  { value: "income", label: t("common.income") },
                  { value: "expense", label: t("common.expense") },
                ]}
              />

              <NativeSelect
                label={t("common.month")}
                value={monthFilter}
                onChange={(e) => setMonthFilter(e.target.value)}
                data={[
                  { value: "", label: t("common.all") },
                  ...availableMonths.map((month) => ({ value: month, label: month })),
                ]}
              />

              <NativeSelect
                label={t("common.category")}
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                data={[
                  { value: "", label: t("common.all") },
                  ...availableCategories.map((category) => ({
                    value: category,
                    label: formatCategoryLabel(category, t),
                  })),
                ]}
              />

              <NativeSelect
                label={t("transactions.amountRange")}
                value={amountRangeFilter}
                onChange={(e) => setAmountRangeFilter(e.target.value)}
                data={[
                  { value: "", label: t("transactions.allAmounts") },
                  ...AMOUNT_RANGE_OPTIONS.map((option) => ({
                    value: option.value,
                    label: option.labelKey ? t(option.labelKey, { amount: option.amount }) : option.label,
                  })),
                ]}
              />

              <TextInput
                label={t("common.description")}
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder={t("transactions.descriptionSearch")}
              />
            </SimpleGrid>

            <Group className="recurring-filter-actions" justify="space-between" gap="sm">
              {searchFilter && (
                <Text className="budget-inline-note recurring-filter-note" size="sm">
                  {t("transactions.descriptionFilterNote", { term: searchFilter })}
                </Text>
              )}

              {(typeFilter ||
                monthFilter ||
                categoryFilter ||
                amountRangeFilter ||
                searchFilter) && (
                <Button type="button" variant="outline" color="gray" radius="md" onClick={clearFilters}>
                  {t("common.clearFilters")}
                </Button>
              )}
            </Group>
          </Stack>
        </Card>

        <Card className="dashboard-card transaction-ledger-card" radius="xl" p={{ base: "md", md: "lg" }}>
          <Stack gap="md">
            <Box>
              <Title order={2} size="h3">{t("transactions.transactionTable")}</Title>
              <Text size="sm" c="dimmed">{t("transactions.tableDetail")}</Text>
            </Box>

            {filteredTransactionTotal === 0 ? (
              <Paper className="empty-state transaction-empty-state" radius="lg" p="lg">
                <Stack gap="sm" align="flex-start">
                  <Text>
                    {scopeTransactionTotal === 0
                      ? t("transactions.noTransactions")
                      : t("transactions.filtersHidingTransactions")}
                  </Text>
                  {scopeTransactionTotal === 0 ? (
                    <Button variant="light" color="teal" radius="md" onClick={() => document.getElementById("add-transaction")?.scrollIntoView({ behavior: "smooth" })}>
                      {t("transactions.addToday")}
                    </Button>
                  ) : (
                    <Button variant="outline" color="gray" radius="md" onClick={clearFilters}>
                      {t("common.clearFilters")}
                    </Button>
                  )}
                </Stack>
              </Paper>
            ) : (
              <Box className="transaction-table-panel">
                <Group className="transaction-table-toolbar" justify="space-between" align="center" gap="md">
                  <Box>
                    <Text className="transaction-page-kicker">
                      {totalPages > 1
                        ? t("common.pageOf", { page: activePage, total: totalPages })
                        : t("common.allTransactions")}
                    </Text>
                    <Text className="transaction-page-summary" size="sm" c="dimmed">
                      {t("transactions.pageSummary", {
                        start: pageStartIndex + 1,
                        end: pageEndIndex,
                        total: filteredTransactionTotal,
                        plural: filteredTransactionTotal === 1 ? "" : "s",
                      })}
                    </Text>
                  </Box>

                  {renderTransactionPagination("transaction-pagination-top")}
                </Group>

                <Box className="transactions-table-wrapper transactions-table-desktop">
                  <Table className="transactions-table" verticalSpacing="sm" highlightOnHover>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t("common.date")}</Table.Th>
                        <Table.Th>{t("common.type")}</Table.Th>
                        <Table.Th>{t("common.category")}</Table.Th>
                        <Table.Th>{t("common.description")}</Table.Th>
                        <Table.Th>{t("common.amount")}</Table.Th>
                        <Table.Th>{t("common.account")}</Table.Th>
                        <Table.Th>{t("common.actions")}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {paginatedTransactions.map((transaction) => {
                        const isEditing = editingId === transaction.id;

                        return (
                          <Table.Tr key={transaction.id}>
                            <Table.Td>
                              {isEditing ? (
                                <TextInput type="date" value={editForm.date} onChange={(e) => setEditForm({ ...editForm, date: e.target.value })} />
                              ) : (
                                <Text fw={700}>{formatTransactionDate(transaction.date)}</Text>
                              )}
                            </Table.Td>

                            <Table.Td>
                              {isEditing ? (
                                <NativeSelect
                                  value={editForm.type}
                                  onChange={(e) => setEditForm({ ...editForm, type: e.target.value })}
                                  data={[
                                    { value: "income", label: t("common.income") },
                                    { value: "expense", label: t("common.expense") },
                                  ]}
                                />
                              ) : (
                                <Badge color={transaction.type === "income" ? "teal" : "rose"} variant="light" radius="sm">
                                  {transaction.type === "income" ? t("common.income") : t("common.expense")}
                                </Badge>
                              )}
                            </Table.Td>

                            <Table.Td>
                              {isEditing ? (
                                <TextInput type="text" value={editForm.category} onChange={(e) => setEditForm({ ...editForm, category: e.target.value })} />
                              ) : (
                                <Badge color="indigo" variant="light" radius="sm">
                                  {formatCategoryLabel(transaction.category, t)}
                                </Badge>
                              )}
                            </Table.Td>

                            <Table.Td>
                              {isEditing ? (
                                <TextInput
                                  type="text"
                                  value={editForm.description}
                                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                                />
                              ) : (
                                <Text className="transaction-description" fw={700}>{transaction.description}</Text>
                              )}
                            </Table.Td>

                            <Table.Td className={!isEditing ? (transaction.type === "income" ? "income-text" : "expense-text") : ""}>
                              {isEditing ? (
                                <TextInput type="number" step="0.01" value={editForm.amount} onChange={(e) => setEditForm({ ...editForm, amount: e.target.value })} />
                              ) : (
                                <Text fw={900}>{formatTransactionAmount(transaction)}</Text>
                              )}
                            </Table.Td>

                            <Table.Td>
                              {isEditing ? (
                                <TextInput
                                  type="number"
                                  value={editForm.account_id}
                                  onChange={(e) => setEditForm({ ...editForm, account_id: e.target.value })}
                                />
                              ) : (
                                <Text size="sm" c="dimmed">{getTransactionAccountLabel(transaction, t)}</Text>
                              )}
                            </Table.Td>

                            <Table.Td>
                              <Group className="transaction-actions-inline" gap="xs" wrap="nowrap">
                                {isEditing ? (
                                  <>
                                    <Button size="xs" color="teal" radius="md" onClick={() => saveEdit(transaction.id)}>
                                      {t("common.save")}
                                    </Button>
                                    <Button size="xs" color="gray" variant="outline" radius="md" onClick={cancelEdit}>
                                      {t("common.cancel")}
                                    </Button>
                                  </>
                                ) : (
                                  <>
                                    <Button size="xs" color="blue" variant="light" radius="md" onClick={() => startEdit(transaction)}>
                                      {t("common.edit")}
                                    </Button>
                                    <Button size="xs" color="red" variant="light" radius="md" onClick={() => handleDelete(transaction.id)}>
                                      {t("common.delete")}
                                    </Button>
                                  </>
                                )}
                              </Group>
                            </Table.Td>
                          </Table.Tr>
                        );
                      })}
                    </Table.Tbody>
                  </Table>
                </Box>

                <Stack className="transactions-mobile-list" gap="sm">
                  {paginatedTransactions.map((transaction) => (
                    <Paper key={`mobile-${transaction.id}`} className="transaction-mobile-card" radius="lg" p="md">
                      <Stack gap="sm">
                        <Group justify="space-between" align="flex-start" gap="md">
                          <Box>
                            <Text fw={850}>{transaction.description}</Text>
                            <Text size="sm" c="dimmed">{formatTransactionDate(transaction.date)}</Text>
                          </Box>
                          <Text className={transaction.type === "income" ? "income-text" : "expense-text"} fw={900}>
                            {formatTransactionAmount(transaction)}
                          </Text>
                        </Group>

                        <Group gap="xs">
                          <Badge color={transaction.type === "income" ? "teal" : "rose"} variant="light" radius="sm">
                            {transaction.type === "income" ? t("common.income") : t("common.expense")}
                          </Badge>
                          <Badge color="indigo" variant="light" radius="sm">
                            {formatCategoryLabel(transaction.category, t)}
                          </Badge>
                          <Badge color="gray" variant="light" radius="sm">
                            {getTransactionAccountLabel(transaction, t)}
                          </Badge>
                        </Group>

                        <Group gap="xs">
                          <Button size="xs" color="blue" variant="light" radius="md" onClick={() => startEdit(transaction)}>
                            {t("common.edit")}
                          </Button>
                          <Button size="xs" color="red" variant="light" radius="md" onClick={() => handleDelete(transaction.id)}>
                            {t("common.delete")}
                          </Button>
                        </Group>
                      </Stack>
                    </Paper>
                  ))}
                </Stack>

                {renderTransactionPagination("transaction-pagination-bottom")}
              </Box>
            )}
          </Stack>
        </Card>
      </div>
    </div>
  );
}

export default TransactionsPage;
