export function getAccountsFromResponse(data) {
  if (!data) {
    return [];
  }

  if (Array.isArray(data)) {
    return data;
  }

  if (typeof data !== "object") {
    return [];
  }

  if (data.id !== undefined && data.name !== undefined) {
    return [data];
  }

  if (Array.isArray(data?.accounts)) {
    return data.accounts;
  }

  if (Array.isArray(data?.items)) {
    return data.items;
  }

  if (Array.isArray(data?.results)) {
    return data.results;
  }

  if (Array.isArray(data?.data)) {
    return data.data;
  }

  for (const key of ["accounts", "items", "results", "data"]) {
    if (data[key] && typeof data[key] === "object") {
      const nestedAccounts = getAccountsFromResponse(data[key]);
      if (nestedAccounts.length > 0) {
        return nestedAccounts;
      }
    }
  }

  return [];
}
