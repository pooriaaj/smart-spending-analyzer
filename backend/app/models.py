from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    reset_token_hash = Column(String(255), nullable=True)
    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    accounts = relationship(
        "Account",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    transactions = relationship(
        "Transaction",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    category_memories = relationship(
        "CategoryMemory",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    budgets = relationship(
        "BudgetPlan",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False, default="other")
    is_active = Column(Boolean, nullable=False, default=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    owner = relationship("User", back_populates="accounts")
    transactions = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    budgets = relationship(
        "BudgetPlan",
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_accounts_owner_name", "owner_id", "name"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    date = Column(Date, nullable=False, index=True)
    type = Column(String(20), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True)

    owner = relationship("User", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_owner_date", "owner_id", "date"),
        Index("ix_transactions_owner_type", "owner_id", "type"),
        Index("ix_transactions_owner_category", "owner_id", "category"),
        Index("ix_transactions_account_date", "account_id", "date"),
    )


class CategoryMemory(Base):
    __tablename__ = "category_memories"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    transaction_type = Column(String(20), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    owner = relationship("User", back_populates="category_memories")

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "keyword",
            "transaction_type",
            name="uq_category_memory_owner_keyword_type",
        ),
        Index("ix_category_memories_owner_keyword", "owner_id", "keyword"),
    )


class BudgetPlan(Base):
    __tablename__ = "budget_plans"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(String(7), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True)

    owner = relationship("User", back_populates="budgets")
    account = relationship("Account", back_populates="budgets")

    __table_args__ = (
        Index("ix_budget_plans_owner_month", "owner_id", "month"),
        Index("ix_budget_plans_owner_account_month", "owner_id", "account_id", "month"),
    )
