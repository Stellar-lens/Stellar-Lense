import { NextRequest, NextResponse } from "next/server";
import { getNewsFeed } from "@/lib/news";

/**
 * Proxies CryptoPanic + CoinDesk so CRYPTOPANIC_API_TOKEN never reaches
 * the browser. This route runs server-side only; src/lib/news.ts's fetch
 * calls happen here, not in client code.
 */
export async function GET(request: NextRequest) {
  const currency = request.nextUrl.searchParams.get("currency") ?? undefined;
  const feed = await getNewsFeed(currency);
  return NextResponse.json(feed);
}
