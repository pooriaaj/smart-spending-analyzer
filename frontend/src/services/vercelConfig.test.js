import { describe, expect, it } from "vitest";

import vercelConfig from "../../vercel.json";

describe("Vercel API rewrites", () => {
  it("routes trailing-slash root API paths to Render before the SPA fallback", () => {
    const rewrites = vercelConfig.rewrites || [];
    const accountsRewriteIndex = rewrites.findIndex(
      (rewrite) => rewrite.source === "/api/accounts/",
    );
    const transactionsRewriteIndex = rewrites.findIndex(
      (rewrite) => rewrite.source === "/api/transactions/",
    );
    const budgetsRewriteIndex = rewrites.findIndex(
      (rewrite) => rewrite.source === "/api/budgets/",
    );
    const normalApiRewriteIndex = rewrites.findIndex(
      (rewrite) => rewrite.source === "/api/:path*",
    );
    const spaFallbackIndex = rewrites.findIndex((rewrite) => rewrite.source === "/(.*)");

    expect(rewrites[accountsRewriteIndex]).toEqual({
      source: "/api/accounts/",
      destination: "https://smart-spending-analyzer.onrender.com/accounts/",
    });
    expect(rewrites[transactionsRewriteIndex]).toEqual({
      source: "/api/transactions/",
      destination: "https://smart-spending-analyzer.onrender.com/transactions/",
    });
    expect(rewrites[budgetsRewriteIndex]).toEqual({
      source: "/api/budgets/",
      destination: "https://smart-spending-analyzer.onrender.com/budgets/",
    });

    expect(accountsRewriteIndex).toBeGreaterThanOrEqual(0);
    expect(transactionsRewriteIndex).toBeGreaterThan(accountsRewriteIndex);
    expect(budgetsRewriteIndex).toBeGreaterThan(transactionsRewriteIndex);
    expect(normalApiRewriteIndex).toBeGreaterThan(budgetsRewriteIndex);
    expect(spaFallbackIndex).toBeGreaterThan(normalApiRewriteIndex);
  });
});
