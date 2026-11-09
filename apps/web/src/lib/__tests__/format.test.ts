import { describe, expect, it } from "vitest";
import {
  formatPrice,
  formatVolume,
  pairAssets,
  pairIssuers,
  pairSymbol,
} from "../format";

const USDC = "USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN";
const YUSDC = "yUSDC:GDGTVWSM4MGS4T7Z6W4RPWOCHE2I6RDFCIFZGS3DOA63LWQTRNZNTTFF";

describe("pair parsing", () => {
  it("handles a native base", () => {
    expect(pairSymbol(`XLM/${USDC}`)).toBe("XLM/USDC");
    expect(pairIssuers(`XLM/${USDC}`)).toEqual([USDC.split(":")[1]]);
  });

  it("handles a credit base with its own issuer", () => {
    expect(pairSymbol(`${YUSDC}/${USDC}`)).toBe("yUSDC/USDC");
    const [base, counter] = pairAssets(`${YUSDC}/${USDC}`);
    expect(base).toEqual({ code: "yUSDC", issuer: YUSDC.split(":")[1] });
    expect(counter.code).toBe("USDC");
    expect(pairIssuers(`${YUSDC}/${USDC}`)).toHaveLength(2);
  });
});

describe("market formatting", () => {
  it("labels prices and volumes in the counter asset, not dollars", () => {
    expect(formatPrice(0.10034, "USDC")).toBe("0.1003 USDC");
    expect(formatPrice(35.19, "SHX")).toBe("35.19 SHX");
    expect(formatVolume(4_810_000, "USDC")).toBe("4.81M USDC");
    expect(formatVolume(1234, "XLM")).toBe("1.2K XLM");
  });
});
