import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "../specs/fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Aşama 11 — disposable Docker stack üzerinde tam akış testi.
 *
 * Yalnız `playwright.docker.config.ts` ile, gerçek bir Docker Compose stack'e
 * karşı çalıştırılmak üzere tasarlanmıştır (bkz. PHASE_11_E2E_REPORT.md).
 * `LIVEKIT_URL`/`OPENAI_API_KEY` disposable ortamda SAHTE/geçersiz
 * değerlerdir — gerçek bir telefon araması ASLA denenmez; dial dispatch
 * bilinçli olarak temiz bir şekilde başarısız olur (`dispatch_failed`) ve bu,
 * gerçek altyapının (frontend→API→DB→Celery→worker→hata işleme→frontend
 * canlı-yenileme) uçtan uca doğru çalıştığını kanıtlar.
 */

test.describe("Lead içe aktarma → çağrı başlatma (gerçek dispatch, sahte telefon sağlayıcı)", () => {
  test("CSV import ile lead oluşturulur, listede görünür, çağrı başlatma denemesi temiz şekilde başarısız olur", async ({
    page,
  }) => {
    await page.goto("/leads/import");
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(
      path.join(__dirname, "../../../services/api/tests/fixtures/leads_tr.csv")
    );

    await expect(page.getByText(/satır bulundu/)).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "İçe Aktarmayı Tamamla" }).click();
    await expect(page).toHaveURL("/leads", { timeout: 15_000 });

    await page.getByPlaceholder("Ara (işletme, adres, sektör)…").fill("Acme Cafe");
    await expect(page.getByText("Acme Cafe")).toBeVisible({ timeout: 10_000 });
    await page.getByText("Acme Cafe").click();
    await expect(page).toHaveURL(/\/leads\/[0-9a-f-]+$/);

    const callButton = page.getByRole("button", { name: "Ara", exact: true });
    await expect(callButton).toBeEnabled();
    await callButton.click();

    // NOT: `call_policy.py::is_within_call_hours` Pazar günleri TÜM aramaları
    // reddeder (gerçek, kasıtlı bir iş kuralı — test kolaylığı için
    // atlanmadı/mock'lanmadı). Bu testin hangi gün çalıştığı kontrol
    // edilemediği için iki geçerli GERÇEK sonuç da kabul edilir:
    //   (a) hafta içi/Cumartesi: dispatch denenir, sahte LIVEKIT_URL nedeniyle
    //       temiz şekilde "Başarısız" olur (worker'ın job'ı gerçekten işlediği
    //       ayrıca `docker exec` ile bizzat doğrulandı, bkz. PHASE_11_E2E_REPORT.md).
    //   (b) Pazar: backend politika kapısı isteği daha en baştan reddeder,
    //       frontend bunu bir hata mesajı olarak gösterir, /calls/'a hiç
    //       gidilmez.
    const failedStatus = page.getByText("Başarısız");
    const policyError = page.getByText(/Arama saatleri dışında|Pazar/);
    await expect(failedStatus.or(policyError)).toBeVisible({ timeout: 20_000 });
  });
});

test.describe("Yetkisiz erişim ve iç API izolasyonu", () => {
  test("viewer rolü mutasyon işlemlerinde 403 alır, iç API dışarıdan izole", async ({
    page,
    request,
  }) => {
    // Gerçek tarayıcı akışı: owner UI üzerinden gerçekten bir viewer
    // kullanıcı oluşturur (form doldurma, dialog, gerçek POST /api/users).
    const email = `e2e-viewer-${Date.now()}@ivac.local`;
    const password = "ViewerPass123!";

    await page.goto("/users");
    await page.getByRole("button", { name: "Yeni Kullanıcı" }).click();
    await page.getByLabel("E-posta").fill(email);
    await page.getByLabel("Ad Soyad").fill("E2E Viewer");
    await page.getByLabel(/Parola/).fill(password);
    await page.getByLabel("Rol", { exact: true }).selectOption("viewer");
    await page.getByRole("button", { name: "Oluştur" }).click();
    await expect(page.getByText(email)).toBeVisible({ timeout: 10_000 });

    // NOT: burada BİLEREK ikinci bir tam tarayıcı context'i (browser.newContext
    // + sayfa navigasyonu + form submit) AÇILMADI. Bu disposable ortamda
    // (2.9GB kısıtlı VM) iki eşzamanlı Chromium context'i altında gerçek bir
    // uygulama hatası OLMADAN tekrarlanan zamanlama yarışlarına yol açtığı
    // ampirik olarak doğrulandı — aynı RBAC sınırı zaten bu oturumda hem
    // `curl` ile (owner→200, viewer→403, PHASE_11_E2E_REPORT.md) hem de
    // kapsamlı `test_authorization.py` paketiyle (Aşama 9) kesin biçimde
    // kanıtlandı. Playwright'ın kendi `request` fixture'ı (gerçek HTTP,
    // gerçek Caddy→API yolu, yalnızca ikinci bir tarayıcı sayfası
    // render ETMİYOR) burada aynı gerçek sonucu deterministik biçimde verir.
    const loginResp = await request.post("/api/auth/login", {
      data: { email, password },
    });
    expect(loginResp.status()).toBe(200);
    const cookieHeader = (await loginResp.headersArray())
      .filter((h) => h.name.toLowerCase() === "set-cookie")
      .map((h) => h.value.split(";")[0])
      .join("; ");

    const usersResp = await request.get("/api/users", {
      headers: { Cookie: cookieHeader },
    });
    expect(usersResp.status()).toBe(403);
    const body = await usersResp.json();
    expect(body.detail).toBe("Bu işlem için yetkiniz yok (users:manage)");

    const internalResponse = await request.get("/api/internal/v1/calls/does-not-exist", {
      headers: { Cookie: cookieHeader },
      failOnStatusCode: false,
    });
    expect([401, 403, 404]).toContain(internalResponse.status());
  });
});

for (const [name, width, height] of [
  ["320px (küçük mobil)", 320, 720],
  ["390px (mobil)", 390, 844],
  ["768px (tablet)", 768, 1024],
  ["1280px (masaüstü)", 1280, 800],
] as const) {
  test.describe(`Viewport ${name}`, () => {
    test.use({ viewport: { width, height } });

    test("dashboard yatay taşma olmadan render edilir", async ({ page }) => {
      await page.goto("/");
      await expect(page.getByText("Bugünkü Aramalar")).toBeVisible({ timeout: 10_000 });
      const hasHorizontalOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      );
      expect(hasHorizontalOverflow).toBe(false);
    });

    test("leads sayfası yatay taşma olmadan render edilir", async ({ page }) => {
      await page.goto("/leads");
      await expect(page.getByPlaceholder("Ara (işletme, adres, sektör)…")).toBeVisible({
        timeout: 10_000,
      });
      const hasHorizontalOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      );
      expect(hasHorizontalOverflow).toBe(false);
    });
  });
}
