import { test, expect, login, OWNER_EMAIL, OWNER_PASSWORD } from "./fixtures";

// Bu dosyadaki testler bilinçli olarak paylaşılan owner storageState'ini KULLANMAZ —
// kimlik doğrulama akışının kendisini (giriş yapmamış/yanlış parola/doğru parola/çıkış)
// test eder. Toplamda en fazla 3 gerçek login POST'u atar (backend rate limiti
// (ip,email) başına 60s'de 5 — bkz. global-setup.ts'deki not).
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("Kimlik doğrulama", () => {
  test("oturumsuz kullanıcı korumalı bir sayfaya gidince /login'e yönlendirilir", async ({ page }) => {
    await page.goto("/leads");
    await expect(page).toHaveURL(/\/login/);
  });

  test("yanlış parola ile giriş başarısız olur ve backend hata mesajı gösterilir", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("E-posta").fill(OWNER_EMAIL);
    await page.getByLabel("Parola").fill("wrong-password-123");
    await page.getByRole("button", { name: "Giriş Yap" }).click();
    await expect(page.getByText("E-posta veya parola hatalı")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("doğru kimlik bilgileriyle giriş yapılır ve dashboard'a yönlendirilir", async ({ page }) => {
    await login(page, OWNER_EMAIL, OWNER_PASSWORD);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("çıkış yapınca oturum sonlanır ve korumalı sayfa tekrar /login'e döner", async ({ page }) => {
    await login(page);
    await page.getByRole("button", { name: "Çıkış yap" }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
    await page.goto("/leads");
    await expect(page).toHaveURL(/\/login/);
  });
});
