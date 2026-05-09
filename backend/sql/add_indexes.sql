CREATE INDEX IF NOT EXISTS ix_transactions_owner_date
ON transactions (owner_id, date);

CREATE INDEX IF NOT EXISTS ix_transactions_owner_type
ON transactions (owner_id, type);

CREATE INDEX IF NOT EXISTS ix_transactions_owner_category
ON transactions (owner_id, category);

CREATE INDEX IF NOT EXISTS ix_transactions_owner_account_date
ON transactions (owner_id, account_id, date);

CREATE INDEX IF NOT EXISTS ix_transactions_owner_account_type_date
ON transactions (owner_id, account_id, type, date);

CREATE INDEX IF NOT EXISTS ix_transactions_owner_account_category_date
ON transactions (owner_id, account_id, category, date);

CREATE INDEX IF NOT EXISTS ix_transactions_date
ON transactions (date);

CREATE INDEX IF NOT EXISTS ix_transactions_type
ON transactions (type);

CREATE INDEX IF NOT EXISTS ix_transactions_category
ON transactions (category);

CREATE INDEX IF NOT EXISTS ix_category_memories_owner_keyword
ON category_memories (owner_id, keyword);

CREATE INDEX IF NOT EXISTS ix_category_memories_transaction_type
ON category_memories (transaction_type);
