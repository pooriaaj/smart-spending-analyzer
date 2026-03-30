from pydantic import BaseModel, EmailStr
from datetime import date


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TransactionBase(BaseModel):
    amount: float
    category: str
    description: str
    date: date
    type: str


class TransactionCreate(TransactionBase):
    pass


class TransactionResponse(TransactionBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True


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


class RecentTransactionItem(BaseModel):
    id: int
    amount: float
    category: str
    description: str
    date: date
    type: str

    class Config:
        from_attributes = True


class TopExpenseCategory(BaseModel):
    category: str
    total: float


class CategorySuggestionRequest(BaseModel):
    description: str
    type: str


class CategorySuggestionResponse(BaseModel):
    suggested_category: str
    confidence: float
    matched_keyword: str | None = None
    reason: str


class BulkCategorySuggestionItem(BaseModel):
    transaction_id: int
    current_category: str
    description: str
    type: str
    suggested_category: str
    confidence: float
    matched_keyword: str | None = None
    reason: str


class BulkCategorySuggestionResponse(BaseModel):
    total_candidates: int
    suggestions: list[BulkCategorySuggestionItem]


class BulkCategoryApplyRequest(BaseModel):
    transaction_ids: list[int]


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


class AssistantQueryRequest(BaseModel):
    question: str


class AssistantQueryResponse(BaseModel):
    answer: str
    supporting_points: list[str]
    suggested_followups: list[str]