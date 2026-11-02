import { useCallback, useEffect, useState } from "react";

const TOKEN_KEY = "foresight_session";
export const session = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

// Set VITE_API_BASE_URL to the deployed API origin (for example,
// https://<render-service>.onrender.com) in the Vercel project settings.
// The relative fallback remains useful with the local Vite proxy.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/backend").replace(/\/+$/, "");

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const token = session.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options, headers, signal: options.signal || AbortSignal.timeout(330000),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Cannot reach the API. Check that the backend is running. If you started training, refresh the registry before retrying.", 0);
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    const payload: { detail?: string | { msg: string }[] } = await response.json().catch(() => ({}));
    if (typeof payload.detail === "string") message = payload.detail;
    if (Array.isArray(payload.detail)) message = payload.detail.map((item) => item.msg).join("; ");
    if (response.status === 401 && token) {
      session.clear();
      globalThis.dispatchEvent(new Event("session-expired"));
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setData(undefined);
    setError("");
    setLoading(path !== null);
    if (path) {
      api<T>(path, { signal: controller.signal })
        .then((value) => { if (!controller.signal.aborted) setData(value); })
        .catch((failure: unknown) => {
          if (!controller.signal.aborted) setError(errorMessage(failure));
        })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }
    return () => controller.abort();
  }, [path, revision]);
  return { data, error, loading, refresh };
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred. Please retry.";
}

export const money = (value: number, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
export const count = (value: number) => new Intl.NumberFormat("en-US").format(value);
export const percent = (value: number | null | undefined) => value == null ? "Not recorded" : `${(value * 100).toFixed(1)}%`;
export const label = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
export const dateTime = (value: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";
