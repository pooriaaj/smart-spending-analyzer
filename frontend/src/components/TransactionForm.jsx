import { useEffect, useState } from "react";
import api from "../services/api";

function TransactionForm({ onTransactionCreated, editingTransaction, onCancelEdit }) {
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState("");
  const [type, setType] = useState("expense");
  const [error, setError] = useState("");

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
  }, [editingTransaction]);

  const resetForm = () => {
    setAmount("");
    setCategory("");
    setDescription("");
    setDate("");
    setType("expense");
    setError("");
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
    } catch (err) {
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

      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

export default TransactionForm;