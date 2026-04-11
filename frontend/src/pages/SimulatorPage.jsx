import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
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
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
  setSelectedAccountId as persistSelectedAccountId,
} from "../services/accountStorage";

const SCENARIO_PRESETS = [
  {
    label: "Cut $200 Expenses",
    description: "Model a steady monthly expense reduction.",
    months: 6,
    incomeAdjustment: 0,
    expenseAdjustment: -200,
    targetBalance: "",
    eventAmount: "",
    eventMonthOffset: 1,
    eventLabel: "",
  },
  {
    label: "Add $500 Income",
    description: "See the impact of a side income stream.",
    months: 6,
    incomeAdjustment: 500,
    expenseAdjustment: 0,
    targetBalance: "",
    eventAmount: "",
    eventMonthOffset: 1,
    eventLabel: "",
  },
  {
    label: "Reach $10,000",
    description: "Aim for a round-number balance goal.",
    months: 6,
    incomeAdjustment: 0,
    expenseAdjustment: 0,
    targetBalance: 10000,
    eventAmount: "",
    eventMonthOffset: 1,
    eventLabel: "",
  },
  {
    label: "Plan $1,200 Purchase",
    description: "Drop a one-time expense into the second month.",
    months: 6,
    incomeAdjustment: 0,
    expenseAdjustment: 0,
    targetBalance: "",
    eventAmount: -1200,
    eventMonthOffset: 2,
    eventLabel: "Planned purchase",
  },
  {
    label: "Reset Scenario",
    description: "Go back to the baseline path.",
    months: 6,
    incomeAdjustment: 0,
    expenseAdjustment: 0,
    targetBalance: "",
    eventAmount: "",
    eventMonthOffset: 1,
    eventLabel: "",
  },
];

function buildReductionBudgetTargets(items) {
  return Array.from(
    (items || [])
      .map((item) => ({
        category: String(item?.category || "").trim(),
        amount: Number(item?.suggested_budget_amount),
      }))
      .filter((item) => item.category && Number.isFinite(item.amount) && item.amount > 0)
      .reduce((map, item) => {
        map.set(item.category.toLowerCase(), item);
        return map;
      }, new Map()).values()
  );
}

function shiftMonthLabel(month, offset) {
  const [yearText, monthText] = String(month || "").split("-");
  const year = Number(yearText);
  const monthNumber = Number(monthText);

  if (!year || !monthNumber) {
    return `Month ${offset + 1}`;
  }

  const totalMonths = year * 12 + (monthNumber - 1) + offset;
  const shiftedYear = Math.floor(totalMonths / 12);
  const shiftedMonth = (totalMonths % 12) + 1;
  return `${shiftedYear.toString().padStart(4, "0")}-${shiftedMonth.toString().padStart(2, "0")}`;
}

function SimulatorPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedAccountId, setSelectedAccountId] = useState(getSelectedAccountId());
  const [months, setMonths] = useState(
    Number(searchParams.get("months")) > 0 ? Number(searchParams.get("months")) : 6
  );
  const [incomeAdjustment, setIncomeAdjustment] = useState(
    searchParams.get("income_adjustment") || 0
  );
  const [expenseAdjustment, setExpenseAdjustment] = useState(
    searchParams.get("expense_adjustment") || 0
  );
  const [targetBalance, setTargetBalance] = useState(searchParams.get("target_balance") || "");
  const [eventAmount, setEventAmount] = useState(searchParams.get("event_amount") || "");
  const [eventMonthOffset, setEventMonthOffset] = useState(
    Number(searchParams.get("event_month_offset")) > 0
      ? Number(searchParams.get("event_month_offset"))
      : 1
  );
  const [eventLabel, setEventLabel] = useState(searchParams.get("event_label") || "");
  const [simulatorData, setSimulatorData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [applyingReductionPlan, setApplyingReductionPlan] = useState(false);
  const [reductionPlanMessage, setReductionPlanMessage] = useState("");
  const [reductionPlanError, setReductionPlanError] = useState("");
  const [scenarioLinkMessage, setScenarioLinkMessage] = useState("");
  const [scenarioLinkError, setScenarioLinkError] = useState("");
  const [themeMode, setThemeMode] = useState(
    document.documentElement.getAttribute("data-theme") || "light"
  );

  const normalizedAccountId =
    selectedAccountId === ALL_ACCOUNTS_VALUE ? undefined : Number(selectedAccountId);
  const searchParamString = searchParams.toString();

  useEffect(() => {
    persistSelectedAccountId(String(selectedAccountId || ALL_ACCOUNTS_VALUE));
  }, [selectedAccountId]);

  useEffect(() => {
    const monthsParam = Number(searchParams.get("months"));
    const incomeParam = searchParams.get("income_adjustment");
    const expenseParam = searchParams.get("expense_adjustment");
    const targetParam = searchParams.get("target_balance");
    const accountParam = searchParams.get("account_id");
    const eventAmountParam = searchParams.get("event_amount");
    const eventMonthParam = Number(searchParams.get("event_month_offset"));
    const eventLabelParam = searchParams.get("event_label");

    if (monthsParam > 0) {
      setMonths(monthsParam);
    }
    if (incomeParam !== null) {
      setIncomeAdjustment(incomeParam);
    }
    if (expenseParam !== null) {
      setExpenseAdjustment(expenseParam);
    }
    if (targetParam !== null) {
      setTargetBalance(targetParam);
    }
    if (accountParam === ALL_ACCOUNTS_VALUE) {
      setSelectedAccountId(ALL_ACCOUNTS_VALUE);
    } else if (Number(accountParam) > 0) {
      setSelectedAccountId(String(Number(accountParam)));
    }
    if (eventAmountParam !== null) {
      setEventAmount(eventAmountParam);
    }
    if (eventMonthParam > 0) {
      setEventMonthOffset(eventMonthParam);
    }
    if (eventLabelParam !== null) {
      setEventLabel(eventLabelParam);
    }
  }, [searchParams]);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set(
      "account_id",
      selectedAccountId === ALL_ACCOUNTS_VALUE ? ALL_ACCOUNTS_VALUE : String(selectedAccountId)
    );
    params.set("months", String(Math.max(1, Math.min(Number(months) || 6, 12))));

    if (Number(incomeAdjustment) !== 0) {
      params.set("income_adjustment", String(Number(incomeAdjustment)));
    }
    if (Number(expenseAdjustment) !== 0) {
      params.set("expense_adjustment", String(Number(expenseAdjustment)));
    }
    if (Number(targetBalance) > 0) {
      params.set("target_balance", String(Number(targetBalance)));
    }
    if (Number(eventAmount) !== 0) {
      params.set("event_amount", String(Number(eventAmount)));
      params.set("event_month_offset", String(Math.max(1, Number(eventMonthOffset) || 1)));
      if (eventLabel.trim()) {
        params.set("event_label", eventLabel.trim());
      }
    }

    const nextParamString = params.toString();
    if (nextParamString !== searchParamString) {
      setSearchParams(params, { replace: true });
    }
  }, [
    selectedAccountId,
    months,
    incomeAdjustment,
    expenseAdjustment,
    targetBalance,
    eventAmount,
    eventMonthOffset,
    eventLabel,
    searchParamString,
    setSearchParams,
  ]);

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
        setReductionPlanMessage("");
        setReductionPlanError("");
        const response = await api.get("/analytics/future-simulator", {
          params: {
            account_id: normalizedAccountId,
            months,
            income_adjustment: Number(incomeAdjustment) || 0,
            expense_adjustment: Number(expenseAdjustment) || 0,
            target_balance: Number(targetBalance) > 0 ? Number(targetBalance) : undefined,
            event_amount: Number(eventAmount) || 0,
            event_month_offset:
              Number(eventAmount) !== 0 && Number(eventMonthOffset) > 0
                ? Number(eventMonthOffset)
                : undefined,
            event_label: eventLabel.trim() || undefined,
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
  }, [
    navigate,
    normalizedAccountId,
    months,
    incomeAdjustment,
    expenseAdjustment,
    targetBalance,
    eventAmount,
    eventMonthOffset,
    eventLabel,
  ]);

  const chartTheme = useMemo(() => {
    const isDark = themeMode === "dark";
    return {
      text: isDark ? "#cbd5e1" : "#475569",
      grid: isDark ? "rgba(148, 163, 184, 0.12)" : "rgba(15, 23, 42, 0.08)",
      tooltipBg: isDark ? "rgba(15, 23, 42, 0.96)" : "rgba(255, 255, 255, 0.96)",
      tooltipBorder: isDark ? "rgba(148, 163, 184, 0.16)" : "rgba(15, 23, 42, 0.08)",
      balanceLine: isDark ? "#60a5fa" : "#2563eb",
      baselineLine: isDark ? "#a78bfa" : "#7c3aed",
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

  const applyPreset = (preset) => {
    setMonths(preset.months);
    setIncomeAdjustment(preset.incomeAdjustment);
    setExpenseAdjustment(preset.expenseAdjustment);
    setTargetBalance(
      preset.targetBalance === "" ? "" : String(preset.targetBalance)
    );
    setEventAmount(preset.eventAmount === "" ? "" : String(preset.eventAmount));
    setEventMonthOffset(preset.eventMonthOffset || 1);
    setEventLabel(preset.eventLabel || "");
  };

  const eventMonthOptions = useMemo(() => {
    const optionCount = Math.max(1, Math.min(Number(months) || 1, 12));
    const startMonth = simulatorData?.start_month;
    return Array.from({ length: optionCount }, (_, index) => ({
      value: index + 1,
      label: startMonth ? shiftMonthLabel(startMonth, index) : `Month ${index + 1}`,
    }));
  }, [months, simulatorData?.start_month]);

  const handleApplyReductionPlan = async () => {
    const targets = buildReductionBudgetTargets(simulatorData?.reduction_plan);
    if (!simulatorData?.start_month || targets.length === 0) {
      return;
    }

    try {
      setApplyingReductionPlan(true);
      setReductionPlanError("");
      setReductionPlanMessage("");
      const response = await api.post("/budgets/bulk-upsert", {
        month: simulatorData.start_month,
        account_id: normalizedAccountId,
        items: targets,
      });
      setReductionPlanMessage(
        response.data?.message ||
          `Applied ${targets.length} budget target${targets.length === 1 ? "" : "s"} to ${simulatorData.start_month}.`
      );
    } catch (applyError) {
      if (!handleApiAuthError(applyError, navigate)) {
        setReductionPlanError(
          applyError?.response?.data?.detail || "Failed to apply reduction plan to budgets."
        );
      }
    } finally {
      setApplyingReductionPlan(false);
    }
  };

  const handleCopyScenarioLink = async () => {
    try {
      setScenarioLinkError("");
      setScenarioLinkMessage("");
      await navigator.clipboard.writeText(window.location.href);
      setScenarioLinkMessage("Scenario link copied.");
    } catch (copyError) {
      console.error("Failed to copy scenario link:", copyError);
      setScenarioLinkError("Could not copy the scenario link from this browser.");
    }
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
            <div>
              <h2>Scenario Controls</h2>
              <p>{scopeDescription}</p>
            </div>
            <div className="budget-section-actions">
              <button type="button" className="secondary-button" onClick={handleCopyScenarioLink}>
                Copy Scenario Link
              </button>
            </div>
          </div>

          <div className="simulator-preset-grid">
            {SCENARIO_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                className="simulator-preset-button"
                onClick={() => applyPreset(preset)}
              >
                <strong>{preset.label}</strong>
                <span>{preset.description}</span>
              </button>
            ))}
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

            <div className="budget-form-field">
              <label htmlFor="simulator-target-balance">Target ending balance</label>
              <input
                id="simulator-target-balance"
                type="number"
                step="0.01"
                min="0"
                value={targetBalance}
                onChange={(event) => setTargetBalance(event.target.value)}
                placeholder="Optional"
              />
            </div>

            <div className="budget-form-field">
              <label htmlFor="simulator-event-amount">One-time event amount</label>
              <input
                id="simulator-event-amount"
                type="number"
                step="0.01"
                value={eventAmount}
                onChange={(event) => setEventAmount(event.target.value)}
                placeholder="-1200"
              />
            </div>

            <div className="budget-form-field">
              <label htmlFor="simulator-event-month">Event month</label>
              <select
                id="simulator-event-month"
                value={eventMonthOffset}
                onChange={(event) => setEventMonthOffset(Number(event.target.value))}
              >
                {eventMonthOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="budget-form-field">
              <label htmlFor="simulator-event-label">Event label</label>
              <input
                id="simulator-event-label"
                type="text"
                maxLength="80"
                value={eventLabel}
                onChange={(event) => setEventLabel(event.target.value)}
                placeholder="Planned trip"
              />
            </div>
          </div>

          <p className="budget-inline-note">
            Positive expense values simulate extra spending. Negative expense values simulate
            savings or cuts.
          </p>
          <p className="budget-inline-note">
            One-time events use positive values for windfalls like bonuses and negative values for
            planned expenses like travel or repairs.
          </p>
          <p className="budget-inline-note">
            Scenario links keep the simulator controls and scope together, so you can reload or
            revisit the same plan quickly.
          </p>
          {scenarioLinkMessage && <p className="success-text">{scenarioLinkMessage}</p>}
          {scenarioLinkError && <p className="error-text">{scenarioLinkError}</p>}
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
                <span className="card-label">Scenario Impact</span>
                <p>${simulatorData?.scenario_impact_amount?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card expense-card">
                <span className="card-label">Projected End Balance</span>
                <p>${simulatorData?.projected_end_balance?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card top-card">
                <span className="card-label">One-Time Event</span>
                <p>
                  {simulatorData?.one_time_event_amount != null
                    ? `${simulatorData.one_time_event_label || "Planned event"} ${
                        simulatorData.one_time_event_amount > 0 ? "+" : "-"
                      }$${Math.abs(simulatorData.one_time_event_amount).toFixed(2)}`
                    : "None"}
                </p>
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
                <div className="simulator-metric-card">
                  <span>Baseline end balance</span>
                  <strong>${simulatorData?.baseline_projected_end_balance?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>Scenario end balance</span>
                  <strong>${simulatorData?.projected_end_balance?.toFixed(2) || "0.00"}</strong>
                </div>
                {simulatorData?.one_time_event_amount != null && (
                  <div className="simulator-metric-card">
                    <span>{simulatorData.one_time_event_month || "Planned event"}</span>
                    <strong>
                      {(simulatorData.one_time_event_label || "One-time event")}:{" "}
                      {simulatorData.one_time_event_amount > 0 ? "+" : "-"}$
                      {Math.abs(simulatorData.one_time_event_amount).toFixed(2)}
                    </strong>
                  </div>
                )}
              </div>
            </div>

            <div className="dashboard-card simulator-chart-card">
              <div className="section-header">
                <h2>Projected Balance Path</h2>
                <p>
                  Compare the baseline path against your adjusted scenario starting from {simulatorData?.start_month}.
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
                    dataKey="baseline_ending_balance"
                    stroke={chartTheme.baselineLine}
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    dot={false}
                    name="Baseline balance"
                  />
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
              {simulatorData?.goal_balance != null && (
                <div className="dashboard-card">
                  <div className="section-header">
                    <h2>Goal Planner</h2>
                    <p>What this scenario would take to reach your target balance.</p>
                  </div>

                  <div className="simulator-metrics-grid">
                    <div className="simulator-metric-card">
                      <span>Target balance</span>
                      <strong>${simulatorData.goal_balance.toFixed(2)}</strong>
                    </div>
                    <div className="simulator-metric-card">
                      <span>Gap from current scenario</span>
                      <strong>${(simulatorData.goal_gap_amount || 0).toFixed(2)}</strong>
                    </div>
                    <div className="simulator-metric-card">
                      <span>Required monthly net</span>
                      <strong>${(simulatorData.required_monthly_net || 0).toFixed(2)}</strong>
                    </div>
                    <div className="simulator-metric-card">
                      <span>Needed monthly improvement</span>
                      <strong>${(simulatorData.required_income_lift || 0).toFixed(2)}</strong>
                    </div>
                  </div>

                  <p className="budget-forecast-banner">{simulatorData.goal_note}</p>
                  <p className="budget-inline-note">
                    Equivalent paths: earn about $
                    {(simulatorData.required_income_lift || 0).toFixed(2)} more each month, spend
                    about ${(simulatorData.required_expense_reduction || 0).toFixed(2)} less, or
                    combine both.
                  </p>
                </div>
              )}

              {(simulatorData?.reduction_plan || []).length > 0 && (
                <div className="dashboard-card">
                  <div className="section-header">
                    <div>
                      <h2>Reduction Plan</h2>
                      <p>
                        Category-level places to look first if you want to close the gap through
                        spending cuts.
                      </p>
                    </div>
                    <div className="budget-section-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={handleApplyReductionPlan}
                        disabled={applyingReductionPlan}
                      >
                        {applyingReductionPlan
                          ? "Applying..."
                          : `Apply To ${simulatorData.start_month} Budgets`}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() =>
                          navigate(
                            `/budgets?month=${encodeURIComponent(simulatorData.start_month)}`
                          )
                        }
                      >
                        Open {simulatorData.start_month} Budgets
                      </button>
                    </div>
                  </div>

                  <div className="simulator-metrics-grid">
                    <div className="simulator-metric-card">
                      <span>Monthly cut target</span>
                      <strong>${(simulatorData.reduction_plan_target || 0).toFixed(2)}</strong>
                    </div>
                    <div className="simulator-metric-card">
                      <span>Plan coverage</span>
                      <strong>${(simulatorData.reduction_plan_coverage_amount || 0).toFixed(2)}</strong>
                    </div>
                  </div>

                  {reductionPlanMessage && <p className="success-text">{reductionPlanMessage}</p>}
                  {reductionPlanError && <p className="error-text">{reductionPlanError}</p>}

                  <div className="budget-insight-list">
                    {simulatorData.reduction_plan.map((item) => (
                      <div
                        key={`reduction-plan-${item.category}`}
                        className="budget-insight-item"
                      >
                        <div className="budget-insight-top">
                          <strong>{item.category}</strong>
                          <span className="budget-insight-badge budget-insight-badge-watch">
                            Cut ${item.suggested_monthly_reduction.toFixed(2)}/mo
                          </span>
                        </div>
                        <p className="budget-insight-title">
                          Current monthly spend: ${item.current_monthly_spend.toFixed(2)}
                        </p>
                        <p className="budget-inline-note">
                          About {item.share_percent.toFixed(1)}% of this plan comes from {item.category}. {item.reason}
                        </p>
                        <div className="budget-insight-actions">
                          <span className="budget-inline-note">
                            Suggested next-month budget: ${item.suggested_budget_amount.toFixed(2)}
                          </span>
                          <div className="budget-section-actions">
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                navigate(
                                  `/budgets?month=${encodeURIComponent(
                                    simulatorData.start_month
                                  )}&category=${encodeURIComponent(
                                    item.category
                                  )}&amount=${encodeURIComponent(item.suggested_budget_amount)}`
                                )
                              }
                            >
                              Open Budget Target
                            </button>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                navigate(
                                  `/transactions?category=${encodeURIComponent(item.category)}&type=expense`
                                )
                              }
                            >
                              Review Transactions
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

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
                        <th>One-Time Event</th>
                        <th>Net</th>
                        <th>Baseline Balance</th>
                        <th>Ending Balance</th>
                        <th>Scenario Delta</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(simulatorData?.timeline || []).map((row) => (
                        <tr key={row.month}>
                          <td>{row.month}</td>
                          <td>${row.income.toFixed(2)}</td>
                          <td>${row.expenses.toFixed(2)}</td>
                          <td>
                            {row.one_time_event_amount
                              ? `${row.one_time_event_label || "Planned event"} ${
                                  row.one_time_event_amount > 0 ? "+" : "-"
                                }$${Math.abs(row.one_time_event_amount).toFixed(2)}`
                              : "None"}
                          </td>
                          <td>${row.net_change.toFixed(2)}</td>
                          <td>${row.baseline_ending_balance.toFixed(2)}</td>
                          <td>${row.ending_balance.toFixed(2)}</td>
                          <td>${row.balance_delta.toFixed(2)}</td>
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
