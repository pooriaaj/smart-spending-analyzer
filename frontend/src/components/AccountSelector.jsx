import { useEffect, useState } from "react";
import api from "../services/api";
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
  setSelectedAccountId as persistSelectedAccountId,
} from "../services/accountStorage";

function normalizeSelection(value, allowAll) {
  return allowAll || value !== ALL_ACCOUNTS_VALUE ? String(value || "") : "";
}

function AccountSelector({
  onChange,
  allowAll = true,
  label = "Account",
  value,
  persistSelection = true,
}) {
  const [accounts, setAccounts] = useState([]);
  const [internalSelected, setInternalSelected] = useState(() =>
    normalizeSelection(value ?? getSelectedAccountId(), allowAll)
  );

  const requestedSelected =
    value === undefined ? internalSelected : normalizeSelection(value, allowAll);
  const accountIds = accounts.map((account) => String(account.id));
  const canUseAllAccounts = allowAll && requestedSelected === ALL_ACCOUNTS_VALUE;
  const canUseSelectedAccount =
    requestedSelected && accountIds.includes(String(requestedSelected));
  const selected =
    accounts.length > 0 && !canUseAllAccounts && !canUseSelectedAccount
      ? accountIds[0]
      : requestedSelected;

  useEffect(() => {
    const loadAccounts = async () => {
      try {
        const response = await api.get("/accounts/");
        setAccounts(response.data || []);
      } catch (error) {
        console.error("Failed to load accounts:", error);
      }
    };

    loadAccounts();
  }, []);

  useEffect(() => {
    if (!selected) {
      return;
    }

    if (persistSelection) {
      persistSelectedAccountId(selected);
    }
    onChange?.(selected);
  }, [selected, onChange, persistSelection]);

  const handleSelectionChange = (event) => {
    const nextSelected = event.target.value;
    setInternalSelected(nextSelected);
    if (value !== undefined) {
      onChange?.(nextSelected);
    }
  };

  return (
    <div className="account-selector-block">
      <label htmlFor="account-selector">{label}</label>
      <select
        id="account-selector"
        value={selected}
        onChange={handleSelectionChange}
      >
        {allowAll && <option value={ALL_ACCOUNTS_VALUE}>All Accounts</option>}
        {!allowAll && !accounts.length && <option value="">Loading accounts...</option>}
        {accounts.map((account) => (
          <option key={account.id} value={String(account.id)}>
            {account.name} ({account.type})
          </option>
        ))}
      </select>
    </div>
  );
}

export default AccountSelector;
