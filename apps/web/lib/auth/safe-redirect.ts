/**
 * `/login?next=...` her zaman kullanıcı tarafından değiştirilebilir bir query
 * parametresidir (middleware bunu `pathname`den üretir ama kullanıcı URL'yi
 * elle `/login?next=https://evil.com` olarak da açabilir). Yalnız kök-göreli,
 * uygulama-içi path'lere izin verilir — aksi halde başarılı girişten sonra
 * kullanıcı harici bir siteye yönlendirilebilir (open redirect).
 *
 * DÜZELTME (CODEX_FINAL_AUDIT_PHASE_5_FRONTEND.md YÜKSEK-1): İlk sürüm yalnız
 * `startsWith("/")` / `startsWith("//")` / `includes("://")` gibi string
 * prefix kontrollerine dayanıyordu ve `"/\evil.example"` (slash+backslash)
 * varyantını GEÇİRİYORDU. WHATWG URL çözümleyicileri (ve bazı tarayıcı
 * normalizasyonları) ters eğik çizgiyi düz eğik çizgiyle eşdeğer sayar, yani
 * bu değer harici bir host'a çözümlenebiliyordu.
 *
 * Bu artık iki katmanlı doğrulanıyor: (1) ham VE decode edilmiş değerde ters
 * eğik çizgi/kontrol karakteri erken reddedilir, (2) sonuç HER DURUMDA sabit
 * güvenilir bir origin'e göre `new URL()` ile çözümlenip origin'in
 * DEĞİŞMEDİĞİ kanıtlanmadan asla kabul edilmez — yalnız string prefix
 * kontrolüne güvenilmiyor.
 */

const FALLBACK_PATH = "/";

// Yalnız URL doğrulaması için kullanılan sabit bir origin — kullanıcıya asla
// dönmez, yalnız candidate'in gerçekten AYNI origin'e (host/scheme/port
// değişmeden) çözümlendiğini kanıtlamak için var.
const TRUSTED_ORIGIN = "https://internal.invalid";

// Sınırsız/iç içe decode döngüsüne asla girilmez — en fazla bu kadar tur.
const MAX_DECODE_PASSES = 3;

const BACKSLASH = String.fromCharCode(92);

/**
 * C0 kontrol karakterleri (0x00-0x1F) + DEL (0x7F) içerip içermediğini
 * kontrol eder — CR/LF (header/URL injection, gizlenmiş harici hedef), null
 * byte, tab, vb. Kaynak dosyada okunaksız/görünmez ham baytlar bırakmamak
 * için karakter kodu karşılaştırması kullanılır (regex kaçış dizisi değil).
 */
function hasControlCharacters(value: string): boolean {
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i);
    if (code <= 0x1f || code === 0x7f) return true;
  }
  return false;
}

function isUnsafeRaw(value: string): boolean {
  return hasControlCharacters(value) || value.includes(BACKSLASH);
}

/**
 * Çift/tekrarlı encoding bypass'ına (`%252F%252F...` gibi) karşı en fazla
 * `MAX_DECODE_PASSES` tur `decodeURIComponent` uygular; değer artık
 * değişmiyorsa (idempotent) erken durur. Malformed percent-encoding
 * `decodeURIComponent`'i throw ettirirse `null` döner — çağıran bunu
 * reddetme sinyali olarak kullanır (ham/kısmi decode edilmiş değer asla
 * "güvenli" sayılmaz).
 */
function safeDecode(value: string): string | null {
  let current = value;
  for (let pass = 0; pass < MAX_DECODE_PASSES; pass++) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(current);
    } catch {
      return null;
    }
    if (decoded === current) return decoded;
    current = decoded;
  }
  return current;
}

export function getSafeRedirectPath(next: unknown): string {
  // 1. Değer string değilse fallback.
  if (typeof next !== "string") return FALLBACK_PATH;

  // 2. Trim sonrası boşsa fallback (leading/trailing whitespace ile
  // gizlenmiş harici URL'ler de böylece " https://evil.example" gibi
  // trim sonrası normal 7. adımda yakalanır).
  const trimmed = next.trim();
  if (trimmed.length === 0) return FALLBACK_PATH;

  // 3 + 4. Ham değerde control character veya ters eğik çizgi varsa fallback.
  if (isUnsafeRaw(trimmed)) return FALLBACK_PATH;

  // 5. Percent decoding kontrollü (sınırlı tur) biçimde yapılır; decode
  // hatası (malformed percent-encoding) reddedilir.
  const decoded = safeDecode(trimmed);
  if (decoded === null) return FALLBACK_PATH;

  // 6. Decode edilmiş değerde de control character/ters eğik çizgi varsa
  // fallback (örn. "%5C" -> ters eğik çizgi, "%0A" -> LF).
  if (isUnsafeRaw(decoded)) return FALLBACK_PATH;

  // 7 + 8. Değer tam olarak TEK "/" ile başlamalı; "//" (protokol-göreli)
  // ile başlayan her şey reddedilir.
  if (!decoded.startsWith("/") || decoded.startsWith("//")) return FALLBACK_PATH;

  // 9 + 10 + 11 + 12. Sabit güvenilir bir origin'e göre canonical URL
  // çözümlemesi yapılır. Çözümlenen origin TRUSTED_ORIGIN ile birebir aynı
  // DEĞİLSE (host/scheme/port değişmişse — yani WHATWG parser'ı bunu harici
  // bir hedef olarak yorumladıysa) reddedilir. Yalnız pathname+search+hash
  // döndürülür; origin hiçbir zaman çağırana sızmaz. Parse hatası da güvenli
  // fallback'e düşer.
  try {
    const resolved = new URL(decoded, TRUSTED_ORIGIN);
    if (resolved.origin !== TRUSTED_ORIGIN) return FALLBACK_PATH;
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return FALLBACK_PATH;
  }
}
