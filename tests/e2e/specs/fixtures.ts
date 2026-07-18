import { test as base, expect, type Page } from "@playwright/test";
import { OWNER_STORAGE_STATE } from "../global-setup";

export const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "owner@ivac.local";
export const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "DevOwnerPass123!";

/** Yalnız `global-setup.ts`'nin TEK seferlik gerçek girişinden kalan çerezleri kullanır — yeniden login POST atmaz. */
export const test = base.extend({
  storageState: OWNER_STORAGE_STATE,
});

/** UI üzerinden GERÇEKTEN giriş yapması gereken az sayıdaki test için (rate limit'e dikkat: (ip,email) başına 60s'de 5 deneme). */
export async function login(page: Page, email = OWNER_EMAIL, password = OWNER_PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("E-posta").fill(email);
  await page.getByLabel("Parola").fill(password);
  await page.getByRole("button", { name: "Giriş Yap" }).click();
  await expect(page).toHaveURL("/", { timeout: 15_000 });
}

export { expect };
