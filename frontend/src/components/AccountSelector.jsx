import { useEffect, useState } from "react";
import api from "../services/api";
import { ALL_ACCOUNTS_VALUE, getSelectedAccountId, setSelectedAccountId } from "../services/accountStorage";

function AccountSelector({ onChange, allowAll = true, label = "Account" }) {
  const [accounts, setAccounts] = useState([]);
  const [selected, setSelected] = useState(getSelectedAccountId());

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
    setSelectedAccountId(selected);
    onChange?.(selected);
  }, [selected, onChange]);

  return (
    <div className="account-selector-block">
      <label htmlFor="account-selector">{label}</label>
      <select
        id="account-selector"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
      >
        {allowAll && <option value={ALL_ACCOUNTS_VALUE}>All Accounts</option>}
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