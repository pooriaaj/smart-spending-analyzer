import { useCallback, useEffect, useMemo, useState } from "react";
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
import { useLanguage } from "../i18n/LanguageContext";
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
  setSelectedAccountId as persistSelectedAccountId,
} from "../services/accountStorage";
import {
  formatCategoryLabel,
  formatRecurringReviewReason,
  formatScopeLabel,
} from "../utils/displayLabels";
import { getApiErrorMessage, getApiSuccessMessage } from "../utils/errorUtils";

const SCENARIO_PRESETS = [
  {
    labelKey: "simulator.presetCutExpenses",
    descriptionKey: "simulator.presetCutExpensesDetail",
    months: 6,
    incomeAdjustment: 0,
    expenseAdjustment: -200,
    targetBalance: "",
    eventAmount: "",
    eventMonthOffset: 1,
    eventLabel: "",
  },
  {
    labelKey: "simulator.presetAddIncome",
    descriptionKey: "simulator.presetAddIncomeDetail",
    months: 6,
    incomeAdjustment: 500,
    expenseAdjustment: 0,
    targetBalance: "",
    eventAmount: "",
    eventMonthOffset: 1,
    eventLabel: "",
  },
  {
    labelKey: "simulator.presetReachGoal",
    descriptionKey: "simulator.presetReachGoalDetail",
    months: 6,
    incomeAdjustment: 0,
    expenseAdjustment: 0,
    targetBalance: 10000,
    eventAmount: "",
    eventMonthOffset: 1,
    eventLabel: "",
  },
  {
    labelKey: "simulator.presetPlanPurchase",
    descriptionKey: "simulator.presetPlanPurchaseDetail",
    months: 6,
    incomeAdjustment: 0,
    expenseAdjustment: 0,
    targetBalance: "",
    eventAmount: -1200,
    eventMonthOffset: 2,
    eventLabelKey: "simulator.plannedPurchase",
  },
  {
    labelKey: "simulator.presetReset",
    descriptionKey: "simulator.presetResetDetail",
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

function formatSignedScenarioAmount(value) {
  const numericValue = Number(value) || 0;
  return `${numericValue >= 0 ? "+" : "-"}$${Math.abs(numericValue).toFixed(2)}`;
}

function formatScenarioCurrency(value) {
  return `$${(Number(value) || 0).toFixed(2)}`;
}

const SAVED_SCENARIO_SORT_OPTIONS = [
  { value: "newest", labelKey: "simulator.newest" },
  { value: "strongest", labelKey: "simulator.strongest" },
  { value: "safest", labelKey: "simulator.safest" },
  { value: "goal", labelKey: "simulator.goalProgress" },
];

const SAVED_SCENARIO_FILTER_OPTIONS = [
  { value: "all", labelKey: "simulator.allPlans" },
  { value: "healthy", labelKey: "simulator.healthyPlans" },
  { value: "attention", labelKey: "simulator.attentionPlans" },
  { value: "goal", labelKey: "simulator.goalPlans" },
  { value: "event", labelKey: "simulator.eventPlans" },
];

const RECOMMENDATION_FILTER_OPTIONS = [
  { value: "all", labelKey: "simulator.allIdeas" },
  { value: "cash_flow", labelKey: "simulator.cashFlow" },
  { value: "recurring", labelKey: "simulator.recurring" },
  { value: "budget_pressure", labelKey: "simulator.budgetRisk" },
  { value: "saved", labelKey: "simulator.saved" },
];

function getRecommendationSourceLabel(source, t) {
  if (source === "cash_flow") return t("simulator.cashFlow");
  if (source === "recurring" || source === "recurring_bundle") return t("simulator.recurring");
  if (source === "budget_pressure") return t("simulator.budgetRisk");
  return t("simulator.strategy");
}

function getRecommendationDisplayLabel(recommendation, t) {
  if (recommendation?.source === "cash_flow") {
    return t("simulator.recommendationCashFlowTitle");
  }

  if (recommendation?.source === "recurring") {
    const merchantName = String(recommendation?.label || "").replace(/^Cancel\s+/i, "").trim();
    return t("simulator.recommendationRecurringTitle", {
      name: merchantName || t("simulator.recurringCost"),
    });
  }

  if (recommendation?.source === "recurring_bundle") {
    return t("simulator.recommendationBundleTitle");
  }

  if (recommendation?.source === "budget_pressure") {
    return t("simulator.recommendationBudgetTitle");
  }

  return recommendation?.label || t("simulator.recommendedPlanName");
}

function getRecommendationDescription(recommendation, t) {
  const monthlyChange = Math.abs(Number(recommendation?.expense_adjustment || 0)).toFixed(2);

  if (recommendation?.source === "cash_flow") {
    return t("simulator.recommendationCashFlowDetail", { amount: monthlyChange });
  }

  if (recommendation?.source === "recurring") {
    return t("simulator.recommendationRecurringDetail", { amount: monthlyChange });
  }

  if (recommendation?.source === "recurring_bundle") {
    return t("simulator.recommendationBundleDetail", { amount: monthlyChange });
  }

  if (recommendation?.source === "budget_pressure") {
    return t("simulator.recommendationBudgetDetail", { amount: monthlyChange });
  }

  return recommendation?.description || t("simulator.recommendationGenericDetail");
}

function getRecommendationReason(recommendation, t) {
  if (recommendation?.source === "cash_flow") {
    return t("simulator.recommendationCashFlowReason");
  }

  if (recommendation?.source === "recurring") {
    return t("simulator.recommendationRecurringReason");
  }

  if (recommendation?.source === "recurring_bundle") {
    return t("simulator.recommendationBundleReason");
  }

  if (recommendation?.source === "budget_pressure") {
    return t("simulator.recommendationBudgetReason");
  }

  return t("simulator.recommendationGenericReason");
}

function filterRecommendations(recommendations, filterMode) {
  if (filterMode === "saved") {
    return recommendations.filter((recommendation) => recommendation.is_saved);
  }
  if (filterMode === "recurring") {
    return recommendations.filter((recommendation) =>
      ["recurring", "recurring_bundle"].includes(String(recommendation.source || ""))
    );
  }
  if (filterMode === "cash_flow" || filterMode === "budget_pressure") {
    return recommendations.filter((recommendation) => recommendation.source === filterMode);
  }
  return recommendations;
}

function buildSavedScenarioSummary(scenario, t) {
  const summaryParts = [
    t("simulator.monthCount", {
      count: scenario.months,
      plural: scenario.months === 1 ? "" : "s",
    }),
  ];

  if (Number(scenario.income_adjustment) !== 0) {
    summaryParts.push(
      t("simulator.summaryIncome", {
        amount: formatSignedScenarioAmount(scenario.income_adjustment),
      })
    );
  }
  if (Number(scenario.expense_adjustment) !== 0) {
    summaryParts.push(
      t("simulator.summaryExpenses", {
        amount: formatSignedScenarioAmount(scenario.expense_adjustment),
      })
    );
  }
  if (scenario.target_balance != null) {
    summaryParts.push(
      t("simulator.summaryTarget", {
        amount: Number(scenario.target_balance).toFixed(2),
      })
    );
  }

  return summaryParts.join(" | ");
}

function buildSimulationRequestParams({
  accountId,
  months,
  incomeAdjustment,
  expenseAdjustment,
  targetBalance,
  eventAmount,
  eventMonthOffset,
  eventLabel,
}) {
  const normalizedEventAmount = Number(eventAmount) || 0;

  return {
    account_id: accountId,
    months: Math.max(1, Math.min(Number(months) || 6, 12)),
    income_adjustment: Number(incomeAdjustment) || 0,
    expense_adjustment: Number(expenseAdjustment) || 0,
    target_balance: Number(targetBalance) > 0 ? Number(targetBalance) : undefined,
    event_amount: normalizedEventAmount,
    event_month_offset:
      normalizedEventAmount !== 0 && Number(eventMonthOffset) > 0
        ? Number(eventMonthOffset)
        : undefined,
    event_label:
      normalizedEventAmount !== 0 ? String(eventLabel || "").trim() || undefined : undefined,
  };
}

function buildSavedScenarioPayloadFromRecommendation(recommendation, accountId, t) {
  return {
    name: getRecommendationDisplayLabel(recommendation, t),
    months: Math.max(1, Math.min(Number(recommendation.months) || 6, 12)),
    income_adjustment: Number(recommendation.income_adjustment) || 0,
    expense_adjustment: Number(recommendation.expense_adjustment) || 0,
    target_balance:
      Number(recommendation.target_balance) > 0 ? Number(recommendation.target_balance) : null,
    event_month_offset:
      Number(recommendation.event_amount) !== 0 && Number(recommendation.event_month_offset) > 0
        ? Number(recommendation.event_month_offset)
        : null,
    event_amount:
      Number(recommendation.event_amount) !== 0 ? Number(recommendation.event_amount) : null,
    event_label:
      Number(recommendation.event_amount) !== 0
        ? String(recommendation.event_label || "").trim() || null
        : null,
    account_id: accountId,
  };
}

function getScenarioRiskLabel(riskLevel, t) {
  if (riskLevel === "high") {
    return t("simulator.highRisk");
  }
  if (riskLevel === "watch") {
    return t("simulator.watchClosely");
  }
  return t("simulator.healthyPace");
}

function getScenarioRiskRank(riskLevel) {
  if (riskLevel === "healthy") {
    return 2;
  }
  if (riskLevel === "watch") {
    return 1;
  }
  return 0;
}

function sortSavedScenarios(scenarios, sortMode) {
  const items = [...scenarios];

  items.sort((left, right) => {
    if (sortMode === "strongest") {
      return (
        (Number(right.projected_end_balance) || 0) - (Number(left.projected_end_balance) || 0) ||
        (Number(right.monthly_net_change) || 0) - (Number(left.monthly_net_change) || 0) ||
        new Date(right.created_at) - new Date(left.created_at)
      );
    }

    if (sortMode === "safest") {
      return (
        getScenarioRiskRank(right.risk_level) - getScenarioRiskRank(left.risk_level) ||
        (Number(right.lowest_balance) || 0) - (Number(left.lowest_balance) || 0) ||
        (Number(right.projected_end_balance) || 0) - (Number(left.projected_end_balance) || 0) ||
        new Date(right.created_at) - new Date(left.created_at)
      );
    }

    if (sortMode === "goal") {
      const leftHasGoal = left.target_balance != null ? 1 : 0;
      const rightHasGoal = right.target_balance != null ? 1 : 0;
      const leftGap =
        left.goal_gap_amount != null ? Number(left.goal_gap_amount) : Number.POSITIVE_INFINITY;
      const rightGap =
        right.goal_gap_amount != null ? Number(right.goal_gap_amount) : Number.POSITIVE_INFINITY;
      const leftGoalScore =
        leftHasGoal === 0
          ? Number.NEGATIVE_INFINITY
          : leftGap <= 0
          ? Number.POSITIVE_INFINITY
          : -leftGap;
      const rightGoalScore =
        rightHasGoal === 0
          ? Number.NEGATIVE_INFINITY
          : rightGap <= 0
          ? Number.POSITIVE_INFINITY
          : -rightGap;

      return (
        rightHasGoal - leftHasGoal ||
        rightGoalScore - leftGoalScore ||
        (Number(right.projected_end_balance) || 0) - (Number(left.projected_end_balance) || 0) ||
        new Date(right.created_at) - new Date(left.created_at)
      );
    }

    return new Date(right.created_at) - new Date(left.created_at) || right.id - left.id;
  });

  return items;
}

function filterSavedScenarios(scenarios, filterMode) {
  if (filterMode === "healthy") {
    return scenarios.filter((scenario) => scenario.risk_level === "healthy");
  }
  if (filterMode === "attention") {
    return scenarios.filter((scenario) =>
      ["watch", "high"].includes(String(scenario.risk_level || ""))
    );
  }
  if (filterMode === "goal") {
    return scenarios.filter((scenario) => scenario.target_balance != null);
  }
  if (filterMode === "event") {
    return scenarios.filter((scenario) => scenario.event_amount != null);
  }
  return scenarios;
}

function buildScenarioComparisonNote(currentData, comparedData, comparedName, t) {
  if (!currentData || !comparedData || !comparedName) {
    return "";
  }

  const difference =
    Number(currentData.projected_end_balance || 0) -
    Number(comparedData.projected_end_balance || 0);

  if (Math.abs(difference) < 0.01) {
    return t("simulator.comparisonSame", { name: comparedName });
  }

  if (difference > 0) {
    return t("simulator.comparisonCurrentAhead", {
      name: comparedName,
      amount: formatScenarioCurrency(difference),
    });
  }

  return t("simulator.comparisonComparedAhead", {
    name: comparedName,
    amount: formatScenarioCurrency(Math.abs(difference)),
  });
}

function buildSimulatorNarrative(simulationData, t) {
  if (!simulationData) return "";

  const months = Number(simulationData.months || 0);
  const startingBalance = Number(simulationData.starting_balance || 0);
  const projectedEndBalance = Number(simulationData.projected_end_balance || 0);
  const projectedChange = projectedEndBalance - startingBalance;
  const baseParams = {
    amount: formatScenarioCurrency(Math.abs(projectedChange)),
    months,
    balance: formatScenarioCurrency(projectedEndBalance),
  };

  let narrative =
    projectedChange < -0.01
      ? t("simulator.narrativeFall", baseParams)
      : projectedChange > 0.01
      ? t("simulator.narrativeGrow", baseParams)
      : t("simulator.narrativeFlat", baseParams);

  if (simulationData.one_time_event_amount != null) {
    narrative += ` ${t("simulator.narrativeEvent", {
      amount: formatScenarioCurrency(Math.abs(Number(simulationData.one_time_event_amount || 0))),
      month: simulationData.one_time_event_month || t("simulator.plannedEvent"),
      label: simulationData.one_time_event_label || t("simulator.oneTimeEvent"),
    })}`;
  }

  return narrative;
}

function buildSimulatorAssumptions(simulationData, t) {
  if (!simulationData) return [];

  const assumptions = [
    t("simulator.assumptionBaseline", {
      income: Number(simulationData.baseline_monthly_income || 0).toFixed(2),
      expenses: Number(simulationData.baseline_monthly_expenses || 0).toFixed(2),
    }),
    t("simulator.assumptionAdjustments", {
      income: Number(simulationData.adjusted_monthly_income || 0).toFixed(2),
      expenses: Number(simulationData.adjusted_monthly_expenses || 0).toFixed(2),
    }),
  ];

  if (simulationData.one_time_event_amount != null) {
    assumptions.push(
      t("simulator.assumptionEvent", {
        label: simulationData.one_time_event_label || t("simulator.oneTimeEvent"),
        month: simulationData.one_time_event_month || t("simulator.plannedEvent"),
        amount: formatSignedScenarioAmount(simulationData.one_time_event_amount),
      })
    );
  }

  if (simulationData.goal_balance != null) {
    assumptions.push(
      t("simulator.assumptionGoal", {
        amount: Number(simulationData.goal_balance || 0).toFixed(2),
      })
    );
  }

  return assumptions;
}

function buildGoalNote(simulationData, t) {
  if (!simulationData || simulationData.goal_balance == null) return "";

  const gapAmount = Number(simulationData.goal_gap_amount || 0);
  if (gapAmount <= 0) {
    return t("simulator.goalOnTrackNote", {
      amount: Number(simulationData.goal_balance || 0).toFixed(2),
    });
  }

  return t("simulator.goalGapNote", {
    amount: gapAmount.toFixed(2),
    monthly: Number(simulationData.required_income_lift || 0).toFixed(2),
  });
}

function formatReductionReason(item, t) {
  if (Number(item?.share_percent || 0) >= 35) {
    return t("simulator.reductionLargeShareReason");
  }

  return t("simulator.reductionReviewReason");
}

function buildScenarioComparisonTimeline(currentData, comparedData) {
  const currentTimeline = currentData?.timeline || [];
  const comparedTimeline = comparedData?.timeline || [];

  const allMonths = Array.from(
    new Set([
      ...currentTimeline.map((item) => item.month),
      ...comparedTimeline.map((item) => item.month),
    ])
  ).sort();

  const currentMap = new Map(currentTimeline.map((item) => [item.month, item]));
  const comparedMap = new Map(comparedTimeline.map((item) => [item.month, item]));

  return allMonths.map((month) => {
    const currentItem = currentMap.get(month);
    const comparedItem = comparedMap.get(month);
    const currentEndingBalance =
      currentItem?.ending_balance != null ? Number(currentItem.ending_balance) : null;
    const comparedEndingBalance =
      comparedItem?.ending_balance != null ? Number(comparedItem.ending_balance) : null;

    return {
      month,
      current_ending_balance: currentEndingBalance,
      compared_ending_balance: comparedEndingBalance,
      current_net_change: currentItem?.net_change != null ? Number(currentItem.net_change) : null,
      compared_net_change:
        comparedItem?.net_change != null ? Number(comparedItem.net_change) : null,
      ending_balance_gap:
        currentEndingBalance != null && comparedEndingBalance != null
          ? currentEndingBalance - comparedEndingBalance
          : null,
    };
  });
}

function buildScenarioComparisonHighlights(currentData, comparedData, comparedName, t) {
  if (!currentData || !comparedData || !comparedName) {
    return [];
  }

  const currentLowest = (currentData.timeline || []).reduce(
    (lowest, item) =>
      Number(item.ending_balance) < Number(lowest.ending_balance) ? item : lowest,
    currentData.timeline?.[0] || null
  );
  const comparedLowest = (comparedData.timeline || []).reduce(
    (lowest, item) =>
      Number(item.ending_balance) < Number(lowest.ending_balance) ? item : lowest,
    comparedData.timeline?.[0] || null
  );

  const endDifference =
    Number(currentData.projected_end_balance || 0) -
    Number(comparedData.projected_end_balance || 0);
  const netDifference =
    Number(currentData.monthly_net_change || 0) - Number(comparedData.monthly_net_change || 0);
  const cashFloorDifference =
    currentLowest && comparedLowest
      ? Number(currentLowest.ending_balance || 0) - Number(comparedLowest.ending_balance || 0)
      : null;

  return [
    {
      title: t("simulator.betterFinish"),
      value:
        endDifference >= 0
          ? t("simulator.currentDraftBy", { amount: formatScenarioCurrency(endDifference) })
          : t("simulator.comparedBy", {
              name: comparedName,
              amount: formatScenarioCurrency(Math.abs(endDifference)),
            }),
      detail: t("simulator.betterFinishDetail"),
    },
    {
      title: t("simulator.monthlyPaceEdge"),
      value:
        netDifference >= 0
          ? t("simulator.monthlyPaceCurrent", { amount: formatSignedScenarioAmount(netDifference) })
          : t("simulator.monthlyPaceCompared", {
              name: comparedName,
              amount: formatSignedScenarioAmount(Math.abs(netDifference)),
            }),
      detail: t("simulator.monthlyPaceDetail"),
    },
    {
      title: t("simulator.saferCashFloor"),
      value:
        cashFloorDifference == null
          ? t("simulator.notEnoughData")
          : cashFloorDifference >= 0
          ? t("simulator.currentDraftBy", { amount: formatScenarioCurrency(cashFloorDifference) })
          : t("simulator.comparedBy", {
              name: comparedName,
              amount: formatScenarioCurrency(Math.abs(cashFloorDifference)),
            }),
      detail:
        currentLowest && comparedLowest
          ? t("simulator.lowestBalanceMonths", {
              currentMonth: currentLowest.month,
              comparedMonth: comparedLowest.month,
            })
          : t("simulator.cashFloorDetail"),
    },
  ];
}

function buildScenarioCheckpoints(simulationData, t) {
  const timeline = simulationData?.timeline || [];
  if (timeline.length === 0) {
    return [];
  }

  const lowestPoint = timeline.reduce((lowest, item) =>
    Number(item.ending_balance) < Number(lowest.ending_balance) ? item : lowest
  );
  const firstNegativePoint = timeline.find((item) => Number(item.ending_balance) < 0);
  const goalPoint =
    simulationData?.goal_balance != null
      ? timeline.find((item) => Number(item.ending_balance) >= Number(simulationData.goal_balance))
      : null;

  const checkpoints = [
    {
      title: t("simulator.lowestBalancePoint"),
      value: `${lowestPoint.month} | ${formatScenarioCurrency(lowestPoint.ending_balance)}`,
      detail: t("simulator.lowestBalanceDetail"),
    },
  ];

  if (goalPoint && simulationData?.goal_balance != null) {
    checkpoints.push({
      title: t("simulator.goalReached"),
      value: `${goalPoint.month} | ${formatScenarioCurrency(simulationData.goal_balance)}`,
      detail: t("simulator.goalReachedDetail", { month: goalPoint.month }),
    });
  } else if (simulationData?.goal_balance != null) {
    checkpoints.push({
      title: t("simulator.goalStatus"),
      value: t("simulator.notReached"),
      detail: buildGoalNote(simulationData, t) || t("simulator.targetNotReached"),
    });
  }

  if (firstNegativePoint) {
    checkpoints.push({
      title: t("simulator.firstNegativeMonth"),
      value: `${firstNegativePoint.month} | ${formatScenarioCurrency(firstNegativePoint.ending_balance)}`,
      detail: t("simulator.firstNegativeDetail"),
    });
  } else {
    checkpoints.push({
      title: t("simulator.cashFloor"),
      value: formatScenarioCurrency(lowestPoint.ending_balance),
      detail: t("simulator.cashFloorHealthy", {
        count: simulationData?.months || timeline.length,
      }),
    });
  }

  if (simulationData?.one_time_event_amount != null) {
    checkpoints.push({
      title: t("simulator.plannedEventMonth"),
      value: `${simulationData.one_time_event_month} | ${formatSignedScenarioAmount(
        simulationData.one_time_event_amount
      )}`,
      detail: simulationData.one_time_event_label || t("simulator.oneTimeEvent"),
    });
  }

  return checkpoints;
}

function SimulatorPage() {
  const navigate = useNavigate();
  const { t } = useLanguage();
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
  const [strategyRecommendations, setStrategyRecommendations] = useState([]);
  const [recommendationFilter, setRecommendationFilter] = useState("all");
  const [recommendationsLoading, setRecommendationsLoading] = useState(true);
  const [recommendationsError, setRecommendationsError] = useState("");
  const [recommendationMessage, setRecommendationMessage] = useState("");
  const [previewedRecommendation, setPreviewedRecommendation] = useState(null);
  const [recommendationPreviewData, setRecommendationPreviewData] = useState(null);
  const [recommendationPreviewLoading, setRecommendationPreviewLoading] = useState(false);
  const [recommendationPreviewError, setRecommendationPreviewError] = useState("");
  const [recurringExpenses, setRecurringExpenses] = useState([]);
  const [recurringLoading, setRecurringLoading] = useState(true);
  const [recurringError, setRecurringError] = useState("");
  const [recurringLeverMessage, setRecurringLeverMessage] = useState("");
  const [applyingReductionPlan, setApplyingReductionPlan] = useState(false);
  const [reductionPlanMessage, setReductionPlanMessage] = useState("");
  const [reductionPlanError, setReductionPlanError] = useState("");
  const [scenarioLinkMessage, setScenarioLinkMessage] = useState("");
  const [scenarioLinkError, setScenarioLinkError] = useState("");
  const [activeSavedScenarioId, setActiveSavedScenarioId] = useState(null);
  const [linkedSavedScenarioId, setLinkedSavedScenarioId] = useState(
    Number(searchParams.get("saved_scenario_id")) > 0
      ? Number(searchParams.get("saved_scenario_id"))
      : null
  );
  const [linkedComparisonScenarioId, setLinkedComparisonScenarioId] = useState(
    Number(searchParams.get("compare_saved_scenario_id")) > 0
      ? Number(searchParams.get("compare_saved_scenario_id"))
      : null
  );
  const [savedScenarioName, setSavedScenarioName] = useState(
    searchParams.get("scenario_name") || ""
  );
  const [savedScenarioQuery, setSavedScenarioQuery] = useState("");
  const [savedScenarioFilter, setSavedScenarioFilter] = useState("all");
  const [savedScenarioSort, setSavedScenarioSort] = useState("newest");
  const [savedScenarios, setSavedScenarios] = useState([]);
  const [savedScenariosLoading, setSavedScenariosLoading] = useState(true);
  const [savingScenario, setSavingScenario] = useState(false);
  const [savingScenarioMode, setSavingScenarioMode] = useState(null);
  const [savingRecommendationKey, setSavingRecommendationKey] = useState(null);
  const [deletingScenarioId, setDeletingScenarioId] = useState(null);
  const [savedScenarioMessage, setSavedScenarioMessage] = useState("");
  const [savedScenarioError, setSavedScenarioError] = useState("");
  const [comparisonScenarioId, setComparisonScenarioId] = useState(
    Number(searchParams.get("compare_saved_scenario_id")) > 0
      ? Number(searchParams.get("compare_saved_scenario_id"))
      : null
  );
  const [comparisonData, setComparisonData] = useState(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState("");
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
    const scenarioNameParam = searchParams.get("scenario_name");
    const compareScenarioParam = Number(searchParams.get("compare_saved_scenario_id"));

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
    if (scenarioNameParam !== null && !activeSavedScenarioId) {
      setSavedScenarioName(scenarioNameParam);
    }
    if (compareScenarioParam > 0) {
      setLinkedComparisonScenarioId(compareScenarioParam);
      setComparisonScenarioId(compareScenarioParam);
    } else {
      setLinkedComparisonScenarioId(null);
      setComparisonScenarioId(null);
    }
  }, [activeSavedScenarioId, searchParams]);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set(
      "account_id",
      selectedAccountId === ALL_ACCOUNTS_VALUE ? ALL_ACCOUNTS_VALUE : String(selectedAccountId)
    );
    params.set("months", String(Math.max(1, Math.min(Number(months) || 6, 12))));
    const savedScenarioParamId = activeSavedScenarioId || linkedSavedScenarioId;
    if (savedScenarioParamId) {
      params.set("saved_scenario_id", String(savedScenarioParamId));
    }
    if (comparisonScenarioId) {
      params.set("compare_saved_scenario_id", String(comparisonScenarioId));
    }

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
    activeSavedScenarioId,
    linkedSavedScenarioId,
    comparisonScenarioId,
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

  const fetchSavedScenarios = useCallback(async () => {
    try {
      setSavedScenariosLoading(true);
      setSavedScenarioError("");
      const response = await api.get("/analytics/saved-scenarios", {
        params: {
          account_id: normalizedAccountId,
        },
      });
      setSavedScenarios(response.data || []);
    } catch (fetchError) {
      if (!handleApiAuthError(fetchError, navigate)) {
        setSavedScenarioError(t("simulator.loadSavedFailed"));
      }
    } finally {
      setSavedScenariosLoading(false);
    }
  }, [navigate, normalizedAccountId, t]);

  useEffect(() => {
    fetchSavedScenarios();
  }, [fetchSavedScenarios]);

  const fetchRecommendations = useCallback(async () => {
    try {
      setRecommendationsLoading(true);
      setRecommendationsError("");
      const response = await api.get("/analytics/future-simulator-recommendations", {
        params: {
          account_id: normalizedAccountId,
          months: Math.max(1, Math.min(Number(months) || 6, 12)),
        },
      });
      setStrategyRecommendations(response.data?.items || []);
    } catch (fetchError) {
      if (!handleApiAuthError(fetchError, navigate)) {
        setStrategyRecommendations([]);
        setRecommendationsError(t("simulator.loadRecommendationsFailed"));
      }
    } finally {
      setRecommendationsLoading(false);
    }
  }, [months, navigate, normalizedAccountId, t]);

  useEffect(() => {
    fetchRecommendations();
  }, [fetchRecommendations]);

  useEffect(() => {
    const fetchRecurringExpenses = async () => {
      try {
        setRecurringLoading(true);
        setRecurringError("");
        const response = await api.get("/analytics/recurring-expenses", {
          params: {
            account_id: normalizedAccountId,
          },
        });
        setRecurringExpenses(response.data?.items || []);
      } catch (fetchError) {
        if (!handleApiAuthError(fetchError, navigate)) {
          setRecurringExpenses([]);
          setRecurringError(t("simulator.loadRecurringFailed"));
        }
      } finally {
        setRecurringLoading(false);
      }
    };

    fetchRecurringExpenses();
  }, [navigate, normalizedAccountId, t]);

  useEffect(() => {
    const fetchSimulation = async () => {
      try {
        setLoading(true);
        setError("");
        setReductionPlanMessage("");
        setReductionPlanError("");
        const response = await api.get("/analytics/future-simulator", {
          params: buildSimulationRequestParams({
            accountId: normalizedAccountId,
            months,
            incomeAdjustment,
            expenseAdjustment,
            targetBalance,
            eventAmount,
            eventMonthOffset,
            eventLabel,
          }),
        });
        setSimulatorData(response.data);
      } catch (fetchError) {
        if (!handleApiAuthError(fetchError, navigate)) {
          setError(t("simulator.loadSimulatorFailed"));
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
    t,
  ]);

  const comparedScenario = useMemo(
    () => savedScenarios.find((scenario) => scenario.id === comparisonScenarioId) || null,
    [savedScenarios, comparisonScenarioId]
  );
  const savedScenarioPortfolioSummary = useMemo(() => {
    const strongestScenario = sortSavedScenarios(savedScenarios, "strongest")[0] || null;
    const safestScenario = sortSavedScenarios(savedScenarios, "safest")[0] || null;
    const goalLeader =
      sortSavedScenarios(
        savedScenarios.filter((scenario) => scenario.target_balance != null),
        "goal"
      )[0] || null;

    return {
      total: savedScenarios.length,
      healthyCount: savedScenarios.filter((scenario) => scenario.risk_level === "healthy").length,
      attentionCount: savedScenarios.filter((scenario) =>
        ["watch", "high"].includes(String(scenario.risk_level || ""))
      ).length,
      goalCount: savedScenarios.filter((scenario) => scenario.target_balance != null).length,
      eventCount: savedScenarios.filter((scenario) => scenario.event_amount != null).length,
      strongestScenario,
      safestScenario,
      goalLeader,
    };
  }, [savedScenarios]);
  const filterCountByMode = useMemo(
    () =>
      Object.fromEntries(
        SAVED_SCENARIO_FILTER_OPTIONS.map((option) => [
          option.value,
          filterSavedScenarios(savedScenarios, option.value).length,
        ])
      ),
    [savedScenarios]
  );
  const quickFilteredSavedScenarios = useMemo(
    () => filterSavedScenarios(savedScenarios, savedScenarioFilter),
    [savedScenarios, savedScenarioFilter]
  );
  const filteredSavedScenarios = useMemo(() => {
    const normalizedQuery = savedScenarioQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return quickFilteredSavedScenarios;
    }

    return quickFilteredSavedScenarios.filter((scenario) => {
      const searchableText = [
        scenario.name,
        scenario.event_label,
        buildSavedScenarioSummary(scenario, t),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return searchableText.includes(normalizedQuery);
    });
  }, [quickFilteredSavedScenarios, savedScenarioQuery, t]);
  const displayedSavedScenarios = useMemo(
    () => sortSavedScenarios(filteredSavedScenarios, savedScenarioSort),
    [filteredSavedScenarios, savedScenarioSort]
  );
  const hasSavedScenarioControlOverrides =
    savedScenarioFilter !== "all" ||
    savedScenarioSort !== "newest" ||
    savedScenarioQuery.trim().length > 0;
  const savedScenarioHighlights = useMemo(() => {
    const highlights = [];
    const seenScenarioIds = new Set();

    const strongestScenario = sortSavedScenarios(displayedSavedScenarios, "strongest")[0];
    if (strongestScenario) {
      highlights.push({
        key: "strongest",
        title: t("simulator.strongestFinish"),
        description: t("simulator.strongestFinishDetail"),
        scenario: strongestScenario,
        value: formatScenarioCurrency(strongestScenario.projected_end_balance),
      });
      seenScenarioIds.add(strongestScenario.id);
    }

    const safestScenario = sortSavedScenarios(displayedSavedScenarios, "safest").find(
      (scenario) => !seenScenarioIds.has(scenario.id)
    );
    if (safestScenario) {
      highlights.push({
        key: "safest",
        title: t("simulator.safestCushion"),
        description: t("simulator.safestCushionDetail"),
        scenario: safestScenario,
        value: getScenarioRiskLabel(safestScenario.risk_level, t),
      });
      seenScenarioIds.add(safestScenario.id);
    }

    const goalScenario = sortSavedScenarios(
      displayedSavedScenarios.filter((scenario) => scenario.target_balance != null),
      "goal"
    ).find((scenario) => !seenScenarioIds.has(scenario.id));
    if (goalScenario) {
      highlights.push({
        key: "goal",
        title: t("simulator.goalLeader"),
        description:
          Number(goalScenario.goal_gap_amount) <= 0
            ? t("simulator.goalLeaderOnTrack")
            : t("simulator.goalLeaderClosest"),
        scenario: goalScenario,
        value:
          Number(goalScenario.goal_gap_amount) <= 0
            ? t("simulator.onTrack")
            : formatScenarioCurrency(goalScenario.goal_gap_amount),
      });
    }

    return highlights;
  }, [displayedSavedScenarios, t]);
  const recommendationCountsByFilter = useMemo(
    () =>
      Object.fromEntries(
        RECOMMENDATION_FILTER_OPTIONS.map((option) => [
          option.value,
          filterRecommendations(strategyRecommendations, option.value).length,
        ])
      ),
    [strategyRecommendations]
  );
  const displayedRecommendations = useMemo(
    () => filterRecommendations(strategyRecommendations, recommendationFilter),
    [strategyRecommendations, recommendationFilter]
  );
  const recommendationSummary = useMemo(() => {
    const strongestRecommendation = [...strategyRecommendations].sort(
      (left, right) =>
        (Number(right.scenario_impact_amount) || 0) - (Number(left.scenario_impact_amount) || 0) ||
        (Number(right.projected_end_balance) || 0) - (Number(left.projected_end_balance) || 0)
    )[0] || null;
    const savedCount = strategyRecommendations.filter((recommendation) => recommendation.is_saved).length;
    const healthyCount = strategyRecommendations.filter(
      (recommendation) => recommendation.risk_level === "healthy"
    ).length;

    return {
      total: strategyRecommendations.length,
      savedCount,
      healthyCount,
      strongestRecommendation,
    };
  }, [strategyRecommendations]);
  const recurringLeverCandidates = useMemo(() => {
    const priorityRank = { high: 2, medium: 1, low: 0 };

    return [...recurringExpenses]
      .sort(
        (left, right) =>
          (priorityRank[String(right.review_priority || "low")] || 0) -
            (priorityRank[String(left.review_priority || "low")] || 0) ||
          (Number(right.annualized_amount) || 0) - (Number(left.annualized_amount) || 0) ||
          (Number(right.average_amount) || 0) - (Number(left.average_amount) || 0)
      )
      .slice(0, 3);
  }, [recurringExpenses]);
  const combinedRecurringLever = useMemo(() => {
    const prioritizedItems = recurringLeverCandidates.filter((item) =>
      ["high", "medium"].includes(String(item.review_priority || ""))
    );
    const selectedItems = prioritizedItems.length > 0 ? prioritizedItems : recurringLeverCandidates;
    const totalMonthlyCut = selectedItems.reduce(
      (sum, item) => sum + (Number(item.average_amount) || 0),
      0
    );

    return {
      items: selectedItems,
      totalMonthlyCut,
      totalAnnualizedCut: totalMonthlyCut * 12,
    };
  }, [recurringLeverCandidates]);

  const handleResetSavedScenarioControls = () => {
    setSavedScenarioFilter("all");
    setSavedScenarioSort("newest");
    setSavedScenarioQuery("");
  };

  const handleOpenSavedScenario = (scenario) => {
    if (!scenario) {
      return;
    }
    handleLoadSavedScenario(scenario);
    handleClearScenarioComparison();
  };

  const handleCompareSavedScenarioPair = (primaryScenario, secondaryScenario) => {
    if (!primaryScenario || !secondaryScenario || primaryScenario.id === secondaryScenario.id) {
      return;
    }
    handleLoadSavedScenario(primaryScenario);
    setLinkedComparisonScenarioId(secondaryScenario.id);
    setComparisonScenarioId(secondaryScenario.id);
    setComparisonError("");
  };

  useEffect(() => {
    if (
      activeSavedScenarioId &&
      !savedScenarios.some((scenario) => scenario.id === activeSavedScenarioId)
    ) {
      setActiveSavedScenarioId(null);
      setLinkedSavedScenarioId(null);
    }
  }, [savedScenarios, activeSavedScenarioId]);

  useEffect(() => {
    if (!comparedScenario) {
      setComparisonData(null);
      setComparisonError("");
      setComparisonLoading(false);
      return;
    }

    const fetchComparison = async () => {
      try {
        setComparisonLoading(true);
        setComparisonError("");
        const response = await api.get("/analytics/future-simulator", {
          params: buildSimulationRequestParams({
            accountId:
              comparedScenario.account_id == null ? undefined : Number(comparedScenario.account_id),
            months: comparedScenario.months,
            incomeAdjustment: comparedScenario.income_adjustment,
            expenseAdjustment: comparedScenario.expense_adjustment,
            targetBalance: comparedScenario.target_balance,
            eventAmount: comparedScenario.event_amount,
            eventMonthOffset: comparedScenario.event_month_offset,
            eventLabel: comparedScenario.event_label,
          }),
        });
        setComparisonData(response.data);
      } catch (fetchError) {
        if (!handleApiAuthError(fetchError, navigate)) {
          setComparisonError(t("simulator.compareFailed", { name: comparedScenario.name }));
        }
      } finally {
        setComparisonLoading(false);
      }
    };

    fetchComparison();
  }, [comparedScenario, navigate, t]);

  const chartTheme = useMemo(() => {
    const isDark = themeMode === "dark";
    return {
      text: isDark ? "#cbd5e1" : "#475569",
      grid: isDark ? "rgba(148, 163, 184, 0.12)" : "rgba(15, 23, 42, 0.08)",
      tooltipBg: isDark ? "rgba(15, 23, 42, 0.96)" : "rgba(255, 255, 255, 0.96)",
      tooltipBorder: isDark ? "rgba(148, 163, 184, 0.16)" : "rgba(15, 23, 42, 0.08)",
      balanceLine: isDark ? "#60a5fa" : "#2563eb",
      compareLine: isDark ? "#fbbf24" : "#d97706",
      baselineLine: isDark ? "#a78bfa" : "#7c3aed",
      netLine: isDark ? "#4ade80" : "#16a34a",
    };
  }, [themeMode]);

  const scopeDescription =
    normalizedAccountId == null
      ? t("simulator.scopeAll")
      : t("simulator.scopeOne");

  const riskMeta = useMemo(() => {
    const riskLevel = simulatorData?.risk_level;
    if (riskLevel === "high") {
      return { label: t("simulator.highRisk"), className: "simulator-risk-pill simulator-risk-high" };
    }
    if (riskLevel === "watch") {
      return { label: t("simulator.watchClosely"), className: "simulator-risk-pill simulator-risk-watch" };
    }
    return { label: t("simulator.healthyPace"), className: "simulator-risk-pill simulator-risk-healthy" };
  }, [simulatorData, t]);

  const comparisonNote = useMemo(
    () => buildScenarioComparisonNote(simulatorData, comparisonData, comparedScenario?.name, t),
    [simulatorData, comparisonData, comparedScenario, t]
  );
  const comparisonTimeline = useMemo(
    () => buildScenarioComparisonTimeline(simulatorData, comparisonData),
    [simulatorData, comparisonData]
  );
  const comparisonHighlights = useMemo(
    () => buildScenarioComparisonHighlights(simulatorData, comparisonData, comparedScenario?.name, t),
    [simulatorData, comparisonData, comparedScenario, t]
  );
  const recommendationPreviewNote = useMemo(
    () =>
      buildScenarioComparisonNote(
        simulatorData,
        recommendationPreviewData,
        previewedRecommendation ? getRecommendationDisplayLabel(previewedRecommendation, t) : "",
        t
      ),
    [simulatorData, recommendationPreviewData, previewedRecommendation, t]
  );
  const recommendationPreviewTimeline = useMemo(
    () => buildScenarioComparisonTimeline(simulatorData, recommendationPreviewData),
    [simulatorData, recommendationPreviewData]
  );
  const recommendationPreviewHighlights = useMemo(
    () =>
      buildScenarioComparisonHighlights(
        simulatorData,
        recommendationPreviewData,
        previewedRecommendation ? getRecommendationDisplayLabel(previewedRecommendation, t) : "",
        t
      ),
    [simulatorData, recommendationPreviewData, previewedRecommendation, t]
  );

  const scenarioCheckpoints = useMemo(
    () => buildScenarioCheckpoints(simulatorData, t),
    [simulatorData, t]
  );

  const comparisonBalanceDelta =
    simulatorData && comparisonData
      ? Number(simulatorData.projected_end_balance || 0) -
        Number(comparisonData.projected_end_balance || 0)
      : null;

  const comparisonMonthlyNetDelta =
    simulatorData && comparisonData
      ? Number(simulatorData.monthly_net_change || 0) -
        Number(comparisonData.monthly_net_change || 0)
      : null;
  const recommendationPreviewBalanceDelta =
    simulatorData && recommendationPreviewData
      ? Number(recommendationPreviewData.projected_end_balance || 0) -
        Number(simulatorData.projected_end_balance || 0)
      : null;
  const recommendationPreviewMonthlyNetDelta =
    simulatorData && recommendationPreviewData
      ? Number(recommendationPreviewData.monthly_net_change || 0) -
        Number(simulatorData.monthly_net_change || 0)
      : null;

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
    setActiveSavedScenarioId(null);
    setLinkedSavedScenarioId(null);
    setSavedScenarioName("");
    setRecurringLeverMessage("");
    setRecommendationMessage("");
    setMonths(preset.months);
    setIncomeAdjustment(preset.incomeAdjustment);
    setExpenseAdjustment(preset.expenseAdjustment);
    setTargetBalance(
      preset.targetBalance === "" ? "" : String(preset.targetBalance)
    );
    setEventAmount(preset.eventAmount === "" ? "" : String(preset.eventAmount));
    setEventMonthOffset(preset.eventMonthOffset || 1);
    setEventLabel(preset.eventLabelKey ? t(preset.eventLabelKey) : preset.eventLabel || "");
  };

  const applyRecommendation = (recommendation) => {
    if (!recommendation) {
      return;
    }

    setActiveSavedScenarioId(null);
    setLinkedSavedScenarioId(null);
    setSavedScenarioName(getRecommendationDisplayLabel(recommendation, t));
    setRecurringLeverMessage("");
    setMonths(recommendation.months || 6);
    setIncomeAdjustment(String(recommendation.income_adjustment || 0));
    setExpenseAdjustment(String(recommendation.expense_adjustment || 0));
    setTargetBalance(
      recommendation.target_balance != null ? String(recommendation.target_balance) : ""
    );
    setEventAmount(
      recommendation.event_amount != null ? String(recommendation.event_amount) : ""
    );
    setEventMonthOffset(recommendation.event_month_offset || 1);
    setEventLabel(recommendation.event_label || "");
    setRecommendationMessage(
      t("simulator.appliedRecommendation", {
        label: getRecommendationDisplayLabel(recommendation, t),
      })
    );
  };

  const handleSaveRecommendation = async (recommendation) => {
    if (!recommendation) {
      return;
    }

    if (recommendation.saved_scenario_id) {
      const matchedScenario = savedScenarios.find(
        (scenario) => scenario.id === recommendation.saved_scenario_id
      );
      if (matchedScenario) {
        handleLoadSavedScenario(matchedScenario);
        return;
      }
    }

    try {
      setSavingRecommendationKey(recommendation.key);
      setSavedScenarioError("");
      setSavedScenarioMessage("");
      const payload = buildSavedScenarioPayloadFromRecommendation(
        recommendation,
        normalizedAccountId,
        t
      );
      const response = await api.post("/analytics/saved-scenarios", payload);
      setActiveSavedScenarioId(response.data.id);
      setLinkedSavedScenarioId(response.data.id);
      setSavedScenarioName(response.data.name);
      setSelectedAccountId(
        response.data.account_id == null ? ALL_ACCOUNTS_VALUE : String(response.data.account_id)
      );
      setMonths(response.data.months || payload.months);
      setIncomeAdjustment(String(response.data.income_adjustment || 0));
      setExpenseAdjustment(String(response.data.expense_adjustment || 0));
      setTargetBalance(
        response.data.target_balance != null ? String(response.data.target_balance) : ""
      );
      setEventAmount(response.data.event_amount != null ? String(response.data.event_amount) : "");
      setEventMonthOffset(response.data.event_month_offset || 1);
      setEventLabel(response.data.event_label || "");
      setSavedScenarioMessage(t("simulator.savedRecommendedPlan", { name: response.data.name }));
      await fetchSavedScenarios();
      await fetchRecommendations();
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setSavedScenarioError(
          getApiErrorMessage(saveError, t("simulator.saveRecommendedFailed"))
        );
      }
    } finally {
      setSavingRecommendationKey(null);
    }
  };

  const handlePreviewRecommendation = async (recommendation) => {
    if (!recommendation) {
      return;
    }

    try {
      setPreviewedRecommendation(recommendation);
      setRecommendationPreviewLoading(true);
      setRecommendationPreviewError("");
      const response = await api.get("/analytics/future-simulator", {
        params: buildSimulationRequestParams({
          accountId: normalizedAccountId,
          months: recommendation.months,
          incomeAdjustment: recommendation.income_adjustment,
          expenseAdjustment: recommendation.expense_adjustment,
          targetBalance: recommendation.target_balance,
          eventAmount: recommendation.event_amount,
          eventMonthOffset: recommendation.event_month_offset,
          eventLabel: recommendation.event_label,
        }),
      });
      setRecommendationPreviewData(response.data);
    } catch (previewError) {
      if (!handleApiAuthError(previewError, navigate)) {
        setRecommendationPreviewData(null);
        setRecommendationPreviewError(
          t("simulator.previewFailed", {
            label: getRecommendationDisplayLabel(recommendation, t),
          })
        );
      }
    } finally {
      setRecommendationPreviewLoading(false);
    }
  };

  const clearRecommendationPreview = () => {
    setPreviewedRecommendation(null);
    setRecommendationPreviewData(null);
    setRecommendationPreviewError("");
    setRecommendationPreviewLoading(false);
  };

  const handleApplyRecurringLever = ({ amount, label }) => {
    const monthlyCut = Math.max(Number(amount) || 0, 0);
    if (monthlyCut <= 0) {
      return;
    }

    setActiveSavedScenarioId(null);
    setLinkedSavedScenarioId(null);
    setSavedScenarioName("");
    setRecommendationMessage("");
    setExpenseAdjustment(String(-monthlyCut));
    setRecurringLeverMessage(
      t("simulator.recurringLeverModeled", {
        label,
        amount: formatSignedScenarioAmount(-monthlyCut),
      })
    );
  };

  const eventMonthOptions = useMemo(() => {
    const optionCount = Math.max(1, Math.min(Number(months) || 1, 12));
    const startMonth = simulatorData?.start_month;
    return Array.from({ length: optionCount }, (_, index) => ({
      value: index + 1,
      label: startMonth ? shiftMonthLabel(startMonth, index) : t("simulator.monthNumber", { count: index + 1 }),
    }));
  }, [months, simulatorData?.start_month, t]);

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
        getApiSuccessMessage(
          response.data,
          t("simulator.reductionApplied", {
            count: targets.length,
            plural: targets.length === 1 ? "" : "s",
            month: simulatorData.start_month,
          })
        )
      );
    } catch (applyError) {
      if (!handleApiAuthError(applyError, navigate)) {
        setReductionPlanError(
          getApiErrorMessage(applyError, t("simulator.reductionFailed"))
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
      setScenarioLinkMessage(t("simulator.scenarioLinkCopied"));
    } catch (copyError) {
      console.error("Failed to copy scenario link:", copyError);
      setScenarioLinkError(t("simulator.scenarioLinkCopyFailed"));
    }
  };

  const handleSaveScenario = async (forceCreate = false) => {
    const fallbackName =
      (simulatorData?.one_time_event_label
        ? t("simulator.oneTimePlanName", { label: simulatorData.one_time_event_label })
        : Number(targetBalance) > 0
        ? t("simulator.targetPlanName", { amount: Number(targetBalance).toFixed(0) })
        : t("simulator.savedSimulatorPlan"));
    const name = savedScenarioName.trim() || fallbackName;
    const isUpdatingExisting = Boolean(activeSavedScenarioId) && !forceCreate;

    try {
      setSavingScenario(true);
      setSavingScenarioMode(forceCreate ? "copy" : isUpdatingExisting ? "update" : "save");
      setSavedScenarioError("");
      setSavedScenarioMessage("");
      const payload = {
        name,
        months: Number(months) || 6,
        income_adjustment: Number(incomeAdjustment) || 0,
        expense_adjustment: Number(expenseAdjustment) || 0,
        target_balance: Number(targetBalance) > 0 ? Number(targetBalance) : null,
        event_month_offset:
          Number(eventAmount) !== 0 && Number(eventMonthOffset) > 0
            ? Number(eventMonthOffset)
            : null,
        event_amount: Number(eventAmount) !== 0 ? Number(eventAmount) : null,
        event_label: eventLabel.trim() || null,
        account_id: normalizedAccountId,
      };
      const response = isUpdatingExisting
        ? await api.put(`/analytics/saved-scenarios/${activeSavedScenarioId}`, payload)
        : await api.post("/analytics/saved-scenarios", payload);
      setActiveSavedScenarioId(response.data.id);
      setLinkedSavedScenarioId(response.data.id);
      setSavedScenarioName(response.data.name);
      setSavedScenarioMessage(
        forceCreate
          ? t("simulator.savedNewScenario", { name: response.data.name })
          : isUpdatingExisting
          ? t("simulator.updatedScenario", { name: response.data.name })
          : t("simulator.savedScenario", { name: response.data.name })
      );
      await fetchSavedScenarios();
    } catch (saveError) {
      if (!handleApiAuthError(saveError, navigate)) {
        setSavedScenarioError(
          getApiErrorMessage(
            saveError,
            isUpdatingExisting ? t("simulator.updateScenarioFailed") : t("simulator.saveScenarioFailed")
          )
        );
      }
    } finally {
      setSavingScenario(false);
      setSavingScenarioMode(null);
    }
  };

  const handleCompareSavedScenario = (scenario) => {
    setLinkedComparisonScenarioId(scenario.id);
    setComparisonScenarioId(scenario.id);
    setComparisonError("");
  };

  const handleClearScenarioComparison = useCallback(() => {
    setLinkedComparisonScenarioId(null);
    setComparisonScenarioId(null);
    setComparisonData(null);
    setComparisonError("");
  }, []);

  const handleLoadSavedScenario = useCallback((scenario) => {
    setActiveSavedScenarioId(scenario.id);
    setLinkedSavedScenarioId(scenario.id);
    setSavedScenarioName(scenario.name || "");
    setSelectedAccountId(
      scenario.account_id == null ? ALL_ACCOUNTS_VALUE : String(scenario.account_id)
    );
    setMonths(scenario.months || 6);
    setIncomeAdjustment(String(scenario.income_adjustment || 0));
    setExpenseAdjustment(String(scenario.expense_adjustment || 0));
    setTargetBalance(
      scenario.target_balance != null ? String(scenario.target_balance) : ""
    );
    setEventAmount(scenario.event_amount != null ? String(scenario.event_amount) : "");
    setEventMonthOffset(scenario.event_month_offset || 1);
    setEventLabel(scenario.event_label || "");
    if (comparisonScenarioId === scenario.id) {
      handleClearScenarioComparison();
    }
    setSavedScenarioMessage(t("simulator.loadedScenario", { name: scenario.name }));
    setSavedScenarioError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [comparisonScenarioId, handleClearScenarioComparison, t]);

  useEffect(() => {
    if (!linkedSavedScenarioId || savedScenariosLoading || activeSavedScenarioId === linkedSavedScenarioId) {
      return;
    }

    const matchedScenario = savedScenarios.find((scenario) => scenario.id === linkedSavedScenarioId);
    if (matchedScenario) {
      handleLoadSavedScenario(matchedScenario);
    }
  }, [
    linkedSavedScenarioId,
    savedScenariosLoading,
    savedScenarios,
    activeSavedScenarioId,
    handleLoadSavedScenario,
  ]);

  useEffect(() => {
    if (!linkedComparisonScenarioId || savedScenariosLoading) {
      return;
    }

    const matchedScenario = savedScenarios.find(
      (scenario) => scenario.id === linkedComparisonScenarioId
    );
    if (matchedScenario) {
      setComparisonScenarioId(matchedScenario.id);
    }
  }, [
    linkedComparisonScenarioId,
    savedScenariosLoading,
    savedScenarios,
  ]);

  const handleDeleteSavedScenario = async (scenarioId) => {
    try {
      setDeletingScenarioId(scenarioId);
      setSavedScenarioError("");
      setSavedScenarioMessage("");
      await api.delete(`/analytics/saved-scenarios/${scenarioId}`);
      if (activeSavedScenarioId === scenarioId) {
        setActiveSavedScenarioId(null);
        setLinkedSavedScenarioId(null);
        setSavedScenarioName("");
      }
      if (comparisonScenarioId === scenarioId) {
        handleClearScenarioComparison();
      }
      setSavedScenarioMessage(t("simulator.savedScenarioDeleted"));
      await fetchSavedScenarios();
    } catch (deleteError) {
      if (!handleApiAuthError(deleteError, navigate)) {
        setSavedScenarioError(
          getApiErrorMessage(deleteError, t("simulator.deleteScenarioFailed"))
        );
      }
    } finally {
      setDeletingScenarioId(null);
    }
  };

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="dashboard-hero">
          <div>
            <p className="eyebrow-text">{t("common.appName")}</p>
            <h1>{t("common.futureSimulator")}</h1>
            <p className="hero-subtitle">
              {t("headers.simulatorSubtitle")}
            </p>
          </div>

          <div className="header-actions">
            <button className="secondary-button" onClick={() => navigate("/dashboard")}>
              {t("common.backToDashboard")}
            </button>
            <button className="secondary-button" onClick={() => navigate("/analytics")}>
              {t("common.analytics")}
            </button>
            <button className="secondary-button" onClick={() => navigate("/money-map")}>
              {t("common.moneyMap")}
            </button>
            <button className="secondary-button" onClick={() => navigate("/budgets")}>
              {t("common.budgets")}
            </button>
            <button className="secondary-button" onClick={() => navigate("/assistant")}>
              {t("common.assistant")}
            </button>
          </div>
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <div>
              <h2>{t("simulator.scenarioControls")}</h2>
              <p>{scopeDescription}</p>
            </div>
            <div className="budget-section-actions">
              <button type="button" className="secondary-button" onClick={handleCopyScenarioLink}>
                {t("simulator.copyScenarioLink")}
              </button>
            </div>
          </div>

          <div className="section-header simulator-recommendations-header">
            <div>
              <h2>{t("simulator.recommendedPlans")}</h2>
              <p>{t("simulator.recommendedPlansDetail")}</p>
            </div>
          </div>

          {recommendationsLoading ? (
            <div className="empty-state">
              <p>{t("simulator.loadingRecommendedPlans")}</p>
            </div>
          ) : recommendationsError ? (
            <div className="empty-state">
              <p>{recommendationsError}</p>
            </div>
          ) : strategyRecommendations.length === 0 ? (
            <div className="empty-state">
              <p>{t("simulator.noRecommendationReady")}</p>
            </div>
          ) : (
            <>
              <div className="simulator-recommendation-summary-grid">
                <div className="simulator-recommendation-summary-card">
                  <span>{t("simulator.ideas")}</span>
                  <strong>{recommendationSummary.total}</strong>
                </div>
                <div className="simulator-recommendation-summary-card">
                  <span>{t("simulator.saved")}</span>
                  <strong>{recommendationSummary.savedCount}</strong>
                </div>
                <div className="simulator-recommendation-summary-card">
                  <span>{t("simulator.healthy")}</span>
                  <strong>{recommendationSummary.healthyCount}</strong>
                </div>
                <div className="simulator-recommendation-summary-card">
                  <span>{t("simulator.bestImpact")}</span>
                  <strong>
                    {recommendationSummary.strongestRecommendation
                      ? formatScenarioCurrency(recommendationSummary.strongestRecommendation.scenario_impact_amount)
                      : "$0.00"}
                  </strong>
                </div>
              </div>

              <div className="simulator-recommendation-filter-row">
                {RECOMMENDATION_FILTER_OPTIONS.map((option) => (
                  <button
                    key={`recommendation-filter-${option.value}`}
                    type="button"
                    className={
                      recommendationFilter === option.value
                        ? "smart-action-button simulator-recommendation-filter-active"
                        : "secondary-button"
                    }
                    onClick={() => setRecommendationFilter(option.value)}
                  >
                    {t(option.labelKey)} ({recommendationCountsByFilter[option.value] || 0})
                  </button>
                ))}
              </div>

              {displayedRecommendations.length === 0 ? (
                <div className="empty-state">
                  <p>{t("simulator.noRecommendedPlansMatch")}</p>
                </div>
              ) : (
                <div className="simulator-recommendation-grid">
                  {displayedRecommendations.map((recommendation) => {
                const savedScenario = recommendation.saved_scenario_id
                  ? savedScenarios.find(
                      (scenario) => scenario.id === recommendation.saved_scenario_id
                    )
                  : null;

                return (
                  <div
                    key={`simulator-recommendation-${recommendation.key}`}
                    className="simulator-recommendation-card"
                  >
                    <div className="simulator-recommendation-top">
                      <div>
                        <h3>{getRecommendationDisplayLabel(recommendation, t)}</h3>
                        <p>{getRecommendationDescription(recommendation, t)}</p>
                      </div>
                      <div className="simulator-saved-scenario-badges">
                        {recommendation.is_saved && (
                          <span className="budget-status budget-status-on-track">{t("simulator.saved")}</span>
                        )}
                        <span className="budget-status budget-status-risk">
                          {getRecommendationSourceLabel(recommendation.source, t)}
                        </span>
                        <span
                          className={`simulator-risk-pill ${
                            recommendation.risk_level === "high"
                              ? "simulator-risk-high"
                              : recommendation.risk_level === "watch"
                                ? "simulator-risk-watch"
                                : "simulator-risk-healthy"
                          }`}
                        >
                          {getScenarioRiskLabel(recommendation.risk_level, t)}
                        </span>
                      </div>
                    </div>

                    <div className="simulator-recommendation-metrics">
                      <div>
                        <span>{t("simulator.impact")}</span>
                        <strong>{formatScenarioCurrency(recommendation.scenario_impact_amount)}</strong>
                      </div>
                      <div>
                        <span>{t("simulator.projectedEnd")}</span>
                        <strong>{formatScenarioCurrency(recommendation.projected_end_balance)}</strong>
                      </div>
                      <div>
                        <span>{t("simulator.monthlyNet")}</span>
                        <strong>{formatSignedScenarioAmount(recommendation.monthly_net_change)}</strong>
                      </div>
                    </div>

                    <p className="budget-inline-note">{getRecommendationReason(recommendation, t)}</p>
                    <div className="simulator-saved-scenario-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => applyRecommendation(recommendation)}
                      >
                        {t("simulator.applyPlan")}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => handlePreviewRecommendation(recommendation)}
                        disabled={
                          recommendationPreviewLoading &&
                          previewedRecommendation?.key === recommendation.key
                        }
                      >
                        {recommendationPreviewLoading &&
                        previewedRecommendation?.key === recommendation.key
                          ? t("simulator.previewing")
                          : t("simulator.previewImpact")}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() =>
                          savedScenario
                            ? handleLoadSavedScenario(savedScenario)
                            : handleSaveRecommendation(recommendation)
                        }
                        disabled={savingRecommendationKey === recommendation.key}
                      >
                        {savingRecommendationKey === recommendation.key
                          ? t("common.saving")
                          : savedScenario
                            ? t("simulator.loadSaved")
                            : t("simulator.savePlan")}
                      </button>
                    </div>
                  </div>
                );
                  })}
                </div>
              )}

              {previewedRecommendation && (
                <div className="simulator-recommendation-preview">
                  <div className="section-header">
                    <div>
                      <h2>{t("simulator.recommendationPreview")}</h2>
                      <p>
                        {t("simulator.currentDraftVs", {
                          label: getRecommendationDisplayLabel(previewedRecommendation, t),
                        })}
                      </p>
                    </div>
                    <div className="budget-section-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => applyRecommendation(previewedRecommendation)}
                      >
                        {t("simulator.applyPreview")}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={clearRecommendationPreview}
                      >
                        {t("simulator.clearPreview")}
                      </button>
                    </div>
                  </div>

                  {recommendationPreviewLoading ? (
                    <div className="empty-state">
                      <p>{t("simulator.previewingRecommendation")}</p>
                    </div>
                  ) : recommendationPreviewError ? (
                    <p className="error-text">{recommendationPreviewError}</p>
                  ) : recommendationPreviewData && simulatorData ? (
                    <>
                      <p className="budget-forecast-banner">{recommendationPreviewNote}</p>
                      <div className="simulator-checkpoint-grid">
                        {recommendationPreviewHighlights.map((item) => (
                          <div
                            key={`recommendation-preview-${item.title}-${item.value}`}
                            className="simulator-checkpoint-card"
                          >
                            <span>{item.title}</span>
                            <strong>{item.value}</strong>
                            <p>{item.detail}</p>
                          </div>
                        ))}
                      </div>

                      <div className="simulator-metrics-grid">
                        <div className="simulator-metric-card">
                          <span>{t("simulator.previewEndBalance")}</span>
                          <strong>{formatScenarioCurrency(recommendationPreviewData.projected_end_balance)}</strong>
                        </div>
                        <div className="simulator-metric-card">
                          <span>{t("simulator.endBalanceLift")}</span>
                          <strong>{formatSignedScenarioAmount(recommendationPreviewBalanceDelta)}</strong>
                        </div>
                        <div className="simulator-metric-card">
                          <span>{t("simulator.monthlyNetLift")}</span>
                          <strong>{formatSignedScenarioAmount(recommendationPreviewMonthlyNetDelta)}</strong>
                        </div>
                      </div>

                      <div className="simulator-comparison-section simulator-chart-card">
                        <ResponsiveContainer width="100%" height={240}>
                          <LineChart data={recommendationPreviewTimeline}>
                            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                            <XAxis dataKey="month" tick={{ fill: chartTheme.text, fontSize: 12 }} />
                            <YAxis tick={{ fill: chartTheme.text, fontSize: 12 }} />
                            <Tooltip
                              contentStyle={customTooltipStyle}
                              formatter={(value) => formatScenarioCurrency(value)}
                            />
                            <Line
                              type="monotone"
                              dataKey="current_ending_balance"
                              name={t("simulator.currentDraft")}
                              stroke={chartTheme.balanceLine}
                              strokeWidth={3}
                              dot={{ r: 3 }}
                            />
                            <Line
                              type="monotone"
                              dataKey="compared_ending_balance"
                              name={getRecommendationDisplayLabel(previewedRecommendation, t)}
                              stroke={chartTheme.compareLine}
                              strokeWidth={3}
                              dot={{ r: 3 }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </>
                  ) : null}
                </div>
              )}
            </>
          )}

          <div className="simulator-preset-grid">
            {SCENARIO_PRESETS.map((preset) => (
              <button
                key={preset.labelKey}
                type="button"
                className="simulator-preset-button"
                onClick={() => applyPreset(preset)}
              >
                <strong>{t(preset.labelKey)}</strong>
                <span>{t(preset.descriptionKey)}</span>
              </button>
            ))}
          </div>

          <div className="section-header simulator-recurring-header">
            <div>
              <h2>{t("simulator.recurringCostLevers")}</h2>
              <p>{t("simulator.recurringCostLeversDetail")}</p>
            </div>
          </div>

          {recurringLoading ? (
            <div className="empty-state">
              <p>{t("simulator.loadingRecurringLevers")}</p>
            </div>
          ) : recurringError ? (
            <div className="empty-state">
              <p>{recurringError}</p>
            </div>
          ) : recurringLeverCandidates.length === 0 ? (
            <div className="empty-state">
              <p>{t("simulator.noRecurringLevers")}</p>
            </div>
          ) : (
            <>
              <div className="simulator-recurring-grid">
                {recurringLeverCandidates.map((item) => (
                  <div
                    key={`sim-recurring-${item.description}-${item.latest_date}`}
                    className="simulator-recurring-card"
                  >
                    <div className="simulator-recurring-top">
                      <div>
                        <h3>{item.description}</h3>
                        <p>{formatCategoryLabel(item.category, t)}</p>
                      </div>
                      <span
                        className={`budget-status ${
                          item.review_priority === "high"
                            ? "budget-status-over"
                            : item.review_priority === "medium"
                              ? "budget-status-risk"
                              : "budget-status-on-track"
                        }`}
                      >
                        {item.review_priority === "high"
                          ? t("transactions.reviewFirst")
                          : item.review_priority === "medium"
                            ? t("transactions.worthReviewing")
                            : t("transactions.stable")}
                      </span>
                    </div>

                    <div className="simulator-recurring-metrics">
                      <div>
                        <span>{t("simulator.monthlyCut")}</span>
                        <strong>{formatScenarioCurrency(item.average_amount)}</strong>
                      </div>
                      <div>
                        <span>{t("simulator.annualImpact")}</span>
                        <strong>{formatScenarioCurrency(item.annualized_amount)}</strong>
                      </div>
                    </div>

                    <p>{formatRecurringReviewReason(item, t)}</p>
                    <div className="simulator-saved-scenario-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() =>
                          handleApplyRecurringLever({
                            amount: item.average_amount,
                            label: item.description,
                          })
                        }
                      >
                        {t("simulator.modelThisCut")}
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {combinedRecurringLever.items.length > 1 && (
                <div className="simulator-recurring-bundle">
                  <div>
                    <h3>{t("simulator.bundleTopCuts")}</h3>
                    <p>
                      {t("simulator.bundleTopCutsDetail", {
                        count: combinedRecurringLever.items.length,
                        amount: formatSignedScenarioAmount(-combinedRecurringLever.totalMonthlyCut),
                      })}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() =>
                      handleApplyRecurringLever({
                        amount: combinedRecurringLever.totalMonthlyCut,
                        label: t("simulator.bundleTopCuts"),
                      })
                    }
                  >
                    {t("simulator.modelBundle")}
                  </button>
                </div>
              )}
            </>
          )}

          <div className="simulator-controls-grid">
            <AccountSelector
              value={selectedAccountId}
              label={t("simulator.simulatorScope")}
              onChange={setSelectedAccountId}
            />

            <div className="budget-form-field">
              <label htmlFor="simulator-months">{t("simulator.monthsAhead")}</label>
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
              <label htmlFor="simulator-income-adjustment">{t("simulator.monthlyIncomeChange")}</label>
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
              <label htmlFor="simulator-expense-adjustment">{t("simulator.monthlyExpenseChange")}</label>
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
              <label htmlFor="simulator-target-balance">{t("simulator.targetEndingBalance")}</label>
              <input
                id="simulator-target-balance"
                type="number"
                step="0.01"
                min="0"
                value={targetBalance}
                onChange={(event) => setTargetBalance(event.target.value)}
                placeholder={t("simulator.optional")}
              />
            </div>

            <div className="budget-form-field">
              <label htmlFor="simulator-event-amount">{t("simulator.oneTimeEventAmount")}</label>
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
              <label htmlFor="simulator-event-month">{t("simulator.eventMonth")}</label>
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
              <label htmlFor="simulator-event-label">{t("simulator.eventLabel")}</label>
              <input
                id="simulator-event-label"
                type="text"
                maxLength="80"
                value={eventLabel}
                onChange={(event) => setEventLabel(event.target.value)}
                placeholder={t("simulator.plannedTrip")}
              />
            </div>
          </div>

          <p className="budget-inline-note">
            {t("simulator.positiveExpenseNote")}
          </p>
          <p className="budget-inline-note">
            {t("simulator.oneTimeEventNote")}
          </p>
          <p className="budget-inline-note">
            {t("simulator.scenarioLinkNote")}
          </p>

          <div className="budget-section-actions">
            <div className="budget-form-field">
              <label htmlFor="saved-scenario-name">{t("simulator.scenarioName")}</label>
              <input
                id="saved-scenario-name"
                type="text"
                maxLength="100"
                value={savedScenarioName}
                onChange={(event) => setSavedScenarioName(event.target.value)}
                placeholder={t("simulator.quarterlyRepairPlan")}
              />
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => handleSaveScenario(false)}
              disabled={savingScenario}
            >
              {savingScenario
                ? savingScenarioMode === "copy"
                  ? t("simulator.saveScenario")
                  : savingScenarioMode === "update"
                  ? t("common.saving")
                  : t("common.saving")
                : activeSavedScenarioId
                ? t("simulator.updateScenario")
                : t("simulator.saveScenario")}
            </button>
            {activeSavedScenarioId && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => handleSaveScenario(true)}
                disabled={savingScenario}
              >
                {savingScenario && savingScenarioMode === "copy" ? t("simulator.savingCopy") : t("simulator.saveAsNew")}
              </button>
            )}
          </div>
          {activeSavedScenarioId && (
            <p className="budget-inline-note">
              {t("simulator.editingLoadedScenario")}
            </p>
          )}

          {scenarioLinkMessage && <p className="success-text">{scenarioLinkMessage}</p>}
          {scenarioLinkError && <p className="error-text">{scenarioLinkError}</p>}
          {recommendationMessage && <p className="success-text">{recommendationMessage}</p>}
          {recurringLeverMessage && <p className="success-text">{recurringLeverMessage}</p>}
          {savedScenarioMessage && <p className="success-text">{savedScenarioMessage}</p>}
          {savedScenarioError && <p className="error-text">{savedScenarioError}</p>}
        </div>

        <div className="dashboard-card">
          <div className="section-header">
            <div>
              <h2>{t("simulator.savedScenarios")}</h2>
              <p>
                {t("simulator.savedScenariosDetail")}
                {savedScenarios.length > 0
                  ? ` ${t("simulator.shownCount", {
                      shown: displayedSavedScenarios.length,
                      total: savedScenarios.length,
                    })}`
                  : ""}
              </p>
            </div>
            <div className="budget-section-actions">
              <div className="budget-form-field simulator-saved-sort-field">
                <label htmlFor="saved-scenario-sort">{t("simulator.sortPlans")}</label>
                <select
                  id="saved-scenario-sort"
                  value={savedScenarioSort}
                  onChange={(event) => setSavedScenarioSort(event.target.value)}
                >
                  {SAVED_SCENARIO_SORT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {t(option.labelKey)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="budget-form-field simulator-saved-search-field">
                <label htmlFor="saved-scenario-search">{t("simulator.searchPlans")}</label>
                <input
                  id="saved-scenario-search"
                  type="text"
                  value={savedScenarioQuery}
                  onChange={(event) => setSavedScenarioQuery(event.target.value)}
                  placeholder={t("simulator.searchPlansPlaceholder")}
                />
              </div>
              <button type="button" className="secondary-button" onClick={fetchSavedScenarios}>
                {t("simulator.refresh")}
              </button>
            </div>
          </div>

          {savedScenariosLoading ? (
            <div className="empty-state">
              <p>{t("simulator.loadingSavedScenarios")}</p>
            </div>
          ) : savedScenarios.length === 0 ? (
            <div className="empty-state">
              <p>{t("simulator.noSavedScenarios")}</p>
            </div>
          ) : (
            <>
              <div className="summary-grid">
                <div className="summary-card balance-card">
                  <span className="card-label">{t("simulator.savedPlans")}</span>
                  <p>{savedScenarioPortfolioSummary.total}</p>
                </div>
                <div className="summary-card income-card">
                  <span className="card-label">{t("simulator.healthy")}</span>
                  <p>{savedScenarioPortfolioSummary.healthyCount}</p>
                </div>
                <div className="summary-card expense-card">
                  <span className="card-label">{t("simulator.needsAttention")}</span>
                  <p>{savedScenarioPortfolioSummary.attentionCount}</p>
                </div>
                <div className="summary-card top-card">
                  <span className="card-label">{t("simulator.bestFinish")}</span>
                  <p>
                    {savedScenarioPortfolioSummary.strongestScenario
                      ? formatScenarioCurrency(
                          savedScenarioPortfolioSummary.strongestScenario.projected_end_balance
                        )
                      : "$0.00"}
                  </p>
                </div>
              </div>

              <div className="import-preview-filters simulator-saved-filters">
                {SAVED_SCENARIO_FILTER_OPTIONS.map((option) => (
                  <button
                    key={`saved-filter-${option.value}`}
                    type="button"
                    className={`import-filter-chip${
                      savedScenarioFilter === option.value ? " import-filter-chip-active" : ""
                    }`}
                    onClick={() => setSavedScenarioFilter(option.value)}
                  >
                    {t(option.labelKey)} ({filterCountByMode[option.value] || 0})
                  </button>
                ))}
              </div>

              <div className="budget-section-actions simulator-saved-quick-actions">
                {savedScenarioPortfolioSummary.strongestScenario && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => handleOpenSavedScenario(savedScenarioPortfolioSummary.strongestScenario)}
                  >
                    {t("simulator.openStrongest")}
                  </button>
                )}
                {savedScenarioPortfolioSummary.strongestScenario &&
                  savedScenarioPortfolioSummary.safestScenario &&
                  savedScenarioPortfolioSummary.strongestScenario.id !==
                    savedScenarioPortfolioSummary.safestScenario.id && (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() =>
                        handleCompareSavedScenarioPair(
                          savedScenarioPortfolioSummary.strongestScenario,
                          savedScenarioPortfolioSummary.safestScenario
                        )
                      }
                    >
                      {t("simulator.compareStrongestSafest")}
                    </button>
                  )}
                {savedScenarioPortfolioSummary.goalLeader && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => handleOpenSavedScenario(savedScenarioPortfolioSummary.goalLeader)}
                  >
                    {t("simulator.openGoalLeader")}
                  </button>
                )}
                {hasSavedScenarioControlOverrides && (
                  <button
                    type="button"
                    className="clear-filter-button"
                    onClick={handleResetSavedScenarioControls}
                  >
                    {t("simulator.resetSavedPlanView")}
                  </button>
                )}
              </div>

              {displayedSavedScenarios.length === 0 ? (
                <div className="empty-state">
                  <p>{t("simulator.noSavedScenarioMatches")}</p>
                </div>
              ) : (
                <>
                  {savedScenarioHighlights.length > 0 && (
                    <div className="simulator-saved-highlight-grid">
                      {savedScenarioHighlights.map((highlight) => (
                        <div
                          key={`saved-highlight-${highlight.key}`}
                          className="budget-card simulator-saved-highlight-card"
                        >
                          <div className="simulator-saved-highlight-top">
                            <div>
                              <span className="card-label">{highlight.title}</span>
                              <h3>{highlight.scenario.name}</h3>
                            </div>
                            <strong>{highlight.value}</strong>
                          </div>
                          <p>{highlight.description}</p>
                          <p className="budget-inline-note">
                            {buildSavedScenarioSummary(highlight.scenario, t)}
                          </p>
                          <div className="simulator-saved-scenario-actions">
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() => handleLoadSavedScenario(highlight.scenario)}
                            >
                              {t("simulator.loadScenario")}
                            </button>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() => handleCompareSavedScenario(highlight.scenario)}
                            >
                              {t("simulator.compare")}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="budget-list">
                    {displayedSavedScenarios.map((scenario) => (
                      <div
                        key={`saved-scenario-${scenario.id}`}
                        className={`budget-card simulator-saved-scenario-card${
                          activeSavedScenarioId === scenario.id ? " simulator-saved-scenario-active" : ""
                        }${
                          comparisonScenarioId === scenario.id ? " simulator-saved-scenario-compared" : ""
                        }`}
                      >
                        <div className="simulator-saved-scenario-top">
                          <div>
                            <h3>{scenario.name}</h3>
                            <p>{buildSavedScenarioSummary(scenario, t)}</p>
                          </div>
                          <div className="simulator-saved-scenario-badges">
                            {activeSavedScenarioId === scenario.id && (
                              <span className="budget-status budget-status-on-track">{t("simulator.loaded")}</span>
                            )}
                            {comparisonScenarioId === scenario.id && (
                              <span className="budget-status budget-status-risk">{t("simulator.comparing")}</span>
                            )}
                          </div>
                        </div>

                        {scenario.event_amount != null && (
                          <p className="budget-inline-note">
                            {t("simulator.savedScenarioEvent", {
                              label: scenario.event_label || t("simulator.oneTimeEvent"),
                              month: scenario.event_month_offset || 1,
                              amount: formatSignedScenarioAmount(scenario.event_amount),
                            })}
                          </p>
                        )}
                        {(scenario.projected_end_balance != null ||
                          scenario.monthly_net_change != null ||
                          scenario.risk_level ||
                          scenario.lowest_balance != null ||
                          scenario.goal_gap_amount != null) && (
                          <div className="simulator-saved-scenario-metrics">
                            {scenario.projected_end_balance != null && (
                              <div className="simulator-saved-scenario-metric">
                                <span>{t("simulator.projectedEnd")}</span>
                                <strong>{formatScenarioCurrency(scenario.projected_end_balance)}</strong>
                              </div>
                            )}
                            {scenario.monthly_net_change != null && (
                              <div className="simulator-saved-scenario-metric">
                                <span>{t("simulator.monthlyNet")}</span>
                                <strong>{formatSignedScenarioAmount(scenario.monthly_net_change)}</strong>
                              </div>
                            )}
                            {scenario.risk_level && (
                              <div className="simulator-saved-scenario-metric">
                                <span>{t("simulator.risk")}</span>
                                <strong>{getScenarioRiskLabel(scenario.risk_level, t)}</strong>
                              </div>
                            )}
                            {scenario.target_balance != null && scenario.goal_gap_amount != null ? (
                              <div className="simulator-saved-scenario-metric">
                                <span>{Number(scenario.goal_gap_amount) <= 0 ? t("simulator.target") : t("simulator.goalGap")}</span>
                                <strong>
                                  {Number(scenario.goal_gap_amount) <= 0
                                    ? t("simulator.onTrack")
                                    : formatScenarioCurrency(scenario.goal_gap_amount)}
                                </strong>
                              </div>
                            ) : scenario.lowest_balance != null ? (
                              <div className="simulator-saved-scenario-metric">
                                <span>{t("simulator.balanceFloor")}</span>
                                <strong>{formatScenarioCurrency(scenario.lowest_balance)}</strong>
                              </div>
                            ) : null}
                          </div>
                        )}
                        <p className="budget-inline-note">
                          {t("simulator.savedDate", { date: new Date(scenario.created_at).toLocaleDateString() })}
                        </p>
                        <div className="simulator-saved-scenario-actions">
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => handleLoadSavedScenario(scenario)}
                          >
                            {t("simulator.loadScenario")}
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => handleCompareSavedScenario(scenario)}
                            disabled={comparisonLoading && comparisonScenarioId === scenario.id}
                          >
                            {comparisonLoading && comparisonScenarioId === scenario.id
                              ? t("simulator.comparingScenarios")
                              : comparisonScenarioId === scenario.id
                              ? t("simulator.refreshCompare")
                              : t("simulator.compare")}
                          </button>
                          <button
                            type="button"
                            className="delete-button"
                            onClick={() => handleDeleteSavedScenario(scenario.id)}
                            disabled={deletingScenarioId === scenario.id}
                          >
                            {deletingScenarioId === scenario.id
                              ? t("simulator.deleting")
                              : t("common.delete")}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>

        {comparedScenario && !loading && (
          <div className="dashboard-card">
            <div className="section-header">
              <div>
                <h2>{t("simulator.scenarioComparison")}</h2>
                <p>{t("simulator.currentDraftVs", { label: comparedScenario.name })}</p>
              </div>
              <div className="budget-section-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => handleLoadSavedScenario(comparedScenario)}
                >
                  {t("simulator.loadComparedScenario")}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={handleClearScenarioComparison}
                >
                  {t("simulator.clearComparison")}
                </button>
              </div>
            </div>

            {comparisonLoading ? (
              <div className="empty-state">
                <p>{t("simulator.comparingScenarios")}</p>
              </div>
            ) : comparisonError ? (
              <p className="error-text">{comparisonError}</p>
            ) : comparisonData && simulatorData ? (
              <>
                <p className="budget-forecast-banner">{comparisonNote}</p>
                <div className="simulator-checkpoint-grid">
                  {comparisonHighlights.map((item) => (
                    <div
                      key={`${item.title}-${item.value}`}
                      className="simulator-checkpoint-card"
                    >
                      <span>{item.title}</span>
                      <strong>{item.value}</strong>
                      <p>{item.detail}</p>
                    </div>
                  ))}
                </div>
                <div className="simulator-metrics-grid">
                  <div className="simulator-metric-card">
                    <span>{t("simulator.currentEndBalance")}</span>
                    <strong>{formatScenarioCurrency(simulatorData.projected_end_balance)}</strong>
                  </div>
                  <div className="simulator-metric-card">
                    <span>{t("simulator.namedEndBalance", { name: comparedScenario.name })}</span>
                    <strong>{formatScenarioCurrency(comparisonData.projected_end_balance)}</strong>
                  </div>
                  <div className="simulator-metric-card">
                    <span>{t("simulator.endBalanceGap")}</span>
                    <strong>{formatSignedScenarioAmount(comparisonBalanceDelta)}</strong>
                  </div>
                  <div className="simulator-metric-card">
                    <span>{t("simulator.monthlyNetGap")}</span>
                    <strong>{formatSignedScenarioAmount(comparisonMonthlyNetDelta)}</strong>
                  </div>
                </div>

                <p className="budget-inline-note">
                  {t("simulator.currentRiskComparedRisk", {
                    current: getScenarioRiskLabel(simulatorData.risk_level, t),
                    compared: getScenarioRiskLabel(comparisonData.risk_level, t),
                  })}
                </p>
                {comparisonData.one_time_event_amount != null && (
                  <p className="budget-inline-note">
                    {t("simulator.comparedPlanEvent", {
                      label: comparisonData.one_time_event_label || t("simulator.oneTimeEvent"),
                      month: comparisonData.one_time_event_month,
                      amount: formatSignedScenarioAmount(comparisonData.one_time_event_amount),
                    })}
                  </p>
                )}

                <div className="simulator-comparison-section simulator-chart-card">
                  <div className="section-header">
                    <h2>{t("simulator.comparisonBalancePath")}</h2>
                    <p>{t("simulator.comparisonBalancePathDetail")}</p>
                  </div>

                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={comparisonTimeline}>
                      <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                      <XAxis dataKey="month" tick={{ fill: chartTheme.text, fontSize: 12 }} />
                      <YAxis tick={{ fill: chartTheme.text, fontSize: 12 }} />
                      <Tooltip contentStyle={customTooltipStyle} />
                      <Line
                        type="monotone"
                        dataKey="current_ending_balance"
                        stroke={chartTheme.balanceLine}
                        strokeWidth={3}
                        dot={{ r: 4 }}
                        connectNulls={false}
                        name={t("simulator.currentDraft")}
                      />
                      <Line
                        type="monotone"
                        dataKey="compared_ending_balance"
                        stroke={chartTheme.compareLine}
                        strokeWidth={3}
                        dot={{ r: 4 }}
                        connectNulls={false}
                        name={comparedScenario.name}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="simulator-comparison-section">
                  <div className="section-header">
                    <h2>{t("simulator.monthlyComparison")}</h2>
                    <p>{t("simulator.monthlyComparisonDetail")}</p>
                  </div>

                  <div className="transactions-table-wrapper">
                    <table className="transactions-table">
                      <thead>
                        <tr>
                          <th>{t("common.month")}</th>
                          <th>{t("simulator.currentBalance")}</th>
                          <th>{comparedScenario.name}</th>
                          <th>{t("simulator.gap")}</th>
                          <th>{t("simulator.currentNet")}</th>
                          <th>{t("simulator.namedNet", { name: comparedScenario.name })}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparisonTimeline.map((row) => (
                          <tr key={`comparison-row-${row.month}`}>
                            <td>{row.month}</td>
                            <td>
                              {row.current_ending_balance == null
                                ? t("simulator.notAvailable")
                                : formatScenarioCurrency(row.current_ending_balance)}
                            </td>
                            <td>
                              {row.compared_ending_balance == null
                                ? t("simulator.notAvailable")
                                : formatScenarioCurrency(row.compared_ending_balance)}
                            </td>
                            <td>
                              {row.ending_balance_gap == null
                                ? t("simulator.notAvailable")
                                : formatSignedScenarioAmount(row.ending_balance_gap)}
                            </td>
                            <td>
                              {row.current_net_change == null
                                ? t("simulator.notAvailable")
                                : formatSignedScenarioAmount(row.current_net_change)}
                            </td>
                            <td>
                              {row.compared_net_change == null
                                ? t("simulator.notAvailable")
                                : formatSignedScenarioAmount(row.compared_net_change)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        )}

        {error && (
          <div className="dashboard-card">
            <p className="error-text">{error}</p>
          </div>
        )}

        {loading ? (
          <div className="dashboard-card">
            <div className="empty-state">
              <p>{t("simulator.runningScenario")}</p>
            </div>
          </div>
        ) : (
          <>
            <div className="summary-grid">
              <div className="summary-card balance-card">
                <span className="card-label">{t("simulator.startingBalance")}</span>
                <p>${simulatorData?.starting_balance?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card income-card">
                <span className="card-label">{t("simulator.monthlyNet")}</span>
                <p>${simulatorData?.monthly_net_change?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card top-card">
                <span className="card-label">{t("simulator.scenarioImpact")}</span>
                <p>${simulatorData?.scenario_impact_amount?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card expense-card">
                <span className="card-label">{t("simulator.projectedEndBalance")}</span>
                <p>${simulatorData?.projected_end_balance?.toFixed(2) || "0.00"}</p>
              </div>

              <div className="summary-card top-card">
                <span className="card-label">{t("simulator.oneTimeEvent")}</span>
                <p>
                  {simulatorData?.one_time_event_amount != null
                    ? `${simulatorData.one_time_event_label || t("simulator.plannedEvent")} ${
                        simulatorData.one_time_event_amount > 0 ? "+" : "-"
                      }$${Math.abs(simulatorData.one_time_event_amount).toFixed(2)}`
                    : t("simulator.none")}
                </p>
              </div>
            </div>

            <div className="dashboard-card">
              <div className="simulator-overview-top">
                <div>
                  <div className="section-header">
                    <h2>{t("simulator.scenarioReadout")}</h2>
                    <p>{formatScopeLabel(simulatorData?.scope_label, t)}</p>
                  </div>
                  <p className="budget-forecast-banner">{buildSimulatorNarrative(simulatorData, t)}</p>
                </div>
                <span className={riskMeta.className}>{riskMeta.label}</span>
              </div>

              <div className="simulator-metrics-grid">
                <div className="simulator-metric-card">
                  <span>{t("simulator.baselineMonthlyIncome")}</span>
                  <strong>${simulatorData?.baseline_monthly_income?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>{t("simulator.baselineMonthlyExpenses")}</span>
                  <strong>${simulatorData?.baseline_monthly_expenses?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>{t("simulator.scenarioIncome")}</span>
                  <strong>${simulatorData?.adjusted_monthly_income?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>{t("simulator.scenarioExpenses")}</span>
                  <strong>${simulatorData?.adjusted_monthly_expenses?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>{t("simulator.baselineEndBalance")}</span>
                  <strong>${simulatorData?.baseline_projected_end_balance?.toFixed(2) || "0.00"}</strong>
                </div>
                <div className="simulator-metric-card">
                  <span>{t("simulator.scenarioEndBalance")}</span>
                  <strong>${simulatorData?.projected_end_balance?.toFixed(2) || "0.00"}</strong>
                </div>
                {simulatorData?.one_time_event_amount != null && (
                  <div className="simulator-metric-card">
                    <span>{simulatorData.one_time_event_month || t("simulator.plannedEvent")}</span>
                    <strong>
                      {(simulatorData.one_time_event_label || t("simulator.oneTimeEvent"))}:{" "}
                      {simulatorData.one_time_event_amount > 0 ? "+" : "-"}$
                      {Math.abs(simulatorData.one_time_event_amount).toFixed(2)}
                    </strong>
                  </div>
                )}
              </div>
            </div>

            <div className="dashboard-card simulator-chart-card">
              <div className="section-header">
                <h2>{t("simulator.projectedBalancePath")}</h2>
                <p>{t("simulator.projectedBalancePathDetail", { month: simulatorData?.start_month })}</p>
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
                    name={t("simulator.baselineBalance")}
                  />
                  <Line
                    type="monotone"
                    dataKey="ending_balance"
                    stroke={chartTheme.balanceLine}
                    strokeWidth={3}
                    dot={{ r: 4 }}
                    name={t("simulator.endingBalance")}
                  />
                  <Line
                    type="monotone"
                    dataKey="net_change"
                    stroke={chartTheme.netLine}
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    dot={false}
                    name={t("simulator.monthlyNet")}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-grid">
              {scenarioCheckpoints.length > 0 && (
                <div className="dashboard-card">
                  <div className="section-header">
                    <h2>{t("simulator.scenarioCheckpoints")}</h2>
                    <p>{t("simulator.scenarioCheckpointsDetail")}</p>
                  </div>

                  <div className="simulator-checkpoint-grid">
                    {scenarioCheckpoints.map((checkpoint) => (
                      <div
                        key={`${checkpoint.title}-${checkpoint.value}`}
                        className="simulator-checkpoint-card"
                      >
                        <span>{checkpoint.title}</span>
                        <strong>{checkpoint.value}</strong>
                        <p>{checkpoint.detail}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {simulatorData?.goal_balance != null && (
                <div className="dashboard-card">
                  <div className="section-header">
                    <h2>{t("simulator.goalPlanner")}</h2>
                    <p>{t("simulator.goalPlannerDetail")}</p>
                  </div>

                  <div className="simulator-metrics-grid">
                    <div className="simulator-metric-card">
                      <span>{t("simulator.targetBalance")}</span>
                      <strong>${simulatorData.goal_balance.toFixed(2)}</strong>
                    </div>
                    <div className="simulator-metric-card">
                      <span>{t("simulator.gapCurrentScenario")}</span>
                      <strong>${(simulatorData.goal_gap_amount || 0).toFixed(2)}</strong>
                    </div>
                    <div className="simulator-metric-card">
                      <span>{t("simulator.requiredMonthlyNet")}</span>
                      <strong>${(simulatorData.required_monthly_net || 0).toFixed(2)}</strong>
                    </div>
                    <div className="simulator-metric-card">
                      <span>{t("simulator.neededMonthlyImprovement")}</span>
                      <strong>${(simulatorData.required_income_lift || 0).toFixed(2)}</strong>
                    </div>
                  </div>

                  <p className="budget-forecast-banner">{buildGoalNote(simulatorData, t)}</p>
                  <p className="budget-inline-note">
                    {t("simulator.equivalentPaths", {
                      income: (simulatorData.required_income_lift || 0).toFixed(2),
                      expense: (simulatorData.required_expense_reduction || 0).toFixed(2),
                    })}
                  </p>
                </div>
              )}

              {(simulatorData?.reduction_plan || []).length > 0 && (
                <div className="dashboard-card">
                  <div className="section-header">
                    <div>
                      <h2>{t("simulator.reductionPlan")}</h2>
                      <p>{t("simulator.reductionPlanDetail")}</p>
                    </div>
                    <div className="budget-section-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={handleApplyReductionPlan}
                        disabled={applyingReductionPlan}
                      >
                        {applyingReductionPlan
                          ? t("transactions.applying")
                          : t("simulator.applyToBudgets", { month: simulatorData.start_month })}
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
                        {t("simulator.openBudgets", { month: simulatorData.start_month })}
                      </button>
                    </div>
                  </div>

                  <div className="simulator-metrics-grid">
                    <div className="simulator-metric-card">
                      <span>{t("simulator.monthlyCutTarget")}</span>
                      <strong>${(simulatorData.reduction_plan_target || 0).toFixed(2)}</strong>
                    </div>
                    <div className="simulator-metric-card">
                      <span>{t("simulator.planCoverage")}</span>
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
                          <strong>{formatCategoryLabel(item.category, t)}</strong>
                          <span className="budget-insight-badge budget-insight-badge-watch">
                            {t("simulator.cutPerMonth", { amount: item.suggested_monthly_reduction.toFixed(2) })}
                          </span>
                        </div>
                        <p className="budget-insight-title">
                          {t("simulator.currentMonthlySpend", { amount: item.current_monthly_spend.toFixed(2) })}
                        </p>
                        <p className="budget-inline-note">
                          {t("simulator.reductionPlanShare", {
                            percent: item.share_percent.toFixed(1),
                            category: formatCategoryLabel(item.category, t),
                            reason: formatReductionReason(item, t),
                          })}
                        </p>
                        <div className="budget-insight-actions">
                          <span className="budget-inline-note">
                            {t("simulator.suggestedNextMonthBudget", { amount: item.suggested_budget_amount.toFixed(2) })}
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
                              {t("simulator.openBudgetTarget")}
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
                              {t("common.reviewTransactions")}
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
                  <h2>{t("simulator.assumptions")}</h2>
                  <p>{t("simulator.assumptionsDetail")}</p>
                </div>

                <ul className="simulator-assumptions-list">
                  {buildSimulatorAssumptions(simulatorData, t).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="dashboard-card">
                <div className="section-header">
                  <h2>{t("simulator.scenarioTimeline")}</h2>
                  <p>{t("simulator.scenarioTimelineDetail")}</p>
                </div>

                <div className="transactions-table-wrapper">
                  <table className="transactions-table">
                    <thead>
                      <tr>
                        <th>{t("common.month")}</th>
                        <th>{t("common.income")}</th>
                        <th>{t("common.expenses")}</th>
                        <th>{t("simulator.oneTimeEvent")}</th>
                        <th>{t("simulator.net")}</th>
                        <th>{t("simulator.baselineBalanceHeader")}</th>
                        <th>{t("simulator.endingBalanceHeader")}</th>
                        <th>{t("simulator.scenarioDelta")}</th>
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
                              ? `${row.one_time_event_label || t("simulator.plannedEvent")} ${
                                  row.one_time_event_amount > 0 ? "+" : "-"
                                }$${Math.abs(row.one_time_event_amount).toFixed(2)}`
                              : t("simulator.none")}
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
