from __future__ import annotations

from datetime import date
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


class TransactionBase(BaseModel):
    amount: float
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    date: date
    type: TransactionType
    account_id: int


class TransactionCreate(TransactionBase):
    pass


class TransactionResponse(TransactionBase, ORMBaseModel):
    id: int
    owner_id: int


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


class AssistantMessage(BaseModel):
    role: str
    content: str


class AssistantAction(BaseModel):
    label: str
    page: str
    section: str | None = None
    category: str | None = None
    transaction_type: str | None = None
    month: str | None = None
    account_id: int | None = None


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
    is_duplicate: bool = False
    duplicate_reason: str | None = None


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
