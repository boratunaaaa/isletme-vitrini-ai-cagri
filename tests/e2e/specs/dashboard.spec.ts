import { test, expect } from "./fixtures";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("gerçek backend'den gelen özet metrikleri gösterir", async ({ page }) => {
    await expect(page.getByText("Bugünkü Aramalar")).toBeVisible();
    await expect(page.getByText("Entegrasyon Durumu")).toBeVisible();
    // Backend integration_status() 5 sağlayıcı döner (openai/livekit/netgsm/sip_trunk/google_places).
    await expect(page.getByText("OpenAI Realtime")).toBeVisible();
    await expect(page.getByText("Netgsm SIP")).toBeVisible();
  });

  test("konsolda beklenmeyen bir hata/uyarı olmadan yüklenir", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.reload();
    await expect(page.getByText("Bugünkü Aramalar")).toBeVisible();
    expect(errors).toEqual([]);
  });
});
