import { z } from "zod";

/**
 * Backend her zaman `{"detail": string}` veya (422'de) `{"detail": string, "errors": [...]}`
 * döner — services/api/app/main.py::validation_exception_handler /
 * http_exception_handler ile doğrulandı (internal/* rotalar hariç, panel onları
 * kullanmıyor).
 */
const errorBodySchema = z.object({
  detail: z.string(),
  errors: z
    .array(
      z.object({
        loc: z.array(z.union([z.string(), z.number()])).optional(),
        msg: z.string().optional(),
        type: z.string().optional(),
      })
    )
    .optional(),
});

export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isValidation(): boolean {
    return this.status === 422;
  }
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CSRF_COOKIE = "ivac_csrf";
const CSRF_HEADER = "X-CSRF-Token";

/** Yalnız tarayıcıda çalışır: httpOnly OLMAYAN CSRF çerezini okur (double-submit deseni). */
function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE}=([^;]*)`));
  const value = match?.[1];
  return value ? decodeURIComponent(value) : null;
}

export type ApiRequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  formData?: FormData;
  searchParams?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
};

function buildUrl(path: string, searchParams?: ApiRequestOptions["searchParams"]): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

function extractFieldErrors(
  errors: z.infer<typeof errorBodySchema>["errors"]
): Record<string, string> {
  const fieldErrors: Record<string, string> = {};
  for (const err of errors ?? []) {
    const field = (err.loc ?? []).filter((p) => p !== "body").join(".");
    if (field && err.msg) fieldErrors[field] = err.msg;
  }
  return fieldErrors;
}

/**
 * Ham fetch sarmalayıcı. Oturum httpOnly çerezde taşınır (`credentials: "include"`),
 * localStorage/sessionStorage'a hiçbir token yazılmaz. Mutasyon isteklerinde
 * (GET/HEAD/OPTIONS dışı) CSRF header'ı otomatik eklenir.
 */
export async function apiRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  options: ApiRequestOptions = {}
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;

  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  if (method !== "GET") {
    const csrf = readCsrfCookie();
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  const response = await fetch(buildUrl(path, options.searchParams), {
    method,
    headers,
    body,
    credentials: "include",
    signal: options.signal,
  });

  if (!response.ok) {
    const raw = await response.json().catch(() => ({ detail: response.statusText }));
    const parsed = errorBodySchema.safeParse(raw);
    const detail = parsed.success ? parsed.data.detail : response.statusText;
    const fieldErrors = parsed.success ? extractFieldErrors(parsed.data.errors) : {};
    throw new ApiError(response.status, detail, fieldErrors);
  }

  if (response.status === 204) {
    return schema.parse(undefined);
  }

  const raw = await response.json();
  return schema.parse(raw);
}

/** application/json döndürmeyen uçlar (ör. CSV export) için ham Response döner. */
export async function apiRequestRaw(
  path: string,
  options: ApiRequestOptions = {}
): Promise<Response> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  if (method !== "GET") {
    const csrf = readCsrfCookie();
    if (csrf) headers[CSRF_HEADER] = csrf;
  }
  const response = await fetch(buildUrl(path, options.searchParams), {
    method,
    headers,
    body,
    credentials: "include",
  });
  if (!response.ok) {
    const raw = await response.json().catch(() => ({ detail: response.statusText }));
    const parsed = errorBodySchema.safeParse(raw);
    throw new ApiError(response.status, parsed.success ? parsed.data.detail : response.statusText);
  }
  return response;
}

export { API_BASE_URL };
