export type ApiErrorShape = {
  message?: string;
  error?: string;
};

function normalizeBaseUrl(baseUrl: string): string {
  // Allow absolute (http://host/api) or relative (/api).
  // Ensure no trailing slash.
  return baseUrl.replace(/\/+$/, '');
}

export function getApiBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL;
  // Default aligns with dev proxy in vite.config.ts
  return normalizeBaseUrl(fromEnv && fromEnv.trim().length > 0 ? fromEnv : '/api');
}

export class ApiError extends Error {
  readonly status: number;
  readonly bodyText?: string;

  constructor(message: string, opts: { status: number; bodyText?: string }) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status;
    this.bodyText = opts.bodyText;
  }
}

function parseMaybeJson(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;

  const resp = await fetch(url, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init?.headers ?? {}),
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    },
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    const parsed = parseMaybeJson(text);
    const msg =
      typeof parsed === 'object' && parsed && ('message' in parsed || 'error' in parsed)
        ? String((parsed as ApiErrorShape).message ?? (parsed as ApiErrorShape).error)
        : text || resp.statusText;

    throw new ApiError(`${resp.status} ${resp.statusText}: ${msg}`, {
      status: resp.status,
      bodyText: text,
    });
  }

  return (await resp.json()) as T;
}

export async function apiFetchVoid(path: string, init?: RequestInit): Promise<void> {
  await apiFetch<unknown>(path, init);
}
