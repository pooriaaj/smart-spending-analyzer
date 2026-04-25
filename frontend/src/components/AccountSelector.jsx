import { useEffect, useState } from "react";
import api from "../services/api";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId, setSelectedAccountId } from "../services/accountStorage";

function AccountSelector({ onChange, allowAll = true, label = "Account" }) {
  const [accounts, setAccounts] = useState([]);
  const [selected, setSelected] = useState(() => {
    const storedAccountId = getSelectedAccountId();
    return allowAll || storedAccountId !== ALL_ACCOUNTS_VALUE ? storedAccountId : "";
  });

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
    if (!accounts.length) {
      onChange?.(selected);
      return;
    }

    const accountIds = accounts.map((account) => String(account.id));
    const canUseAllAccounts = allowAll && selected === ALL_ACCOUNTS_VALUE;
    const canUseSelectedAccount = selected && accountIds.includes(String(selected));

    if (!canUseAllAccounts && !canUseSelectedAccount) {
      setSelected(accountIds[0]);
      return;
    }

    setSelectedAccountId(selected);
    onChange?.(selected);
  }, [accounts, allowAll, selected, onChange]);

  return (
    <div className="account-selector-block">
      <label htmlFor="account-selector">{label}</label>
      <select
        id="account-selector"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
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
