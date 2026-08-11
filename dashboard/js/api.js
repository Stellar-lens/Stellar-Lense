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
