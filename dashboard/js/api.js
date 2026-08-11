export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Fetch JSON from the LedgerLens API.
 * `fetchImpl` and `baseUrl` are injectable so this stays unit-testable
 * without a browser (see tests/api.test.js).
 */
export async function apiFetch(path, { baseUrl, fetchImpl = fetch, signal } = {}) {
  const resp = await fetchImpl(`${baseUrl}${path}`, { signal });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(detail, resp.status);
  }
  return resp.json();
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * apiFetch with retry-on-transient-failure. Retries network errors and
 * 5xx responses with exponential backoff; 4xx responses (bad input,
 * unknown wallet/pair) are the caller's problem and fail immediately.
 */
export async function apiFetchWithRetry(path, opts = {}, { retries = 2, baseDelayMs = 300 } = {}) {
  let attempt = 0;
  for (;;) {
    try {
      return await apiFetch(path, opts);
    } catch (err) {
      const transient = !(err instanceof ApiError) || err.status >= 500;
      if (!transient || attempt >= retries || opts.signal?.aborted) throw err;
      await sleep(baseDelayMs * 2 ** attempt);
      attempt += 1;
    }
  }
}
