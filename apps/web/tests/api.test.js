import { test } from "node:test";
import assert from "node:assert/strict";
import { apiFetch, ApiError } from "../dashboard/js/api.js";

function fakeFetch(response) {
  return async () => response;
}

test("apiFetch resolves with parsed JSON on a 2xx response", async () => {
  const fetchImpl = fakeFetch({ ok: true, json: async () => ({ status: "ok" }) });
  const data = await apiFetch("/health", { baseUrl: "http://x", fetchImpl });
  assert.deepEqual(data, { status: "ok" });
});

test("apiFetch throws ApiError with the response's detail message on failure", async () => {
  const fetchImpl = fakeFetch({
    ok: false,
    status: 404,
    statusText: "Not Found",
    json: async () => ({ detail: "Unknown asset pair: XLM/FOO" }),
  });
  await assert.rejects(
    () => apiFetch("/score/GABC/XLM%2FFOO", { baseUrl: "http://x", fetchImpl }),
    (err) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.status, 404);
      assert.equal(err.message, "Unknown asset pair: XLM/FOO");
      return true;
    },
  );
});

test("apiFetch falls back to statusText when the error body isn't JSON", async () => {
  const fetchImpl = fakeFetch({
    ok: false,
    status: 500,
    statusText: "Internal Server Error",
    json: async () => {
      throw new SyntaxError("not json");
    },
  });
  await assert.rejects(
    () => apiFetch("/health", { baseUrl: "http://x", fetchImpl }),
    (err) => {
      assert.equal(err.message, "Internal Server Error");
      return true;
    },
  );
});

test("apiFetch builds the request URL from baseUrl + path", async () => {
  let requestedUrl;
  const fetchImpl = async (url) => {
    requestedUrl = url;
    return { ok: true, json: async () => ({}) };
  };
  await apiFetch("/alerts/recent?limit=50", { baseUrl: "http://localhost:8000", fetchImpl });
  assert.equal(requestedUrl, "http://localhost:8000/alerts/recent?limit=50");
});
