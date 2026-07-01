import { useEffect, useState } from "react";
import {
  Alert,
  Autocomplete,
  Badge,
  Box,
  Button,
  Card,
  Group,
  NativeSelect,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import api from "../services/api";
import AccountSelector from "./AccountSelector";
import { getSelectedAccountId } from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";

function TransactionForm({
  onTransactionCreated,
  editingTransaction,
  onCancelEdit,
  categoryOptions = [],
}) {
  const [accountId, setAccountId] = useState(getSelectedAccountId());
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState("");
  const [type, setType] = useState("expense");
  const [error, setError] = useState("");
  const [suggestion, setSuggestion] = useState(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const { t } = useLanguage();

  useEffect(() => {
    if (editingTransaction) {
      setAccountId(editingTransaction.account_id || getSelectedAccountId());
      setAmount(editingTransaction.amount);
      setCategory(editingTransaction.category);
      setDescription(editingTransaction.description);
      setDate(editingTransaction.date);
      setType(editingTransaction.type);
    } else {
      setAmount("");
      setCategory("");
      setDescription("");
      setDate("");
      setType("expense");
    }

    setSuggestion(null);
    setError("");
  }, [editingTransaction]);

  const resetForm = () => {
    setAmount("");
    setCategory("");
    setDescription("");
    setDate("");
    setType("expense");
    setError("");
    setSuggestion(null);
  };

  const handleSuggestCategory = async () => {
    setError("");
    setSuggestion(null);

    if (!description.trim()) {
      setError(t("transactionForm.descriptionRequired"));
      return;
    }

    try {
      setSuggestionLoading(true);

      const response = await api.post("/transactions/categorize/suggest", {
        description,
        type,
      });

      setSuggestion(response.data);
      setCategory(response.data.suggested_category);
    } catch {
      setError(t("transactionForm.suggestFailed"));
    } finally {
      setSuggestionLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    try {
      if (!accountId) {
        setError(t("transactionForm.accountRequired"));
        return;
      }

      const payload = {
        amount: parseFloat(amount),
        category,
        description,
        date,
        type,
        account_id: Number(accountId),
      };

      if (editingTransaction) {
        await api.put(`/transactions/${editingTransaction.id}`, payload);
      } else {
        await api.post("/transactions/", payload);
      }

      resetForm();

      if (onTransactionCreated) {
        onTransactionCreated();
      }

      if (editingTransaction && onCancelEdit) {
        onCancelEdit();
      }
    } catch {
      setError(
        editingTransaction
          ? t("transactionForm.updateFailed")
          : t("transactionForm.createFailed")
      );
    }
  };

  return (
    <Card className="dashboard-card transaction-form-card" radius="xl" p={{ base: "md", md: "lg" }}>
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" gap="md">
          <Box>
            <Title order={2} size="h3">
              {editingTransaction ? t("transactionForm.editTitle") : t("transactionForm.addTitle")}
            </Title>
            <Text size="sm" c="dimmed">
              {editingTransaction ? t("common.edit") : t("transactions.addToday")}
            </Text>
          </Box>
          <Badge color={type === "income" ? "teal" : "red"} variant="light" radius="sm">
            {type === "income" ? t("common.income") : t("common.expense")}
          </Badge>
        </Group>

        <form onSubmit={handleSubmit} className="transaction-form transaction-form-mantine">
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <Box className="transaction-form-account-field">
              <AccountSelector
                value={accountId}
                onChange={setAccountId}
                allowAll={false}
                label={t("common.targetAccount")}
              />
            </Box>

            <TextInput
              type="number"
              step="0.01"
              label={t("common.amount")}
              placeholder={t("common.amount")}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />

            <Autocomplete
              label={t("common.category")}
              placeholder={t("common.category")}
              data={[...new Set((categoryOptions || []).filter(Boolean))]}
              value={category}
              onChange={setCategory}
              required
            />

            <TextInput
              type="text"
              label={t("common.description")}
              placeholder={t("common.descriptionOptional")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />

            <TextInput
              type="date"
              label={t("common.date")}
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />

            <NativeSelect
              label={t("common.type")}
              value={type}
              onChange={(e) => setType(e.target.value)}
              data={[
                { value: "expense", label: t("common.expense") },
                { value: "income", label: t("common.income") },
              ]}
            />
          </SimpleGrid>

          <Group gap="sm" className="transaction-form-actions">
            <Button
              type="button"
              color="indigo"
              variant="light"
              radius="md"
              onClick={handleSuggestCategory}
              disabled={suggestionLoading}
            >
              {suggestionLoading ? t("transactionForm.suggesting") : t("transactionForm.suggestCategory")}
            </Button>

            <Button type="submit" color="teal" radius="md">
              {editingTransaction ? t("transactionForm.update") : t("transactionForm.add")}
            </Button>

            {editingTransaction && (
              <Button
                type="button"
                color="gray"
                variant="outline"
                radius="md"
                onClick={() => {
                  resetForm();
                  onCancelEdit();
                }}
              >
                {t("transactionForm.cancel")}
              </Button>
            )}
          </Group>
        </form>

        {suggestion && (
          <Alert className="suggestion-box" color="indigo" radius="lg" variant="light">
            <Stack gap={6}>
              <Title order={3} size="h4">{t("transactionForm.suggestedCategory")}</Title>
              <Text fw={800}>{suggestion.suggested_category}</Text>
              <Text size="sm">{t("transactionForm.confidence")}: {(suggestion.confidence * 100).toFixed(0)}%</Text>
              <Text size="sm">{suggestion.reason}</Text>
              {suggestion.matched_keyword && (
                <Text size="sm">{t("transactionForm.matchedKeyword")}: {suggestion.matched_keyword}</Text>
              )}
            </Stack>
          </Alert>
        )}

        {error && (
          <Alert color="red" radius="lg" variant="light">
            {error}
          </Alert>
        )}
      </Stack>
    </Card>
  );
}

export default TransactionForm;
