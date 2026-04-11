import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api, { handleApiAuthError } from "../services/api";
import AccountSelector from "../components/AccountSelector";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId } from "../services/accountStorage";

function SimulatorPage() {
  const navigate = useNavigate();
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [months, setMonths] = useState(6);
  const [incomeAdjustment, setIncomeAdjustment] = useState(0);
  const [expenseAdjustment, setExpenseAdjustment] = useState(0);
  const [simulatorData, setSimulatorData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [themeMode, setThemeMode] = useState(
    document.documentElement.getAttribute("data-theme") || "light"
  );

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setThemeMode(document.documentElement.getAttribute("data-theme") || "light");
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const fetchSimulation = async () => {
      try {
        setLoading(true);
        setError("");
        const response = await api.get("/analytics/future-simulator", {
          params: {
            account_id: normalizedAccountId,
            months,
            income_adjustment: Number(incomeAdjustment) || 0,
            expense_adjustment: Number(expenseAdjustment) || 0,
          },
        });
        setSimulatorData(response.data);
      } catch (fetchError) {
        if (!handleApiAuthError(fetchError, navigate)) {
          setError("Failed to load simulator.");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchSimulation();
  }, [navigate, normalizedAccountId, months, incomeAdjustment, expenseAdjustment]);

  const chartTheme = useMemo(() => {
    const isDark = themeMode === "dark";
    return {
      text: isDark ? "#cbd5e1" : "#475569",
      grid: isDark ? "rgba(148, 163, 184, 0.12)" : "rgba(15, 23, 42, 0.08)",
      tooltipBg: isDark ? "rgba(15, 23, 42, 0.96)" : "rgba(255, 255, 255, 0.96)",
      tooltipBorder: isDark ? "rgba(148, 163, 184, 0.16)" : "rgba(15, 23, 42, 0.08)",
      balanceLine: isDark ? "#60a5fa" : "#2563eb",
      netLine: isDark ? "#4ade80" : "#16a34a",
    };
  }, [themeMode]);

  const scopeDescription =
    normalizedAccountId == null
      ? "Projection uses all accounts combined."
      : "Projection uses only the selected account.";

  const riskMeta = useMemo(() => {
    const riskLevel = simulatorData?.risk_level;
    if (riskLevel === "high") {
      return { label: "High risk", className: "simulator-risk-pill simulator-risk-high" };
    }
    if (riskLevel === "watch") {
      return { label: "Watch closely", className: "simulator-risk-pill simulator-risk-watch" };
    }
    return { label: "Healthy pace", className: "simulator-risk-pill simulator-risk-healthy" };
  }, [simulatorData]);

  const customTooltipStyle = {
    backgroundColor: chartTheme.tooltipBg,
    border: `1px solid ${chartTheme.tooltipBorder}`,
    borderRadius: "14px",
    color: chartTheme.text,
    boxShadow:
      themeMode === "dark"
        ? "0 18px 40px rgba(0, 0, 0, 0.28)"
        : "0 18px 40px rgba(15, 23, 42, 0.12)",
  };

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">Smart Spending Analyzer</p>
            <h1>Future Simulator</h1>
            <p className="hero-subtitle">
              Project your balance forward, test monthly changes, and see how today&apos;s pace
              could play out over the next few months.
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              Back to Dashboard
            </button>
            <button className="secondary-button" onClick={() => navigate("/analytics")}>
              Analytics
            </button>
            <button className="secondary-button" onClick={() => navigate("/budgets")}>
              Budgets
            </button>
            <button className="secondary-button" onClick={() => navigate("/assistant")}>
              Assistant
            </button>
          </div>
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <h2>Scenario Controls</h2>
            <p>{scopeDescription}</p>
          </div>

          <div className="simulator-controls-grid">
            <AccountSelector label="Simulator scope" onChange={setSelectedAccountId} />

            <div className="budget-form-field">
              <label htmlFor="simulator-months">Months ahead</label>
              <input
                id="simulator-months"
                type="number"
                min="1"
                max="12"
                value={months}
                onChange={(event) => setMonths(event.target.value)}
              />
            </div>

            <div className="budget-form-field">
              <label htmlFor="simulator-income-adjustment">Monthly income change</label>
              <input
                id="simulator-income-adjustment"
                type="number"
                step="0.01"
                value={incomeAdjustment}
                onChange={(event) => setIncomeAdjustment(event.target.value)}
                placeholder="0"
              />
            </div>

            <div className="budget-form-field">
              <label htmlFor="simulator-expense-adjustment">Monthly expense change</label>
              <input
                id="simulator-expense-adjustment"
                type="number"
                step="0.01"
                value={expenseAdjustment}
                onChange={(event) => setExpenseAdjustment(event.target.value)}
                placeholder="0"
              />
            </div>
          </div>

          <p className="budget-inline-note">
            Positive expense values simulate extra spending. Negative expense values simulate
            savings or cuts.
          </p>
        </div>

        {error && (
          <div className="dashboard-card">
            <p className="error-text">{error}</p>
          </div>
        )}

        {loading ? (
          <div className="dashboard-card">
            <div className="empty-state">
              <p>Running your scenario...</p>
            </div>
          </div>
        ) : (
          <>
            <div className="summary-grid">
              <div className="summary-card balance-card">
                <span className="card-label">Starting Balance</span>
                <p>${simulatorData?.starting_balance?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card income-card">
                <span className="card-label">Monthly Net</span>
                <p>${simulatorData?.monthly_net_change?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card top-card">
                <span className="card-label">Projected Change</span>
                <p>${simulatorData?.projected_change_amount?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card expense-card">
                <span className="card-label">Projected End Balance</span>
                <p>${simulatorData?.projected_end_balance?.toFixed(2) || "0.00"}</p>
              </div>
            </div>

            <div className="dashboard-card">
              <div className="simulator-overview-top">
                <div>
                  <div className="section-header">
                    <h2>Scenario Readout</h2>
                    <p>{simulatorData?.scope_label}</p>
                  </div>
                  <p className="budget-forecast-banner">{simulatorData?.narrative}</p>
                </div>
                <span className={riskMeta.className}>{riskMeta.label}</span>
              </div>

              <div className="simulator-metrics-grid">
                <div className="simulator-metric-card">
                  <span>Baseline monthly income</span>
                  <strong>${simulatorData?.baseline_monthly_income?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>Baseline monthly expenses</span>
                  <strong>${simulatorData?.baseline_monthly_expenses?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>Scenario income</span>
                  <strong>${simulatorData?.adjusted_monthly_income?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>Scenario expenses</span>
                  <strong>${simulatorData?.adjusted_monthly_expenses?.toFixed(2) || "0.00"}</strong>
                </div>
              </div>
            </div>

            <div className="dashboard-card simulator-chart-card">
              <div className="section-header">
                <h2>Projected Balance Path</h2>
                <p>
                  Month-by-month ending balance starting from {simulatorData?.start_month}.
                </p>
              </div>

              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={simulatorData?.timeline || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                  <XAxis dataKey="month" tick={{ fill: chartTheme.text, fontSize: 12 }} />
                  <YAxis tick={{ fill: chartTheme.text, fontSize: 12 }} />
                  <Tooltip contentStyle={customTooltipStyle} />
                  <Line
                    type="monotone"
                    dataKey="ending_balance"
                    stroke={chartTheme.balanceLine}
                    strokeWidth={3}
                    dot={{ r: 4 }}
                    name="Ending balance"
                  />
                  <Line
                    type="monotone"
                    dataKey="net_change"
                    stroke={chartTheme.netLine}
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    dot={false}
                    name="Monthly net"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-grid">
              <div className="dashboard-card">
                <div className="section-header">
                  <h2>Assumptions</h2>
                  <p>What this scenario is using behind the scenes.</p>
                </div>

                <ul className="simulator-assumptions-list">
                  {(simulatorData?.assumptions || []).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="dashboard-card">
                <div className="section-header">
                  <h2>Scenario Timeline</h2>
                  <p>Projected income, expenses, and ending balance for each month.</p>
                </div>

                <div className="transactions-table-wrapper">
                  <table className="transactions-table">
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th>Income</th>
                        <th>Expenses</th>
                        <th>Net</th>
                        <th>Ending Balance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(simulatorData?.timeline || []).map((row) => (
                        <tr key={row.month}>
                          <td>{row.month}</td>
                          <td>${row.income.toFixed(2)}</td>
                          <td>${row.expenses.toFixed(2)}</td>
                          <td>${row.net_change.toFixed(2)}</td>
                          <td>${row.ending_balance.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default SimulatorPage;
