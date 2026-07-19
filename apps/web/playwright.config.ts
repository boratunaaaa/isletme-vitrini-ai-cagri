import path from "node:path";
import { fileURLToPath } from "node:url";
import baseConfig from "../../tests/e2e/playwright.config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const e2eRoot = path.resolve(__dirname, "../../tests/e2e");

/**
 * CODEX_AUDIT_PHASE_5_FRONTEND.md — Playwright test discovery sorunu.
 *
 * `apps/web` E2E testlerinin SAHİBİ DEĞİLDİR — bunlar `tests/e2e` (`@ivac/e2e`
 * paketi) altında yaşar (bkz. o dizindeki `playwright.config.ts`). Önceden
 * `apps/web`'de HİÇBİR Playwright config'i yoktu; `cd apps/web && pnpm exec
 * playwright test` çalıştırıldığında Playwright config'i cwd'de (apps/web)
 * arar, bulamayınca varsayılan geniş `testDir`/`testMatch`'e düşer ve
 * `apps/web/**\/*.test.{ts,tsx}` (Vitest birim testleri!) dosyalarını E2E
 * testi sanıp yüklemeye çalışırdı — "Vitest failed to access its internal
 * state" hatasıyla çöküyordu.
 *
 * Bu dosya gerçek config'i (`tests/e2e/playwright.config.ts`) SAF VERİ olarak
 * import eder (yalnız bir JS objesi — `@playwright/test`'i BURADAN import
 * ETMİYORUZ, o yüzden `apps/web`'e yeni bir bağımlılık eklenmedi; nested
 * import Node çözümlemesiyle `tests/e2e`'nin kendi `node_modules`'ından
 * çözülür) ve yalnız üç YOL-DUYARLI alanı (`testDir`, `globalSetup`,
 * `webServer.cwd`) bu dosyanın kendi konumuna göre MUTLAK yola çevirir —
 * `use`/`reporter`/`projects`/`retries` gibi diğer TÜM ayarlar TEK kaynaktan
 * (`tests/e2e/playwright.config.ts`) gelir, burada tekrarlanmaz/kopyalanmaz.
 *
 * Sonuç: `apps/web` içinden çalıştırılan Playwright artık YALNIZ gerçek E2E
 * spec'lerini (`tests/e2e/specs/*.spec.ts`) görür; Vitest `*.test.ts(x)`
 * dosyaları `testDir` bu dizinin tamamen dışına işaret ettiği için hiç
 * taranmaz bile (testIgnore'a gerek kalmadan yapısal olarak imkânsız).
 *
 * NOT (PRODUCTION_INFRA_REPORT.md): Bu dosya `apps/web/tsconfig.json`'un
 * `exclude` listesinde — `../../tests/e2e/playwright.config` importu
 * `apps/web` dizini DIŞINA çıkıyor; production Docker build context'i
 * yalnız `apps/web/`'i içerdiği için (`tests/e2e/` orada YOK) `next build`
 * bu dosyayı typecheck etmeye çalışırsa "Cannot find module" ile GERÇEKTEN
 * başarısız oluyordu (build sırasında ampirik olarak doğrulandı). Bu
 * dosyanın doğruluğu `pnpm exec playwright test --list`/`test:e2e` ile ayrı
 * doğrulanır — Playwright kendi TS dönüşümünü kullanır, `tsc`'ye ihtiyaç
 * duymaz.
 */
const config = {
  ...baseConfig,
  testDir: path.join(e2eRoot, "specs"),
  globalSetup: path.join(e2eRoot, "global-setup.ts"),
  outputDir: path.join(e2eRoot, "test-results"),
  webServer: {
    ...baseConfig.webServer,
    cwd: path.resolve(__dirname, "../.."),
  },
};

export default config;
