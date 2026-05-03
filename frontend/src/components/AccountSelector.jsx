import { useEffect, useState } from "react";
import api from "../services/api";
import {
  ALL_ACCOUNTS_VALUE,
  getSelectedAccountId,
  setSelectedAccountId as persistSelectedAccountId,
} from "../services/accountStorage";
import { useLanguage } from "../i18n/LanguageContext";
import { formatAccountLabel } from "../utils/displayLabels";

function normalizeSelection(value, allowAll) {
  return allowAll || value !== ALL_ACCOUNTS_VALUE ? String(value || "") : "";
}

function AccountSelector({
  onChange,
  allowAll = true,
  label,
  value,
  persistSelection = true,
}) {
  const { t } = useLanguage();
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
      <label htmlFor="account-selector">{label || t("common.account")}</label>
      <select
        id="account-selector"
        value={selected}
        onChange={handleSelectionChange}
      >
        {allowAll && <option value={ALL_ACCOUNTS_VALUE}>{t("common.allAccounts")}</option>}
        {!allowAll && !accounts.length && <option value="">{t("common.loadingAccounts")}</option>}
        {accounts.map((account) => (
          <option key={account.id} value={String(account.id)}>
            {formatAccountLabel(account, t)}
          </option>
        ))}
      </select>
    </div>
  );
}

export default AccountSelector;
