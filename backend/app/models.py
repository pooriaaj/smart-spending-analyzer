from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    reset_token_hash = Column(String(255), nullable=True)
    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)

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


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    date = Column(Date, nullable=False, index=True)
    type = Column(String(20), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    owner = relationship("User", back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_owner_date", "owner_id", "date"),
        Index("ix_transactions_owner_type", "owner_id", "type"),
        Index("ix_transactions_owner_category", "owner_id", "category"),
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