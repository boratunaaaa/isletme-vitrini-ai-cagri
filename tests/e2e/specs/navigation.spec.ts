import { test, expect } from "./fixtures";

test.describe("Gezinme", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("kenar çubuğundan Lead'ler sayfasına gidilebilir ve gerçek liste yüklenir", async ({ page }) => {
    await page.getByRole("link", { name: "Lead'ler" }).click();
    await expect(page).toHaveURL("/leads");
    await expect(page.getByPlaceholder("Ara (işletme, adres, sektör)…")).toBeVisible();
  });

  test("Kampanyalar sayfası açılır", async ({ page }) => {
    await page.getByRole("link", { name: "Kampanyalar" }).click();
    await expect(page).toHaveURL("/campaigns");
    await expect(page.getByRole("heading", { name: "Kampanyalar" })).toBeVisible();
  });

  test("Canlı Aramalar sayfası açılır ve boş durumu doğru gösterir", async ({ page }) => {
    await page.getByRole("link", { name: "Canlı Aramalar" }).click();
    await expect(page).toHaveURL("/calls/live");
    await expect(page.getByText("Şu anda aktif arama yok")).toBeVisible({ timeout: 10_000 });
  });

  test("Kullanıcılar sayfası owner rolü için görünür ve erişilebilir", async ({ page }) => {
    await page.getByRole("link", { name: "Kullanıcılar" }).click();
    await expect(page).toHaveURL("/users");
    await expect(page.getByRole("heading", { name: "Kullanıcılar" })).toBeVisible();
  });
});

test.describe("Mobil kenar çubuğu (375px)", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("hamburger menü kenar çubuğunu açar/kapatır", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Lead'ler" })).toBeHidden();
    await page.getByRole("button", { name: "Menüyü aç" }).click();
    await expect(page.getByRole("link", { name: "Lead'ler" })).toBeVisible();
    await page.getByRole("button", { name: "Menüyü kapat" }).click();
    await expect(page.getByRole("link", { name: "Lead'ler" })).toBeHidden();
  });
});
