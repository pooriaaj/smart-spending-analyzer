import { describe, expect, it } from "vitest";

import vercelConfig from "../../vercel.json";

describe("Vercel API rewrites", () => {
  it("routes trailing-slash API paths to Render before the SPA fallback", () => {
    const rewrites = vercelConfig.rewrites || [];
    const trailingSlashApiRewriteIndex = rewrites.findIndex(
      (rewrite) => rewrite.source === "^/api/(.+)/$",
    );
    const normalApiRewriteIndex = rewrites.findIndex(
      (rewrite) => rewrite.source === "/api/:path*",
    );
    const spaFallbackIndex = rewrites.findIndex((rewrite) => rewrite.source === "/(.*)");

    expect(rewrites[trailingSlashApiRewriteIndex]).toEqual({
      source: "^/api/(.+)/$",
      destination: "https://smart-spending-analyzer.onrender.com/$1/",
    });
    expect(trailingSlashApiRewriteIndex).toBeGreaterThanOrEqual(0);
    expect(normalApiRewriteIndex).toBeGreaterThan(trailingSlashApiRewriteIndex);
    expect(spaFallbackIndex).toBeGreaterThan(normalApiRewriteIndex);
  });
});
