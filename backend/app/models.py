from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
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

    merchant_category_profiles = relationship(
        "MerchantCategoryProfile",
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
    saved_scenarios = relationship(
        "SavedScenario",
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
    saved_scenarios = relationship(
        "SavedScenario",
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
        Index("ix_transactions_owner_account_date", "owner_id", "account_id", "date"),
        Index("ix_transactions_owner_account_type_date", "owner_id", "account_id", "type", "date"),
        Index("ix_transactions_owner_account_category_date", "owner_id", "account_id", "category", "date"),
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


class MerchantCategoryProfile(Base):
    __tablename__ = "merchant_category_profiles"

    id = Column(Integer, primary_key=True, index=True)
    merchant_key = Column(String(160), nullable=False)
    display_name = Column(String(160), nullable=False)
    category = Column(String(100), nullable=False)
    transaction_type = Column(String(20), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.9)
    confirmation_count = Column(Integer, nullable=False, default=1)
    last_amount = Column(Float, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="merchant_category_profiles")

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "merchant_key",
            "transaction_type",
            name="uq_merchant_profile_owner_key_type",
        ),
        Index("ix_merchant_profiles_owner_key", "owner_id", "merchant_key"),
    )


class MerchantLookupCache(Base):
    __tablename__ = "merchant_lookup_cache"

    id = Column(Integer, primary_key=True, index=True)
    merchant_key = Column(String(160), nullable=False)
    display_name = Column(String(160), nullable=False)
    category = Column(String(100), nullable=False)
    transaction_type = Column(String(20), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.78)
    matched_signal = Column(String(160), nullable=True)
    provider = Column(String(40), nullable=False, default="semantic")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "merchant_key",
            "transaction_type",
            name="uq_merchant_lookup_cache_key_type",
        ),
        Index("ix_merchant_lookup_cache_key", "merchant_key"),
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


class SavedScenario(Base):
    __tablename__ = "saved_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    months = Column(Integer, nullable=False, default=6)
    income_adjustment = Column(Float, nullable=False, default=0.0)
    expense_adjustment = Column(Float, nullable=False, default=0.0)
    target_balance = Column(Float, nullable=True)
    event_month_offset = Column(Integer, nullable=True)
    event_amount = Column(Float, nullable=True)
    event_label = Column(String(80), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    owner = relationship("User", back_populates="saved_scenarios")
    account = relationship("Account", back_populates="saved_scenarios")

    __table_args__ = (
        Index("ix_saved_scenarios_owner_account", "owner_id", "account_id"),
    )
