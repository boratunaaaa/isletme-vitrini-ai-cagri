import { chromium, expect, type FullConfig } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "owner@ivac.local";
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "DevOwnerPass123!";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const STORAGE_STATE_DIR = path.join(__dirname, ".auth");
export const OWNER_STORAGE_STATE = path.join(STORAGE_STATE_DIR, "owner.json");

/**
 * Backend `/api/auth/login`'i (ip, email) başına 60 saniyede 5 deneme ile
 * sınırlar (app/core/ratelimit.py::check_rate_limit — gerçek bir güvenlik
 * kontrolü, test kolaylığı için gevşetilmedi). Her testin kendi `beforeEach`
 * içinde UI üzerinden giriş yapması bu limiti hızla aşar. Bunun yerine TEK
 * seferlik gerçek bir UI girişi yapılır ve oturum çerezleri diskte saklanıp
 * ihtiyaç duyan testlere `storageState` ile enjekte edilir.
 */
export default async function globalSetup(config: FullConfig) {
  fs.mkdirSync(STORAGE_STATE_DIR, { recursive: true });
  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:3000";

  // CODEX_AUDIT_PHASE_5_FRONTEND.md: backend ayakta değilken E2E'nin "/login"
  // üzerinde takılıp anlaşılmaz biçimde timeout ile başarısız olması yerine,
  // burada erkenden AÇIK ve anlaşılır bir hata üretiyoruz. Bu backend'i
  // otomatik BAŞLATMAZ (README/docs'ta belirtilen ön koşullar elle
  // sağlanmalı) — yalnız hazır olup olmadığını kontrol eder.
  try {
    const response = await fetch(`${API_URL}/ready`, { signal: AbortSignal.timeout(3_000) });
    if (!response.ok) {
      throw new Error(`Backend /ready ${response.status} döndü`);
    }
    const body = (await response.json()) as { checks?: Record<string, string> };
    const notOk = Object.entries(body.checks ?? {}).filter(([, v]) => v !== "ok");
    if (notOk.length > 0) {
      throw new Error(`Backend hazır değil: ${JSON.stringify(body.checks)}`);
    }
  } catch (err) {
    throw new Error(
      `E2E backend ön koşulu sağlanmadı — ${API_URL} adresinde çalışan, veritabanı+Redis'i hazır bir ` +
        `backend bulunamadı (${err instanceof Error ? err.message : String(err)}).\n` +
        "Önce şunları çalıştırın:\n" +
        "  1) docker compose -f docker-compose.dev.yml up -d\n" +
        "  2) cd services/api && uv run alembic upgrade head && uv run python -m app.seed\n" +
        "  3) BOOTSTRAP_ADMIN_EMAIL=... BOOTSTRAP_ADMIN_PASSWORD=... uv run python -m app.bootstrap\n" +
        "  4) cd services/api && uv run uvicorn app.main:app --port 8000\n" +
        "Ardından E2E_OWNER_EMAIL/E2E_OWNER_PASSWORD ile bu paketi tekrar çalıştırın."
    );
  }

  const browser = await chromium.launch();
  const page = await browser.newPage();
  // İlk istek Next.js dev sunucusunun /login rotasını sıfırdan derlemesini
  // tetikleyebilir (birkaç saniye sürebilir) — bu yüzden cömert bir timeout.
  await page.goto(`${baseURL}/login`, { timeout: 30_000 });
  await page.getByLabel("E-posta").fill(OWNER_EMAIL);
  await page.getByLabel("Parola").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Giriş Yap" }).click();
  try {
    await expect(page).toHaveURL(`${baseURL}/`, { timeout: 30_000 });
  } catch (err) {
    await browser.close();
    throw new Error(
      "E2E global-setup: giriş sonrası dashboard'a yönlendirme gerçekleşmedi. " +
        `Son URL: ${page.url()}. Bootstrap owner kimlik bilgileri ` +
        "(E2E_OWNER_EMAIL/E2E_OWNER_PASSWORD) backend'de gerçekten var mı ve doğru mu kontrol edin. " +
        `Orijinal hata: ${err instanceof Error ? err.message : String(err)}`
    );
  }
  await page.context().storageState({ path: OWNER_STORAGE_STATE });
  await browser.close();
}
