import { useState } from "react";
import api from "../services/api";

function TransactionForm({ onTransactionCreated }) {
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState("");
  const [type, setType] = useState("expense");
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    try {
      await api.post("/transactions/", {
        amount: parseFloat(amount),
        category,
        description,
        date,
        type,
      });

      setAmount("");
      setCategory("");
      setDescription("");
      setDate("");
      setType("expense");

      if (onTransactionCreated) {
        onTransactionCreated();
      }
    } catch (err) {
      setError("Failed to create transaction.");
    }
  };

  return (
    <div className="dashboard-card">
      <h2>Add Transaction</h2>

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

        <button type="submit">Add Transaction</button>
      </form>

      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

export default TransactionForm;