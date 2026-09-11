/**
 * Basic usage example for @stellar-lense/sdk.
 *
 * Instantiates the client, checks API health, lists a page of risk scores,
 * and fetches the detail for a single wallet. Errors from the API are
 * surfaced as `StellarLenseError`.
 *
 * Run it against a local API:
 *
 *   cd sdk
 *   npm install
 *   STELLARLENSE_BASE_URL=http://localhost:8000 npm run example
 *
 * (`npm run example` uses `tsx` to execute this file directly — no build step.)
 *
 * When consuming the published package instead of running it from this repo,
 * change the import below to:
 *
 *   import { StellarLenseClient, StellarLenseError } from "@stellar-lense/sdk";
 */

import { StellarLenseClient, StellarLenseError } from "../src/index";

async function main(): Promise<void> {
  const client = new StellarLenseClient({
    baseUrl: process.env.STELLARLENSE_BASE_URL ?? "http://localhost:8000",
    // adminKey / complianceKey can be passed here for gated endpoints:
    // adminKey: process.env.STELLARLENSE_ADMIN_KEY,
    timeout: 15_000,
  });

  try {
    // 1. Liveness check.
    const health = await client.getHealth();
    console.log("API health:", health);

    // 2. List the 5 highest-scoring wallets.
    const scores = await client.getScores({
      limit: 5,
      sort_by: "score",
      order: "desc",
    });
    console.log(`\nFetched ${scores.length} risk score(s):`);
    for (const s of scores) {
      const flags = [s.benford_flag && "benford", s.ml_flag && "ml"]
        .filter(Boolean)
        .join(",");
      console.log(
        `  ${s.wallet}  ${s.asset_pair}  score=${s.score} ` +
          `confidence=${s.confidence}${flags ? `  flags=[${flags}]` : ""}`,
      );
    }

    // 3. Fetch the full record for the first wallet, if any.
    if (scores.length > 0) {
      const detail = await client.getScore(scores[0].wallet);
      console.log(`\nDetail for ${detail.wallet}:`, detail);
    }
  } catch (err) {
    if (err instanceof StellarLenseError) {
      console.error(
        `StellarLense API error (HTTP ${err.statusCode ?? "n/a"}): ${err.message}`,
      );
      if (err.zodIssues) console.error("Validation issues:", err.zodIssues);
      process.exitCode = 1;
      return;
    }
    throw err;
  }
}

main();
