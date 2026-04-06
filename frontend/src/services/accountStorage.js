export const ALL_ACCOUNTS_VALUE = "all";

export function getSelectedAccountId() {
  return localStorage.getItem("selectedAccountId") || ALL_ACCOUNTS_VALUE;
}

export function setSelectedAccountId(value) {
  localStorage.setItem("selectedAccountId", value || ALL_ACCOUNTS_VALUE);
}