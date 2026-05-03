const BUDGET_STATUS_PRIORITY = {
  over_budget: 0,
  at_risk: 1,
  on_track: 2,
};

export function formatMoney(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function translate(t, key, params, fallback) {
  return typeof t === "function" ? t(key, params) : fallback;
}

export function buildBudgetPaceLabel(budget, t) {
  if (!budget) return "";

  if (budget.days_remaining > 0 && budget.daily_allowance != null) {
    const allowanceText =
      budget.daily_allowance >= 0
        ? translate(
            t,
            "budgets.paceAllowanceLeft",
            { amount: Number(budget.daily_allowance).toFixed(2) },
            `${formatMoney(budget.daily_allowance)}/day left`
          )
        : translate(
            t,
            "budgets.paceOver",
            { amount: Number(Math.abs(budget.daily_allowance)).toFixed(2) },
            `${formatMoney(Math.abs(budget.daily_allowance))}/day over pace`
          );
    const paceText =
      budget.daily_pace != null
        ? translate(
            t,
            "budgets.currentPace",
            { amount: Number(budget.daily_pace).toFixed(2) },
            ` Current pace: ${formatMoney(budget.daily_pace)}/day.`
          )
        : "";
    return translate(
      t,
      "budgets.paceNextDays",
      { pace: allowanceText, days: budget.days_remaining, currentPace: paceText },
      `${allowanceText} for the next ${budget.days_remaining} day(s).${paceText}`
    );
  }

  if (budget.days_remaining === 0 && budget.daily_pace != null) {
    return translate(
      t,
      "budgets.finalAveragePace",
      { amount: Number(budget.daily_pace).toFixed(2), days: budget.days_total },
      `Final average pace: ${formatMoney(budget.daily_pace)}/day across ${budget.days_total} day(s).`
    );
  }

  if (budget.days_elapsed === 0 && budget.daily_allowance != null) {
    return translate(
      t,
      "budgets.plannedAveragePace",
      { amount: Number(budget.daily_allowance).toFixed(2), days: budget.days_total },
      `Planned average pace: ${formatMoney(budget.daily_allowance)}/day across ${budget.days_total} day(s).`
    );
  }

  return "";
}

export function buildBudgetProjectionLabel(budget, t) {
  if (
    !budget ||
    budget.projected_spent_amount == null ||
    budget.projected_remaining_amount == null
  ) {
    return "";
  }

  const finishText =
    budget.projected_remaining_amount >= 0
      ? translate(
          t,
          "budgets.projectedRemaining",
          { amount: Number(budget.projected_remaining_amount).toFixed(2) },
          `${formatMoney(budget.projected_remaining_amount)} remaining`
        )
      : translate(
          t,
          "budgets.projectedOver",
          { amount: Number(Math.abs(budget.projected_remaining_amount)).toFixed(2) },
          `${formatMoney(Math.abs(budget.projected_remaining_amount))} over`
        );

  return translate(
    t,
    "budgets.projectedMonthEnd",
    { spent: formatMoney(budget.projected_spent_amount), finish: finishText },
    `Projected month-end: ${formatMoney(budget.projected_spent_amount)} spent, ${finishText}.`
  );
}

export function buildBudgetForecastSummary(summary, t) {
  if (!summary) return "";

  if (summary.projected_over_budget_count > 0) {
    const finishText =
      summary.projected_total_remaining >= 0
        ? translate(
            t,
            "budgets.remainingOverall",
            { amount: Number(summary.projected_total_remaining).toFixed(2) },
            `${formatMoney(summary.projected_total_remaining)} remaining overall`
          )
        : translate(
            t,
            "budgets.overOverall",
            { amount: Number(Math.abs(summary.projected_total_remaining)).toFixed(2) },
            `${formatMoney(Math.abs(summary.projected_total_remaining))} over overall`
          );
    return translate(
      t,
      "budgets.forecastOver",
      { count: summary.projected_over_budget_count, finish: finishText },
      `At the current pace, ${summary.projected_over_budget_count} budget(s) are projected to finish over budget, with ${finishText}.`
    );
  }

  if (summary.projected_at_risk_count > 0) {
    return translate(
      t,
      "budgets.forecastRisk",
      { count: summary.projected_at_risk_count },
      `At the current pace, ${summary.projected_at_risk_count} budget(s) are projected to get tight before month end.`
    );
  }

  return translate(
    t,
    "budgets.forecastHealthy",
    { amount: Number(summary.projected_total_remaining || 0).toFixed(2) },
    `At the current pace, these budgets are projected to finish with ${formatMoney(summary.projected_total_remaining)} remaining overall.`
  );
}

export function getBudgetPriority(budget) {
  const currentPriority = BUDGET_STATUS_PRIORITY[budget?.status] ?? 3;
  const projectedPriority = BUDGET_STATUS_PRIORITY[budget?.projected_status] ?? 3;
  return Math.min(currentPriority, projectedPriority);
}
