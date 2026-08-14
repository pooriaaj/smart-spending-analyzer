import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Modal,
  Paper,
  Stack,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import api from "../services/api";
import { useLanguage } from "../i18n/LanguageContext";
import { getApiErrorMessage } from "../utils/errorUtils";

const ROLE_CHOICES = [
  { role: "income", color: "teal", labelKey: "income", hintKey: "incomeHint" },
  { role: "expense", color: "red", labelKey: "expense", hintKey: "expenseHint" },
  { role: "neutral", color: "gray", labelKey: "neutral", hintKey: "neutralHint" },
];

const SAVED_MESSAGE_KEYS = {
  income: "savedIncome",
  expense: "savedExpense",
  neutral: "savedNeutral",
};

function formatAmount(value) {
  return `$${Math.abs(Number(value || 0)).toFixed(2)}`;
}

/**
 * Lets the owner say what a transfer actually was.
 *
 * The app deliberately does not guess: a bank prints the same words for a
 * paycheque, a repaid debt, and money moved between the owner's own accounts.
 */
function CashflowReviewModal({ opened, onClose, accountId, onAnswered }) {
  const { t } = useLanguage();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState("");
  const [includeAnswered, setIncludeAnswered] = useState(false);
  // On by default: answering the same person over and over is the thing this
  // screen exists to avoid.
  const [applyToSimilar, setApplyToSimilar] = useState(true);

  const loadPendingTransfers = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const params = { include_answered: includeAnswered, limit: 50 };
      if (accountId && accountId !== "all") {
        params.account_id = Number(accountId);
      }

      const response = await api.get("/transactions/cashflow-review", { params });
      setItems(Array.isArray(response.data?.items) ? response.data.items : []);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, t("cashflowReview.loadFailed")));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [accountId, includeAnswered, t]);

  useEffect(() => {
    if (opened) {
      loadPendingTransfers();
    }
  }, [opened, loadPendingTransfers]);

  const answerTransfer = async (transactionId, role) => {
    setSavingId(transactionId);

    try {
      const response = await api.post("/transactions/cashflow-role", {
        transaction_ids: [transactionId],
        role,
        apply_to_similar: applyToSimilar,
      });

      const similarCount = Number(response.data?.similar_updated_count || 0);
      const baseMessage = role === null
        ? t("cashflowReview.savedUndo")
        : t(`cashflowReview.${SAVED_MESSAGE_KEYS[role]}`);

      notifications.show({
        color: role === null ? "gray" : "teal",
        message: similarCount > 0
          ? `${baseMessage} ${t("cashflowReview.alsoApplied", { count: similarCount })}`
          : baseMessage,
      });

      await loadPendingTransfers();
      onAnswered?.();
    } catch (requestError) {
      notifications.show({
        color: "red",
        message: getApiErrorMessage(requestError, t("cashflowReview.saveFailed")),
      });
    } finally {
      setSavingId(null);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={t("cashflowReview.title")}
      size="lg"
      radius="lg"
    >
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          {t("cashflowReview.intro")}
        </Text>

        <Stack gap="xs">
          <Checkbox
            label={t("cashflowReview.applyToSimilar")}
            description={t("cashflowReview.applyToSimilarHint")}
            checked={applyToSimilar}
            onChange={(event) => setApplyToSimilar(event.currentTarget.checked)}
          />
          <Checkbox
            label={t("cashflowReview.showAnswered")}
            checked={includeAnswered}
            onChange={(event) => setIncludeAnswered(event.currentTarget.checked)}
          />
        </Stack>

        {error && (
          <Alert color="red" radius="md">
            {error}
          </Alert>
        )}

        {loading && (
          <Group justify="center" py="lg">
            <Loader size="sm" />
          </Group>
        )}

        {!loading && !error && items.length === 0 && (
          <Text size="sm" c="dimmed">
            {t("cashflowReview.empty")}
          </Text>
        )}

        {!loading &&
          items.map((item) => (
            <Paper key={item.id} withBorder radius="md" p="md">
              <Stack gap="sm">
                <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap">
                  <Stack gap={2}>
                    <Text fw={600} size="sm">
                      {item.description}
                    </Text>
                    <Group gap="xs">
                      <Text size="xs" c="dimmed">
                        {item.date}
                      </Text>
                      {applyToSimilar && item.similar_pending_count > 1 && (
                        <Badge color="indigo" variant="light" radius="sm" size="sm">
                          {t("cashflowReview.groupHint", {
                            count: item.similar_pending_count,
                            counterparty: item.counterparty,
                          })}
                        </Badge>
                      )}
                    </Group>
                  </Stack>
                  <Text fw={700}>{formatAmount(item.amount)}</Text>
                </Group>

                {item.cashflow_role ? (
                  <Group gap="sm">
                    <Badge color="teal" variant="light" radius="sm">
                      {t("cashflowReview.answeredAs", {
                        role: t(`cashflowReview.${item.cashflow_role}`),
                      })}
                    </Badge>
                    <Button
                      size="xs"
                      variant="subtle"
                      color="gray"
                      loading={savingId === item.id}
                      onClick={() => answerTransfer(item.id, null)}
                    >
                      {t("cashflowReview.undo")}
                    </Button>
                  </Group>
                ) : (
                  <Group gap="xs">
                    {ROLE_CHOICES.map((choice) => (
                      <Button
                        key={choice.role}
                        size="xs"
                        radius="md"
                        variant="light"
                        color={choice.color}
                        title={t(`cashflowReview.${choice.hintKey}`)}
                        loading={savingId === item.id}
                        onClick={() => answerTransfer(item.id, choice.role)}
                      >
                        {t(`cashflowReview.${choice.labelKey}`)}
                      </Button>
                    ))}
                  </Group>
                )}
              </Stack>
            </Paper>
          ))}

        <Group justify="flex-end">
          <Button variant="outline" color="gray" radius="md" onClick={onClose}>
            {t("cashflowReview.close")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export default CashflowReviewModal;
