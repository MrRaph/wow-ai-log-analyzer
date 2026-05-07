"use client";
import type { ApiError, TokenPair } from "@/types/api";
import { clearAuth, getAccessToken, getRefreshToken, setTokens } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

interface RequestOpts {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  locale?: string;
  /** Allow callers to opt out of the Bearer header (login/register endpoints). */
  anonymous?: boolean;
  /** When true, do not attempt a 401-refresh retry. Used internally. */
  skipRefresh?: boolean;
}

let refreshInFlight: Promise<TokenPair | null> | null = null;

async function tryRefresh(): Promise<TokenPair | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) {
        clearAuth();
        return null;
      }
      const tokens = (await res.json()) as TokenPair;
      setTokens(tokens);
      return tokens;
    } catch {
      clearAuth();
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export async function apiFetch<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (opts.locale) headers["X-Locale"] = opts.locale;
  if (!opts.anonymous) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });

  if (res.status === 401 && !opts.anonymous && !opts.skipRefresh) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return apiFetch<T>(path, { ...opts, skipRefresh: true });
    }
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let json: unknown = null;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      json = { error: { code: "parse_error", message: text } } satisfies ApiError;
    }
  }

  if (!res.ok) {
    const err = (json as ApiError | null)?.error;
    throw new ApiClientError(
      err?.message ?? `HTTP ${res.status}`,
      res.status,
      err?.code ?? "http_error",
      err?.details,
    );
  }
  return json as T;
}
