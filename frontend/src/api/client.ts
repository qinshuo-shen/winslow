// Small typed fetch wrapper for the FastAPI backend, proxied at `/api` by
// Vite in dev (see vite.config.ts) and served same-origin in production.

const BASE_PATH = "/api";

// Multi-user follow-up: the session cookie is already sent automatically
// (fetch defaults to `credentials: "same-origin"`, and this app is always
// same-origin) -- no per-call change needed for that. What every verb
// below DOES newly need is a shared signal for "the server says I'm not
// logged in," since a session can expire/get revoked mid-use on any page.
// Dispatching one DOM event here means AuthContext is the only thing that
// has to listen for it, rather than every one of this app's many call
// sites handling a 401 itself.
export const UNAUTHORIZED_EVENT = "winslow:unauthorized";

function reportIfUnauthorized(status: number): void {
  if (status === 401) {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
  }
}

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
    reportIfUnauthorized(res.status);
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
    reportIfUnauthorized(res.status);
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
    reportIfUnauthorized(res.status);
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(res.status, detail);
  }

  return body as T;
}

/**
 * PATCH `${BASE_PATH}${path}` with `payload` as a JSON body, and parse the
 * JSON response as `T`. Same error handling as `apiPost` -- used for
 * partial updates (e.g. the Board's PATCH /backlog/{id}).
 */
export async function apiPatch<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${BASE_PATH}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    reportIfUnauthorized(res.status);
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(res.status, detail);
  }

  return body as T;
}
