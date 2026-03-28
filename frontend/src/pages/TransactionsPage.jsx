import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";

function TransactionsPage() {
  const [transactions, setTransactions] = useState([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchTransactions = async () => {
    try {
      const response = await api.get("/transactions/");
      setTransactions(response.data);
    } catch (error) {
      console.error("Failed to load transactions:", error);
      localStorage.removeItem("token");
      navigate("/");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, []);

  const availableMonths = useMemo(() => {
    const months = new Set(
      transactions.map((transaction) =>
        new Date(transaction.date).toISOString().slice(0, 7)
      )
    );

    return Array.from(months).sort();
  }, [transactions]);

  const filteredTransactions = useMemo(() => {
    return transactions
      .filter((transaction) => {
        if (typeFilter && transaction.type !== typeFilter) {
          return false;
        }

        if (monthFilter) {
          const transactionMonth = new Date(transaction.date)
            .toISOString()
            .slice(0, 7);

          if (transactionMonth !== monthFilter) {
            return false;
          }
        }

        return true;
      })
      .sort((a, b) => new Date(b.date) - new Date(a.date));
  }, [transactions, typeFilter, monthFilter]);

  const handleDelete = async (transactionId) => {
    try {
      await api.delete(`/transactions/${transactionId}`);
      fetchTransactions();
    } catch (error) {
      console.error("Failed to delete transaction:", error);
    }
  };

  if (loading) {
    return (
      <div className="page-container">
        <div className="dashboard-wrapper">
          <p>Loading transactions...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-header">
          <div>
            <h1>All Transactions</h1>
            <p>View and filter your full transaction history</p>
          </div>

          <button className="logout-button" onClick={() => navigate("/dashboard")}>
            Back to Dashboard
          </button>
        </div>

        <div className="filter-bar">
          <label>Type:</label>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All</option>
            <option value="income">Income</option>
            <option value="expense">Expense</option>
          </select>

          <label>Month:</label>
          <select
            value={monthFilter}
            onChange={(e) => setMonthFilter(e.target.value)}
          >
            <option value="">All</option>
            {availableMonths.map((month) => (
              <option key={month} value={month}>
                {month}
              </option>
            ))}
          </select>
        </div>

        <div className="dashboard-card">
          {filteredTransactions.length === 0 ? (
            <p>No transactions found.</p>
          ) : (
            <div className="transactions-table-wrapper">
              <table className="transactions-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Category</th>
                    <th>Description</th>
                    <th>Amount</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransactions.map((transaction) => (
                    <tr key={transaction.id}>
                      <td>{transaction.date}</td>
                      <td>{transaction.type}</td>
                      <td>{transaction.category}</td>
                      <td>{transaction.description}</td>
                      <td
                        className={
                          transaction.type === "income"
                            ? "income-text"
                            : "expense-text"
                        }
                      >
                        {transaction.type === "income" ? "+" : "-"}$
                        {transaction.amount.toFixed(2)}
                      </td>
                      <td>
                        <button
                          className="delete-button"
                          onClick={() => handleDelete(transaction.id)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default TransactionsPage;