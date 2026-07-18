import { defineConfig, devices } from "@playwright/test";

/**
 * Bu paket gerçek bir backend + Postgres + Redis bekler (mock kullanılmaz).
 * Beklenen ön koşullar (README.md'de belgelenmiştir):
 *   1. `docker compose -f docker-compose.dev.yml up -d` (Postgres + Redis)
 *   2. `cd services/api && uv run alembic upgrade head && uv run python -m app.seed`
 *   3. `BOOTSTRAP_ADMIN_EMAIL=... BOOTSTRAP_ADMIN_PASSWORD=... uv run python -m app.bootstrap`
 *   4. `cd services/api && uv run uvicorn app.main:app --port 8000` (ayrı terminal)
 *   5. `E2E_OWNER_EMAIL=... E2E_OWNER_PASSWORD=... pnpm --filter @ivac/e2e test`
 *
 * `webServer` yalnız Next.js dev sunucusunu başlatır (backend'i DEĞİL) — backend
 * migration/seed/bootstrap adımları otomatik/güvenli biçimde CI dışında
 * tekrarlanabilir değildir, bu yüzden bilinçli olarak burada başlatılmaz.
 */
export default defineConfig({
  testDir: "./specs",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"]],
  globalSetup: "./global-setup.ts",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm --filter @ivac/web dev -p 3000",
    url: "http://localhost:3000/login",
    reuseExistingServer: true,
    cwd: "../..",
    timeout: 60_000,
  },
});
