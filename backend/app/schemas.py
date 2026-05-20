from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security import validate_password_strength


TransactionType = Literal["income", "expense"]
AssistantMode = Literal["balanced", "strict", "coach"]
AccountType = Literal["chequing", "savings", "credit_card", "cash", "business", "other"]
ImportDetectedType = Literal["csv_statement", "receipt_image", "pdf_statement"]
ImportStatus = Literal["completed", "draft_review", "table_review"]
TransactionEntrySource = Literal[
    "manual",
    "manual_import_review",
    "csv_import",
    "pdf_import",
    "receipt_import",
    "statement_import",
    "seed",
]


class ORMBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, value: str) -> str:
        validate_password_strength(value)
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserProfileResponse(ORMBaseModel):
    id: int
    email: EmailStr
    community_learning_enabled: bool = True


class UserProfileUpdate(BaseModel):
    email: EmailStr


class UserLearningPreferenceUpdate(BaseModel):
    community_learning_enabled: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_is_strong(cls, value: str) -> str:
        validate_password_strength(value)
        return value


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_url: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def reset_password_is_strong(cls, value: str) -> str:
        validate_password_strength(value)
        return value


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
    items: list[BudgetPlanTarget] = Field(default_factory=list, max_length=100)


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
    data_quality_level: str = "empty"
    data_quality_score: float = 0.0
    data_quality_message: str | None = None
    data_review_action_count: int = 0
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
    amount: float = Field(gt=0, le=1_000_000)
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
    category_confidence: float = 0.0
    category_source: str | None = None
    category_reason: str | None = None
    description: str
    date: date
    type: TransactionType
    entry_source: str = "manual"
    import_file_name: str | None = None
    import_file_type: str | None = None
    imported_at: datetime | None = None
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


class TransactionSourceSummaryItem(BaseModel):
    entry_source: str
    label: str
    transaction_count: int = 0
    income_count: int = 0
    expense_count: int = 0
    total_income: float = 0.0
    total_expenses: float = 0.0
    balance: float = 0.0
    imported_file_count: int = 0
    latest_transaction_date: date | None = None
    latest_imported_at: datetime | None = None


class TransactionSourceSummaryResponse(BaseModel):
    total_transactions: int = 0
    manual_count: int = 0
    imported_count: int = 0
    seed_count: int = 0
    total_income: float = 0.0
    total_expenses: float = 0.0
    balance: float = 0.0
    imported_file_count: int = 0
    latest_imported_at: datetime | None = None
    sources: list[TransactionSourceSummaryItem] = Field(default_factory=list)


class TransactionImportHistoryItem(BaseModel):
    import_file_name: str
    import_file_type: str | None = None
    entry_source: str
    account_id: int | None = None
    transaction_count: int = 0
    income_count: int = 0
    expense_count: int = 0
    total_income: float = 0.0
    total_expenses: float = 0.0
    balance: float = 0.0
    first_transaction_date: date | None = None
    latest_transaction_date: date | None = None
    first_imported_at: datetime | None = None
    latest_imported_at: datetime | None = None


class TransactionImportHistoryResponse(BaseModel):
    import_batch_count: int = 0
    imported_file_count: int = 0
    total_imported_transactions: int = 0
    total_income: float = 0.0
    total_expenses: float = 0.0
    balance: float = 0.0
    latest_imported_at: datetime | None = None
    items: list[TransactionImportHistoryItem] = Field(default_factory=list)


class TransactionDataQualityAction(BaseModel):
    key: str
    label: str
    detail: str
    severity: str = "info"
    count: int = 0


class TransactionDataQualityResponse(BaseModel):
    transaction_count: int = 0
    manual_count: int = 0
    imported_count: int = 0
    uncategorized_count: int = 0
    category_review_count: int = 0
    learning_candidate_count: int = 0
    suspicious_amount_count: int = 0
    likely_duplicate_count: int = 0
    quality_level: str = "empty"
    quality_score: float = 0.0
    message: str
    actions: list[TransactionDataQualityAction] = Field(default_factory=list)
    source_summary: TransactionSourceSummaryResponse


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
    transaction_ids: list[int] = Field(default_factory=list, max_length=1000)
    account_id: int | None = None


class SuspiciousAmountRepairApplyResponse(BaseModel):
    updated_count: int
    repairs: list[dict] = Field(default_factory=list)


class DuplicateCleanupApplyRequest(BaseModel):
    transaction_ids: list[int] = Field(default_factory=list, max_length=1000)
    account_id: int | None = None


class DuplicateCleanupApplyResponse(BaseModel):
    deleted_count: int
    kept_transaction_ids: list[int] = Field(default_factory=list)
    deleted_transaction_ids: list[int] = Field(default_factory=list)
    skipped_transaction_ids: list[int] = Field(default_factory=list)


class FreshStartRequest(BaseModel):
    keep_from: date | None = None
    account_id: int | None = None
    delete_all: bool = False
    entry_source: TransactionEntrySource | None = None


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
    amount: float | None = Field(default=None, gt=0, le=1_000_000)


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
    transaction_ids: list[int] = Field(default_factory=list, max_length=1000)


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
    representative_amount: float | None = None
    amount_min: float
    amount_max: float
    example_descriptions: list[str] = Field(default_factory=list)
    reason: str
    review_required: bool


class CategoryLearningEventItem(BaseModel):
    merchant_key: str
    display_name: str
    category: str
    type: TransactionType
    signal_source: str
    confidence: float
    affected_count: int
    created_at: datetime


class CategoryLearningCandidatesResponse(BaseModel):
    total_candidates: int
    candidates: list[CategoryLearningCandidateItem]


class TransactionReviewQueueDuplicateItem(BaseModel):
    transaction_ids: list[int] = Field(default_factory=list)
    date: date
    description: str
    type: TransactionType
    category: str
    amount: float
    account_id: int | None = None
    occurrence_count: int
    reason: str


class TransactionCategoryReviewItem(BaseModel):
    transaction_id: int
    date: date
    description: str
    type: TransactionType
    category: str
    amount: float
    account_id: int | None = None
    category_confidence: float = 0.0
    category_source: str | None = None
    category_reason: str | None = None
    reason: str
    merchant_key: str | None = None
    suggested_category: str | None = None
    suggestion_confidence: float = 0.0
    suggestion_source: str | None = None
    suggestion_reason: str | None = None
    apply_to_similar_recommended: bool = True


class TransactionReviewQueueResponse(BaseModel):
    quality_report: TransactionDataQualityResponse
    next_action: TransactionDataQualityAction | None = None
    amount_repair_count: int = 0
    amount_repairs: list[SuspiciousAmountRepairItem] = Field(default_factory=list)
    category_review_count: int = 0
    category_review_candidates: list[TransactionCategoryReviewItem] = Field(default_factory=list)
    category_learning_count: int = 0
    category_learning_candidates: list[CategoryLearningCandidateItem] = Field(default_factory=list)
    duplicate_group_count: int = 0
    duplicate_groups: list[TransactionReviewQueueDuplicateItem] = Field(default_factory=list)


class CategoryLearningSummaryResponse(BaseModel):
    transaction_count: int
    uncategorized_count: int
    learning_candidate_count: int
    personal_memory_count: int
    merchant_profile_count: int
    community_learning_enabled: bool
    community_pattern_count: int
    learning_event_count: int
    recent_learning_events: list[CategoryLearningEventItem] = Field(default_factory=list)
    confidence_level: str
    confidence_score: float
    message: str


class CategoryLearningApplyRequest(BaseModel):
    merchant_key: str = Field(min_length=1, max_length=160)
    type: TransactionType
    category: str = Field(min_length=1, max_length=100)
    account_id: int | None = None
    representative_amount: float | None = Field(default=None, gt=0, le=1_000_000)


class CategoryLearningApplyResponse(BaseModel):
    matched_count: int
    updated_count: int
    memory_entries_created: int
    memory_entries_updated: int


class CategoryReviewApplyRequest(BaseModel):
    transaction_id: int = Field(gt=0)
    category: str = Field(min_length=1, max_length=100)
    apply_to_similar: bool = True


class CategoryReviewApplyResponse(BaseModel):
    transaction_id: int
    category: str
    matched_count: int
    updated_count: int
    similar_updated_count: int
    memory_entries_created: int
    memory_entries_updated: int
    learning_event_recorded: bool


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
    learning_candidates: list[CategoryLearningCandidateItem] = Field(default_factory=list)
    learning_signals: list[MoneyMapLearningSignal] = Field(default_factory=list)
    actions: list[MoneyMapAction] = Field(default_factory=list)
    narrative: str


class AssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


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
    question: str = Field(min_length=1, max_length=1200)
    history: list[AssistantMessage] = Field(default_factory=list, max_length=12)
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
    merchant: str | None = Field(default=None, max_length=160)
    date: str | None = None
    amount: float | None = None
    category: str = "other"
    type: TransactionType = "expense"
    confidence: float = 0.0
    raw_text_preview: str | None = Field(default=None, max_length=1200)
    notes: list[str] = Field(default_factory=list)


class ImportSummary(BaseModel):
    imported: int = 0
    duplicates_skipped: int = 0
    invalid_rows_skipped: int = 0


class DraftTransaction(BaseModel):
    amount: float | None = None
    category: str = "other"
    description: str = Field(default="", max_length=500)
    date: str | None = None
    type: TransactionType = "expense"
    account_id: int
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)


class StatementPreviewRow(BaseModel):
    date: str
    description: str = Field(min_length=1, max_length=500)
    amount: float
    amount_confidence: float = 1.0
    amount_review_required: bool = False
    amount_review_reason: str | None = Field(default=None, max_length=500)
    suggested_amount: float | None = Field(default=None, gt=0, le=1_000_000)
    amount_review_approved: bool = False
    type: TransactionType
    category: str = Field(min_length=1, max_length=100)
    source_line: str | None = Field(default=None, max_length=1200)
    source_file_name: str | None = Field(default=None, max_length=255)
    source_file_type: ImportDetectedType | None = None
    confidence: float = 0.0
    review_reason: str | None = None
    category_confidence: float = 0.0
    category_source: str | None = None
    category_reason: str | None = Field(default=None, max_length=500)
    category_review_required: bool = False
    category_review_reason: str | None = Field(default=None, max_length=500)
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
    rows: list[StatementPreviewRow] = Field(default_factory=list, max_length=5000)
