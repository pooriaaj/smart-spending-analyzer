const BUDGET_STATUS_PRIORITY = {
  over_budget: 0,
  at_risk: 1,
  on_track: 2,
};

export function formatMoney(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

export function buildBudgetPaceLabel(budget) {
  if (!budget) return "";

  if (budget.days_remaining > 0 && budget.daily_allowance != null) {
    const allowanceText =
      budget.daily_allowance >= 0
        ? `${formatMoney(budget.daily_allowance)}/day left`
        : `${formatMoney(Math.abs(budget.daily_allowance))}/day over pace`;
    const paceText =
      budget.daily_pace != null ? ` Current pace: ${formatMoney(budget.daily_pace)}/day.` : "";
    return `${allowanceText} for the next ${budget.days_remaining} day(s).${paceText}`;
  }

  if (budget.days_remaining === 0 && budget.daily_pace != null) {
    return `Final average pace: ${formatMoney(budget.daily_pace)}/day across ${budget.days_total} day(s).`;
  }

  if (budget.days_elapsed === 0 && budget.daily_allowance != null) {
    return `Planned average pace: ${formatMoney(budget.daily_allowance)}/day across ${budget.days_total} day(s).`;
  }

  return "";
}

export function buildBudgetProjectionLabel(budget) {
  if (
    !budget ||
    budget.projected_spent_amount == null ||
    budget.projected_remaining_amount == null
  ) {
    return "";
  }

  const finishText =
    budget.projected_remaining_amount >= 0
      ? `${formatMoney(budget.projected_remaining_amount)} remaining`
      : `${formatMoney(Math.abs(budget.projected_remaining_amount))} over`;

  return `Projected month-end: ${formatMoney(budget.projected_spent_amount)} spent, ${finishText}.`;
}

export function buildBudgetForecastSummary(summary) {
  if (!summary) return "";

  if (summary.projected_over_budget_count > 0) {
    const finishText =
      summary.projected_total_remaining >= 0
        ? `${formatMoney(summary.projected_total_remaining)} remaining overall`
        : `${formatMoney(Math.abs(summary.projected_total_remaining))} over overall`;
    return `At the current pace, ${summary.projected_over_budget_count} budget(s) are projected to finish over budget, with ${finishText}.`;
  }

  if (summary.projected_at_risk_count > 0) {
    return `At the current pace, ${summary.projected_at_risk_count} budget(s) are projected to get tight before month end.`;
  }

  return `At the current pace, these budgets are projected to finish with ${formatMoney(summary.projected_total_remaining)} remaining overall.`;
}

export function getBudgetPriority(budget) {
  const currentPriority = BUDGET_STATUS_PRIORITY[budget?.status] ?? 3;
  const projectedPriority = BUDGET_STATUS_PRIORITY[budget?.projected_status] ?? 3;
  return Math.min(currentPriority, projectedPriority);
}
