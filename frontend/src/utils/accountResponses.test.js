import { describe, expect, it } from "vitest";

import { getAccountsFromResponse } from "./accountResponses";

const accounts = [{ id: 1, name: "Main Account" }];

describe("getAccountsFromResponse", () => {
  it("accepts raw account arrays", () => {
    expect(getAccountsFromResponse(accounts)).toEqual(accounts);
  });

  it("accepts common wrapped account response shapes", () => {
    expect(getAccountsFromResponse({ accounts })).toEqual(accounts);
    expect(getAccountsFromResponse({ items: accounts })).toEqual(accounts);
    expect(getAccountsFromResponse({ results: accounts })).toEqual(accounts);
    expect(getAccountsFromResponse({ data: accounts })).toEqual(accounts);
  });

  it("accepts nested wrapped account response shapes", () => {
    expect(getAccountsFromResponse({ data: { accounts } })).toEqual(accounts);
    expect(getAccountsFromResponse({ accounts: { items: accounts } })).toEqual(accounts);
    expect(getAccountsFromResponse({ results: { data: accounts } })).toEqual(accounts);
  });

  it("accepts a single account object", () => {
    expect(getAccountsFromResponse({ id: 2, name: "Savings", type: "savings" })).toEqual([
      { id: 2, name: "Savings", type: "savings" },
    ]);
  });

  it("falls back to an empty array for unexpected responses", () => {
    expect(getAccountsFromResponse(null)).toEqual([]);
    expect(getAccountsFromResponse({ accounts: { id: 1 } })).toEqual([]);
    expect(getAccountsFromResponse({ message: "ok" })).toEqual([]);
  });
});
