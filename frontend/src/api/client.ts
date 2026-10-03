/**
 * The single axios instance (standards/08): session cookie, CSRF header, error normalisation, 401 handling.
 *
 * Generated request functions (src/api/generated) call `apiRequest`, which returns the response body,
 * i.e. the standard envelope `{ success, message, data, pagination? }` (ADR-0002). Hooks unwrap `data`
 * so list pages keep `pagination`.
 */
import axios, { AxiosError, type AxiosRequestConfig } from "axios";

const CSRF_COOKIE = "ft_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = new Set(["get", "head", "options"]);

export const http = axios.create({
  // Generated paths already start with /api/v1; production uses the same origin behind Nginx.
  baseURL: import.meta.env.VITE_API_ORIGIN ?? "",
  withCredentials: true,
  timeout: 30_000,
});

export function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

http.interceptors.request.use((config) => {
  const method = (config.method ?? "get").toLowerCase();
  if (!SAFE_METHODS.has(method)) {
    const token = readCookie(CSRF_COOKIE);
    if (token) config.headers.set(CSRF_HEADER, token);
  }
  return config;
});

/** Error thrown by every API call: the envelope's message plus field errors for forms. */
export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string[]>;

  constructor(status: number, message: string, fieldErrors: Record<string, string[]> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;

/** Registered by the auth provider: a 401 on a protected call means the session expired. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler;
}

function toFieldErrors(value: unknown): Record<string, string[]> {
  if (!value || typeof value !== "object") return {};
  const result: Record<string, string[]> = {};
  for (const [key, messages] of Object.entries(value as Record<string, unknown>)) {
    result[key] = Array.isArray(messages) ? messages.map(String) : [String(messages)];
  }
  return result;
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof AxiosError) {
    const status = error.response?.status ?? 0;
    const body = error.response?.data as { message?: unknown; errors?: unknown } | undefined;
    const message =
      typeof body?.message === "string"
        ? body.message
        : status === 0
          ? "Cannot reach the server. Check your connection and try again."
          : "Something went wrong. Please try again.";
    return new ApiError(status, message, toFieldErrors(body?.errors));
  }
  return new ApiError(0, "Something went wrong. Please try again.");
}

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const apiError = toApiError(error);
    const url = error instanceof AxiosError ? (error.config?.url ?? "") : "";
    if (apiError.status === 401 && !url.includes("/auth/")) onUnauthorized?.();
    return Promise.reject(apiError);
  },
);

/** orval mutator: every generated function goes through here. */
export async function apiRequest<T>(config: AxiosRequestConfig, options?: AxiosRequestConfig): Promise<T> {
  const response = await http.request<T>({ ...config, ...options });
  return response.data;
}

export default apiRequest;
