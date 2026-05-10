from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


TransactionType = Literal["income", "expense"]
AssistantMode = Literal["balanced", "strict", "coach"]
AccountType = Literal["chequing", "savings", "credit_card", "cash", "business", "other"]
ImportDetectedType = Literal["csv_statement", "receipt_image", "pdf_statement"]
ImportStatus = Literal["completed", "draft_review", "table_review"]


class ORMBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserProfileResponse(ORMBaseModel):
    id: int
    email: EmailStr


class UserProfileUpdate(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_url: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=128)


class MessageResponse(BaseModel):
    message: str


class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType = "other"


class AccountCreate(AccountBase):
    pass


class AccountUpdate(AccountBase):
    pass


class AccountResponse(AccountBase, ORMBaseModel):
    id: int
    owner_id: int
    is_active: bool


class AccountSummaryResponse(AccountResponse):
    total_income: float = 0.0
    total_expenses: float = 0.0
    balance: float = 0.0
    top_category: str | None = None
    top_category_amount: float = 0.0


class BudgetPlanBase(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    category: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0)
    account_id: int | None = None


class BudgetPlanCreate(BudgetPlanBase):
    pass


class BudgetPlanTarget(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0)


class BudgetCopyRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    account_id: int | None = None


class BudgetBuildRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    account_id: int | None = None


class BudgetBulkUpsertRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    account_id: int | None = None
    items: list[BudgetPlanTarget] = Field(default_factory=list)


class BudgetPlanResponse(ORMBaseModel):
    id: int
    month: str
    category: str
    amount: float
    owner_id: int
    account_id: int | None = None
    spent_amount: float = 0.0
    remaining_amount: float = 0.0
    usage_percent: float = 0.0
    status: str
    days_total: int | None = None
    days_elapsed: int | None = None
    days_remaining: int | None = None
    daily_allowance: float | None = None
    daily_pace: float | None = None
    pace_note: str | None = None
    projected_spent_amount: float | None = None
    projected_remaining_amount: float | None = None
    projected_usage_percent: float | None = None
    projected_status: str | None = None
    projection_note: str | None = None


class BudgetSuggestionResponse(BaseModel):
    category: str
    suggested_amount: float
    average_spent: float = 0.0
    latest_month_spent: float = 0.0
    note: str


class BudgetInsightResponse(BaseModel):
    category: str
    severity: str
    title: str
    detail: str
    recommended_amount: float | None = None


class BudgetSummaryResponse(BaseModel):
    total_budgeted: float = 0.0
    total_spent: float = 0.0
    total_remaining: float = 0.0
    over_budget_count: int = 0
    at_risk_count: int = 0
    on_track_count: int = 0
    projected_total_spent: float = 0.0
    projected_total_remaining: float = 0.0
    projected_over_budget_count: int = 0
    projected_at_risk_count: int = 0
    projected_on_track_count: int = 0


class BudgetListResponse(BaseModel):
    month: str
    account_id: int | None = None
    budgets: list[BudgetPlanResponse]
    summary: BudgetSummaryResponse
    available_categories: list[str] = Field(default_factory=list)
    suggestions: list[BudgetSuggestionResponse] = Field(default_factory=list)
    insights: list[BudgetInsightResponse] = Field(default_factory=list)


class BudgetCopyResponse(BaseModel):
    source_month: str
    target_month: str
    account_id: int | None = None
    copied_count: int = 0
    skipped_existing_count: int = 0
    message: str


class BudgetBuildResponse(BaseModel):
    source_month: str
    target_month: str
    account_id: int | None = None
    created_count: int = 0
    adjusted_count: int = 0
    skipped_existing_count: int = 0
    message: str


class BudgetBulkUpsertResponse(BaseModel):
    month: str
    account_id: int | None = None
    applied_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    message: str


class SavedScenarioBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    months: int = Field(default=6, ge=1, le=12)
    income_adjustment: float = 0.0
    expense_adjustment: float = 0.0
    target_balance: float | None = Field(default=None, gt=0)
    event_month_offset: int | None = Field(default=None, ge=1, le=12)
    event_amount: float | None = None
    event_label: str | None = Field(default=None, max_length=80)
    account_id: int | None = None


class SavedScenarioCreate(SavedScenarioBase):
    pass


class SavedScenarioResponse(SavedScenarioBase, ORMBaseModel):
    id: int
    owner_id: int
    created_at: datetime
    projected_end_balance: float | None = None
    monthly_net_change: float | None = None
    risk_level: str | None = None
    lowest_balance: float | None = None
    goal_gap_amount: float | None = None


class FutureSimulationPoint(BaseModel):
    month: str
    income: float
    expenses: float
    net_change: float
    baseline_ending_balance: float
    ending_balance: float
    balance_delta: float
    one_time_event_amount: float = 0.0
    one_time_event_label: str | None = None


class FutureSimulationReductionItem(BaseModel):
    category: str
    current_monthly_spend: float
    suggested_monthly_reduction: float
    suggested_budget_amount: float
    share_percent: float
    reason: str


class FutureSimulationResponse(BaseModel):
    scope_label: str = "All accounts combined"
    start_month: str
    months: int
    starting_balance: float
    baseline_monthly_income: float
    baseline_monthly_expenses: float
    adjusted_monthly_income: float
    adjusted_monthly_expenses: float
    monthly_net_change: float
    baseline_monthly_net_change: float
    baseline_projected_end_balance: float
    scenario_impact_amount: float
    projected_change_amount: float
    projected_end_balance: float
    risk_level: str
    narrative: str
    one_time_event_month: str | None = None
    one_time_event_amount: float | None = None
    one_time_event_label: str | None = None
    goal_balance: float | None = None
    goal_gap_amount: float | None = None
    required_monthly_net: float | None = None
    required_income_lift: float | None = None
    required_expense_reduction: float | None = None
    goal_note: str | None = None
    reduction_plan_target: float | None = None
    reduction_plan_coverage_amount: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    timeline: list[FutureSimulationPoint] = Field(default_factory=list)
    reduction_plan: list[FutureSimulationReductionItem] = Field(default_factory=list)


class FutureSimulationRecommendationItem(BaseModel):
    key: str
    label: str
    description: str
    reason: str
    source: str
    saved_scenario_id: int | None = None
    is_saved: bool = False
    months: int
    income_adjustment: float = 0.0
    expense_adjustment: float = 0.0
    target_balance: float | None = None
    event_month_offset: int | None = None
    event_amount: float | None = None
    event_label: str | None = None
    projected_end_balance: float
    scenario_impact_amount: float
    monthly_net_change: float
    risk_level: str


class FutureSimulationRecommendationsResponse(BaseModel):
    scope_label: str = "All accounts combined"
    items: list[FutureSimulationRecommendationItem] = Field(default_factory=list)


class TransactionBase(BaseModel):
    amount: float
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    date: date
    type: TransactionType
    account_id: int


class TransactionCreate(TransactionBase):
    pass


class TransactionResponse(ORMBaseModel):
    id: int
    amount: float
    category: str
    description: str
    date: date
    type: TransactionType
    account_id: int | None = None
    owner_id: int


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse] = Field(default_factory=list)
    total: int = 0
    scope_total: int = 0
    page: int = 1
    page_size: int = 12
    total_pages: int = 1
    available_months: list[str] = Field(default_factory=list)
    available_categories: list[str] = Field(default_factory=list)


class SuspiciousAmountRepairItem(BaseModel):
    transaction_id: int
    date: date
    description: str
    type: TransactionType
    category: str
    current_amount: float
    suggested_amount: float
    confidence: float
    reason: str


class SuspiciousAmountRepairPreviewResponse(BaseModel):
    total_candidates: int
    candidates: list[SuspiciousAmountRepairItem] = Field(default_factory=list)


class SuspiciousAmountRepairApplyRequest(BaseModel):
    transaction_ids: list[int] = Field(default_factory=list)
    account_id: int | None = None


class SuspiciousAmountRepairApplyResponse(BaseModel):
    updated_count: int
    repairs: list[dict] = Field(default_factory=list)


class FreshStartRequest(BaseModel):
    keep_from: date | None = None
    account_id: int | None = None
    delete_all: bool = False


class FreshStartResponse(BaseModel):
    deleted_count: int
    message: str


class AnalyticsSummary(BaseModel):
    total_income: float
    total_expenses: float
    balance: float


class CategoryBreakdownItem(BaseModel):
    category: str
    total: float


class MonthlySummaryItem(BaseModel):
    month: str
    income: float
    expenses: float
    balance: float


class RecentTransactionItem(ORMBaseModel):
    id: int
    amount: float
    category: str
    description: str
    date: date
    type: TransactionType
    account_id: int


class TopExpenseCategory(BaseModel):
    category: str
    total: float


class CategorySuggestionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    type: TransactionType


class CategorySuggestionResponse(BaseModel):
    suggested_category: str
    confidence: float
    matched_keyword: str | None = None
    reason: str


class BulkCategorySuggestionItem(BaseModel):
    transaction_id: int
    current_category: str
    description: str
    type: TransactionType
    suggested_category: str
    confidence: float
    matched_keyword: str | None = None
    reason: str


class BulkCategorySuggestionResponse(BaseModel):
    total_candidates: int
    suggestions: list[BulkCategorySuggestionItem]


class BulkCategoryApplyRequest(BaseModel):
    transaction_ids: list[int] = Field(default_factory=list)


class BulkCategoryApplyResponse(BaseModel):
    updated_count: int


class CategoryLearningCandidateItem(BaseModel):
    merchant_key: str
    display_name: str
    type: TransactionType
    transaction_count: int
    current_category: str
    suggested_category: str
    confidence: float
    total_amount: float
    amount_min: float
    amount_max: float
    example_descriptions: list[str] = Field(default_factory=list)
    reason: str
    review_required: bool


class CategoryLearningCandidatesResponse(BaseModel):
    total_candidates: int
    candidates: list[CategoryLearningCandidateItem]


class CategoryLearningApplyRequest(BaseModel):
    merchant_key: str = Field(min_length=1, max_length=160)
    type: TransactionType
    category: str = Field(min_length=1, max_length=100)
    account_id: int | None = None


class CategoryLearningApplyResponse(BaseModel):
    matched_count: int
    updated_count: int
    memory_entries_created: int
    memory_entries_updated: int


class SpendingInsights(BaseModel):
    current_month: str | None = None
    current_month_expenses: float
    previous_month_expenses: float
    expense_change_percent: float | None = None
    top_category: str | None = None
    top_category_amount: float
    top_category_share_percent: float | None = None
    insights: list[str]
    recommendations: list[str]


class OverspendingAlertItem(BaseModel):
    level: str
    title: str
    message: str


class OverspendingAlertsResponse(BaseModel):
    current_month: str | None = None
    alerts: list[OverspendingAlertItem]


class CategoryTrendItem(BaseModel):
    category: str
    current_amount: float
    previous_amount: float
    change_amount: float
    change_percent: float | None = None


class CategoryTrendsResponse(BaseModel):
    current_month: str | None = None
    previous_month: str | None = None
    top_increases: list[CategoryTrendItem]
    top_decreases: list[CategoryTrendItem]
    summary: list[str]


class RecurringExpenseItem(BaseModel):
    description: str
    category: str
    type: TransactionType = "expense"
    occurrences: int
    cadence: str
    average_amount: float
    latest_amount: float
    latest_date: date
    average_interval_days: int | None = None
    next_expected_date: date | None = None
    annualized_amount: float
    latest_change_percent: float | None = None
    review_priority: str = "low"
    review_reason: str | None = None
    confidence: float


class RecurringExpensesResponse(BaseModel):
    items: list[RecurringExpenseItem]


class MoneyMapCategoryItem(BaseModel):
    category: str
    total: float
    share_percent: float


class MoneyMapRecurringItem(BaseModel):
    description: str
    category: str
    average_amount: float
    annualized_amount: float
    review_priority: str
    review_reason: str | None = None


class MoneyMapCategorySuggestionItem(BaseModel):
    description: str
    current_category: str
    suggested_category: str
    confidence: float
    source: str
    matched_keyword: str | None = None
    reason: str


class MoneyMapLearningSignal(BaseModel):
    label: str
    value: str
    detail: str
    severity: str = "info"


class MoneyMapAction(BaseModel):
    label: str
    detail: str
    page: str
    priority: str = "medium"


class MoneyMapResponse(BaseModel):
    scope_label: str = "All accounts combined"
    status: str
    confidence_level: str
    confidence_score: float
    transaction_count: int = 0
    month_count: int = 0
    learned_merchant_count: int = 0
    memory_count: int = 0
    uncategorized_count: int = 0
    summary: AnalyticsSummary
    top_categories: list[MoneyMapCategoryItem] = Field(default_factory=list)
    recurring_highlights: list[MoneyMapRecurringItem] = Field(default_factory=list)
    category_suggestions: list[MoneyMapCategorySuggestionItem] = Field(default_factory=list)
    learning_signals: list[MoneyMapLearningSignal] = Field(default_factory=list)
    actions: list[MoneyMapAction] = Field(default_factory=list)
    narrative: str


class AssistantMessage(BaseModel):
    role: str
    content: str


class AssistantAction(BaseModel):
    label: str
    page: str
    section: str | None = None
    scenario_name: str | None = None
    saved_scenario_id: int | None = None
    compare_saved_scenario_id: int | None = None
    category: str | None = None
    description: str | None = None
    transaction_type: str | None = None
    month: str | None = None
    months_ahead: int | None = None
    account_id: int | None = None
    amount: float | None = None
    target_balance: float | None = None
    income_adjustment: float | None = None
    expense_adjustment: float | None = None
    event_month_offset: int | None = None
    event_amount: float | None = None
    event_label: str | None = None


class AssistantQueryRequest(BaseModel):
    question: str = Field(min_length=1)
    history: list[AssistantMessage] = Field(default_factory=list)
    mode: AssistantMode = "balanced"
    account_id: int | None = None


class AssistantQueryResponse(BaseModel):
    answer: str
    supporting_points: list[str]
    suggested_followups: list[str]
    suggested_actions: list[AssistantAction] = Field(default_factory=list)
    scope_label: str = "All accounts combined"


class AssistantSuggestionsResponse(BaseModel):
    suggestions: list[str]


class ReceiptScanResponse(BaseModel):
    merchant: str | None = None
    date: str | None = None
    amount: float | None = None
    category: str = "other"
    type: TransactionType = "expense"
    confidence: float = 0.0
    raw_text_preview: str | None = None
    notes: list[str] = Field(default_factory=list)


class ImportSummary(BaseModel):
    imported: int = 0
    duplicates_skipped: int = 0
    invalid_rows_skipped: int = 0


class DraftTransaction(BaseModel):
    amount: float | None = None
    category: str = "other"
    description: str = ""
    date: str | None = None
    type: TransactionType = "expense"
    account_id: int
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)


class StatementPreviewRow(BaseModel):
    date: str
    description: str
    amount: float
    type: TransactionType
    category: str
    source_line: str | None = None
    confidence: float = 0.0
    review_reason: str | None = None
    category_confidence: float = 0.0
    category_source: str | None = None
    category_reason: str | None = None
    category_review_required: bool = False
    category_review_reason: str | None = None
    is_duplicate: bool = False
    duplicate_reason: str | None = None
    matched_transaction_id: int | None = None
    reconciliation_status: str = "missing"
    reconciliation_reason: str | None = None
    is_repeating_pattern: bool = False
    repeating_pattern_type: TransactionType | None = None
    repeating_pattern_reason: str | None = None
    repeating_pattern_occurrences: int = 0
    repeating_pattern_average_amount: float | None = None
    repeating_pattern_cadence: str | None = None
    repeating_pattern_confidence: float | None = None


class SmartImportResponse(BaseModel):
    detected_type: ImportDetectedType
    status: ImportStatus
    message: str
    import_summary: ImportSummary | None = None
    draft_transaction: DraftTransaction | None = None
    preview_rows: list[StatementPreviewRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ConfirmPreviewImportRequest(BaseModel):
    account_id: int
    rows: list[StatementPreviewRow] = Field(default_factory=list)
