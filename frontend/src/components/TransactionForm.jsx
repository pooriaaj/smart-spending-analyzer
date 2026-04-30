import { useEffect, useState } from "react";
import api from "../services/api";

function TransactionForm({ onTransactionCreated, editingTransaction, onCancelEdit }) {
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState("");
  const [type, setType] = useState("expense");
  const [error, setError] = useState("");
  const [suggestion, setSuggestion] = useState(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);

  useEffect(() => {
    if (editingTransaction) {
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
      setError("Please enter a description before requesting a category suggestion.");
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
      setError("Failed to suggest a category.");
    } finally {
      setSuggestionLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    try {
      const payload = {
        amount: parseFloat(amount),
        category,
        description,
        date,
        type,
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
          ? "Failed to update transaction."
          : "Failed to create transaction."
      );
    }
  };

  return (
    <div className="dashboard-card">
      <h2>{editingTransaction ? "Edit Transaction" : "Add Transaction"}</h2>

      <form onSubmit={handleSubmit} className="transaction-form">
        <input
          type="number"
          step="0.01"
          placeholder="Amount"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          required
        />

        <input
          type="text"
          placeholder="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          required
        />

        <input
          type="text"
          placeholder="Description"
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
          <option value="expense">Expense</option>
          <option value="income">Income</option>
        </select>

        <button
          type="button"
          className="suggest-button"
          onClick={handleSuggestCategory}
          disabled={suggestionLoading}
        >
          {suggestionLoading ? "Suggesting..." : "Suggest Category"}
        </button>

        <button type="submit">
          {editingTransaction ? "Update Transaction" : "Add Transaction"}
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
            Cancel
          </button>
        )}
      </form>

      {suggestion && (
        <div className="suggestion-box">
          <h3>Suggested Category</h3>
          <p>
            <strong>{suggestion.suggested_category}</strong>
          </p>
          <p>Confidence: {(suggestion.confidence * 100).toFixed(0)}%</p>
          <p>{suggestion.reason}</p>
          {suggestion.matched_keyword && (
            <p>Matched keyword: {suggestion.matched_keyword}</p>
          )}
        </div>
      )}

      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

export default TransactionForm;
