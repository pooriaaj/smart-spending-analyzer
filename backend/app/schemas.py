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