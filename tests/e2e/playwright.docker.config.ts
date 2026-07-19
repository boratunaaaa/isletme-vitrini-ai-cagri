import { defineConfig, devices } from "@playwright/test";

/**
 * Aşama 11 — disposable Docker E2E için ayrık konfigürasyon.
 *
 * `playwright.config.ts`'ten farkı: kendi bir `webServer` BAŞLATMAZ (frontend
 * zaten `docker compose -p ivac-e2e ... up -d` ile ayakta) ve `baseURL`
 * yerel Caddy'nin düz-HTTP portuna (8080, `deploy/caddy/Caddyfile.local`)
 * işaret eder. Aynı `global-setup.ts` ve `./specs` dizini (auth/dashboard/
 * navigation) yeniden kullanılır — yalnız gerçek bir çalışma ortamına karşı
 * çalıştırılır, mock YOKTUR.
 */
export default defineConfig({
  testDir: ".",
  // `auth-redirect.spec.ts` bilerek hariç tutuldu — `http://localhost:3000`
  // portunu sabit kodluyor (yerel dev config'e özel); Docker stack farklı
  // bir porttan (8080) sunulur.
  testMatch: [
    "specs/auth.spec.ts",
    "specs/dashboard.spec.ts",
    "specs/navigation.spec.ts",
    "specs-docker/**/*.spec.ts",
  ],
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  globalSetup: "./global-setup.ts",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
