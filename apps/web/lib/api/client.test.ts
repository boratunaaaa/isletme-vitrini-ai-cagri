import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { apiRequest, ApiError } from "./client";

const schema = z.object({ ok: z.boolean() });

function mockFetchOnce(response: { status: number; body: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: response.status >= 200 && response.status < 300,
      status: response.status,
      statusText: "status",
      json: async () => response.body,
    })
  );
}

describe("apiRequest", () => {
  beforeEach(() => {
    document.cookie = "";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "ivac_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
  });

  it("parses a successful JSON response with the provided zod schema", async () => {
    mockFetchOnce({ status: 200, body: { ok: true } });
    const result = await apiRequest("/api/whatever", schema);
    expect(result).toEqual({ ok: true });
  });

  it("throws ApiError with the backend detail message on failure", async () => {
    mockFetchOnce({ status: 403, body: { detail: "Bu işlem için yetkiniz yok" } });
    await expect(apiRequest("/api/whatever", schema)).rejects.toMatchObject({
      status: 403,
      message: "Bu işlem için yetkiniz yok",
    });
  });

  it("marks 401 responses as isUnauthorized", async () => {
    mockFetchOnce({ status: 401, body: { detail: "Oturum geçersiz" } });
    try {
      await apiRequest("/api/whatever", schema);
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).isUnauthorized).toBe(true);
    }
  });

  it("extracts field-level errors from a 422 validation response", async () => {
    mockFetchOnce({
      status: 422,
      body: {
        detail: "İstek doğrulanamadı",
        errors: [{ loc: ["body", "email"], msg: "Geçerli bir e-posta girin", type: "value_error" }],
      },
    });
    try {
      await apiRequest("/api/whatever", schema);
      expect.unreachable();
    } catch (err) {
      expect((err as ApiError).fieldErrors).toEqual({ email: "Geçerli bir e-posta girin" });
    }
  });

  it("sends the X-CSRF-Token header (read from the ivac_csrf cookie) on mutating requests", async () => {
    document.cookie = "ivac_csrf=test-csrf-token";
    mockFetchOnce({ status: 200, body: { ok: true } });
    await apiRequest("/api/whatever", schema, { method: "POST", body: { a: 1 } });
    const call = vi.mocked(fetch).mock.calls[0]!;
    const headers = call[1]?.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("test-csrf-token");
  });

  it("does not send a CSRF header on GET requests", async () => {
    document.cookie = "ivac_csrf=test-csrf-token";
    mockFetchOnce({ status: 200, body: { ok: true } });
    await apiRequest("/api/whatever", schema);
    const call = vi.mocked(fetch).mock.calls[0]!;
    const headers = (call[1]?.headers ?? {}) as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBeUndefined();
  });
});
