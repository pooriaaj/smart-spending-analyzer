import { useEffect, useState } from "react";
import api from "../services/api";
import AccountSelector from "./AccountSelector";
import { getSelectedAccountId } from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";

function TransactionForm({ onTransactionCreated, editingTransaction, onCancelEdit }) {
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
    <div className="dashboard-card">
      <h2>{editingTransaction ? t("transactionForm.editTitle") : t("transactionForm.addTitle")}</h2>

      <form onSubmit={handleSubmit} className="transaction-form">
        <AccountSelector
          value={accountId}
          onChange={setAccountId}
          allowAll={false}
          label={t("common.targetAccount")}
        />

        <input
          type="number"
          step="0.01"
          placeholder={t("common.amount")}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          required
        />

        <input
          type="text"
          placeholder={t("common.category")}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          required
        />

        <input
          type="text"
          placeholder={t("common.description")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
        />

        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          required
        />

        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="expense">{t("common.expense")}</option>
          <option value="income">{t("common.income")}</option>
        </select>

        <button
          type="button"
          className="suggest-button"
          onClick={handleSuggestCategory}
          disabled={suggestionLoading}
        >
          {suggestionLoading ? t("transactionForm.suggesting") : t("transactionForm.suggestCategory")}
        </button>

        <button type="submit">
          {editingTransaction ? t("transactionForm.update") : t("transactionForm.add")}
        </button>

        {editingTransaction && (
          <button
            type="button"
            className="cancel-button"
            onClick={() => {
              resetForm();
              onCancelEdit();
            }}
          >
            {t("transactionForm.cancel")}
          </button>
        )}
      </form>

      {suggestion && (
        <div className="suggestion-box">
          <h3>{t("transactionForm.suggestedCategory")}</h3>
          <p>
            <strong>{suggestion.suggested_category}</strong>
          </p>
          <p>{t("transactionForm.confidence")}: {(suggestion.confidence * 100).toFixed(0)}%</p>
          <p>{suggestion.reason}</p>
          {suggestion.matched_keyword && (
            <p>{t("transactionForm.matchedKeyword")}: {suggestion.matched_keyword}</p>
          )}
        </div>
      )}

      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

export default TransactionForm;
