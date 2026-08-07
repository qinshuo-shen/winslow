// Small typed fetch wrapper for the FastAPI backend, proxied at `/api` by
// Vite in dev (see vite.config.ts) and served same-origin in production.

const BASE_PATH = "/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(
      typeof detail === "string"
        ? detail
        : `Request failed with status ${status}`,
    );
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * GET `${BASE_PATH}${path}` and parse the JSON body as `T`. Throws
 * `ApiError` (surfacing FastAPI's `{"detail": ...}` error body) for any
 * non-2xx response.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_PATH}${path}`);
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(res.status, detail);
  }

  return body as T;
}

/**
 * DELETE `${BASE_PATH}${path}` and parse the JSON response as `T`. Same
 * error handling as `apiGet`/`apiPost` -- throws `ApiError` for any non-2xx
 * response. Used by the planner's unassign action
 * (DELETE /planner/assign/{uid}).
 */
export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_PATH}${path}`, { method: "DELETE" });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(res.status, detail);
  }

  return body as T;
}

/**
 * POST `${BASE_PATH}${path}` with `payload` (if given) as a JSON body, and
 * parse the JSON response as `T`. Same error handling as `apiGet` -- throws
 * `ApiError` (surfacing FastAPI's `{"detail": ...}` error body, e.g. the
 * 400s from character/rest and gear/{id}/buy) for any non-2xx response.
 */
export async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const res = await fetch(`${BASE_PATH}${path}`, {
    method: "POST",
    headers: payload !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: payload !== undefined ? JSON.stringify(payload) : undefined,
  });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(res.status, detail);
  }

  return body as T;
}
