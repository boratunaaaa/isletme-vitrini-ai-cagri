import { test, expect, type BrowserContext } from "@playwright/test";
import { OWNER_STORAGE_STATE } from "../global-setup";

/**
 * CODEX_AUDIT_PHASE_5_FRONTEND.md YÜKSEK-1 için regresyon testleri: gerçek
 * production `middleware.ts` + `SessionProvider` + `/login` sayfası yolunu
 * kullanır (mock yok). Bu dosya HİÇBİR gerçek `/api/auth/login` POST'u atmaz
 * (login rate limiter'ı tetiklememek için) — "geçerli oturum" senaryoları
 * `global-setup.ts`'nin TEK gerçek girişinden kalan `storageState`'i, "süresi
 * dolmuş/geçersiz çerez" senaryoları ise backend'in ASLA tanımadığı sahte bir
 * `ivac_session` değerini enjekte eder (Redis'te süresi dolmuş bir çerezle
 * birebir aynı sonucu üretir: middleware çerezi "var" görür, backend
 * `/api/auth/me`'de gerçekten 401 döner).
 */

async function addExpiredSessionCookie(context: BrowserContext) {
  await context.addCookies([
    {
      name: "ivac_session",
      // Backend Redis'te asla karşılığı olmayan, sözdizimsel olarak geçerli
      // görünen bir değer — süresi dolmuş/silinmiş bir Redis anahtarıyla aynı
      // gerçek sonucu (load_session() -> None -> 401) üretir.
      value: "e2e-simulated-expired-session-token",
      domain: "localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

test.describe("Auth redirect — çerez yok", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("1) çerez yok + korumalı route → /login'e yönlendirilir", async ({ page }) => {
    await page.goto("/leads");
    await expect(page).toHaveURL(/\/login\?next=%2Fleads/);
  });

  test("2) çerez yok + /login → login sayfası doğrudan açılır", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveURL("/login");
    await expect(page.getByRole("button", { name: "Giriş Yap" })).toBeVisible();
  });
});

test.describe("Auth redirect — geçerli oturum (paylaşılan storageState, yeni login POST yok)", () => {
  test.use({ storageState: OWNER_STORAGE_STATE });

  test("3) geçerli çerez + korumalı route → sayfa doğrudan açılır", async ({ page }) => {
    await page.goto("/leads");
    await expect(page).toHaveURL("/leads");
    await expect(page.getByPlaceholder("Ara (işletme, adres, sektör)…")).toBeVisible();
  });

  test("4) geçerli çerez + /login → gerçek current-user doğrulamasından SONRA dashboard'a yönlendirilir", async ({
    page,
  }) => {
    await page.goto("/login");
    // Form bir an için render edilebilir (useMe() sonucu gelene kadar) ama
    // en geç birkaç yüz ms içinde gerçek /api/auth/me başarısıyla dashboard'a geçilmeli.
    await expect(page).toHaveURL("/", { timeout: 10_000 });
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("10a) /login?next=https://evil.com (open redirect denemesi) → harici siteye GİTMEZ, güvenli fallback'e döner", async ({
    page,
  }) => {
    await page.goto("/login?next=https%3A%2F%2Fevil.com");
    await expect(page).toHaveURL("http://localhost:3000/", { timeout: 10_000 });
  });

  test("10b) /login?next=//evil.com (protokol-göreli open redirect denemesi) → güvenli fallback'e döner", async ({
    page,
  }) => {
    await page.goto("/login?next=%2F%2Fevil.com");
    await expect(page).toHaveURL("http://localhost:3000/", { timeout: 10_000 });
  });

  test("10c) /login?next=/campaigns (güvenli, uygulama-içi path) → o path'e yönlendirilir", async ({ page }) => {
    await page.goto("/login?next=%2Fcampaigns");
    await expect(page).toHaveURL("http://localhost:3000/campaigns", { timeout: 10_000 });
  });

  test("10d) /login?next=/\\evil.example (slash+backslash open redirect — CODEX_FINAL_AUDIT_PHASE_5_FRONTEND.md YÜKSEK-1) → harici siteye GİTMEZ, güvenli fallback'e döner", async ({
    page,
  }) => {
    // new URL("/\\evil.example", origin) WHATWG kurallarıyla harici host'a
    // çözümlenebiliyordu — bu, gerçek düzeltmeden sonraki tarayıcı akışında
    // asıl bulunan açığı kanıtlayan regresyon testidir.
    await page.goto("/login?next=%2F%5Cevil.example");
    await expect(page).toHaveURL("http://localhost:3000/", { timeout: 10_000 });
  });

  test("10e) /login?next=%2F%2Fevil.example (encoded protokol-göreli) → güvenli fallback'e döner", async ({
    page,
  }) => {
    await page.goto("/login?next=%2F%2Fevil.example");
    await expect(page).toHaveURL("http://localhost:3000/", { timeout: 10_000 });
  });

  test("10f) /login?next=https%3A%2F%2Fevil.example (tam encoded harici URL) → güvenli fallback'e döner", async ({
    page,
  }) => {
    await page.goto("/login?next=https%3A%2F%2Fevil.example");
    await expect(page).toHaveURL("http://localhost:3000/", { timeout: 10_000 });
  });
});

test.describe("Auth redirect — süresi dolmuş/geçersiz çerez (redirect loop regresyonu)", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("5) geçersiz çerez + /login → login sayfası açılır, DÖNGÜ OLMAZ", async ({ page, context }) => {
    await addExpiredSessionCookie(context);
    await page.goto("/login");
    await expect(page).toHaveURL("/login");
    await expect(page.getByRole("button", { name: "Giriş Yap" })).toBeVisible();
    // 7) current-user 401 + zaten /login üzerinde → yeni redirect tetiklenmez:
    // birkaç yüz ms bekleyip hâlâ /login'de olduğumuzu (başka bir URL'e
    // sıçramadığımızı) doğruluyoruz — asıl redirect-loop regresyon kanıtı budur.
    await page.waitForTimeout(1500);
    await expect(page).toHaveURL("/login");
    await expect(page.getByRole("button", { name: "Giriş Yap" })).toBeVisible();
  });

  test("6) geçersiz çerez + korumalı route → BİR KEZ /login'e gider ve orada kalır", async ({ page, context }) => {
    await addExpiredSessionCookie(context);
    await page.goto("/leads");
    await expect(page).toHaveURL("/login");
    await page.waitForTimeout(1500);
    // Döngü varsa bu noktada "/" ile "/login" arasında sıçrıyor olurdu;
    // burada hâlâ /login'de ve form görünür olmalı.
    await expect(page).toHaveURL("/login");
    await expect(page.getByRole("button", { name: "Giriş Yap" })).toBeVisible();
  });
});
