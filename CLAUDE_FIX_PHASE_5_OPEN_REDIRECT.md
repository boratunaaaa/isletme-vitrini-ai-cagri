# CLAUDE_FIX_PHASE_5_OPEN_REDIRECT.md

## 1. Yönetici Özeti

`CODEX_FINAL_AUDIT_PHASE_5_FRONTEND.md`'nin tek YÜKSEK bulgusu —
`getSafeRedirectPath()`'in slash+backslash (`"/\evil.example"`) open-redirect
varyantını kabul etmesi — kök nedeniyle doğrulanıp kapatıldı. Bu oturumda
**yalnız** redirect helper'ı, doğrudan kullanım noktaları, testler ve ilgili
dokümantasyon değiştirildi; backend'e, voice-agent'a veya stale-cookie
düzeltmesinin kendisine dokunulmadı. Helper artık salt string-prefix
kontrolüne değil, WHATWG `URL` ile canonical çözümleme + origin-eşitliği
doğrulamasına dayanıyor. 16 Vitest + 3 yeni Playwright testi eklendi
(toplam Vitest 33/33, Playwright 23/23), hepsi geçiyor.

## 2. Codex Yüksek Bulgusu

`CODEX_FINAL_AUDIT_PHASE_5_FRONTEND.md` §14, YÜKSEK-1:
`apps/web/lib/auth/safe-redirect.ts:13-16` yalnız `startsWith("/")` /
`startsWith("//")` / `includes("://")` kontrolü yapıyordu. Codex'in kanıtı:

```js
new URL('/\\evil.com', 'http://localhost:3000').href
// => "http://evil.com/"
```

`"/\evil.com"` bu üç kontrolün HİÇBİRİNİ tetiklemiyordu (tek `/` ile
başlıyor, `//` ile başlamıyor, `://` içermiyor) — ama WHATWG URL
çözümleyicisi ters eğik çizgiyi düz eğik çizgiyle eşdeğer sayıp bunu harici
bir host'a çözümlüyordu. Sonuç kararı: `KÜÇÜK DÜZELTMELERDEN SONRA COMMIT
EDİLEBİLİR` — bu tek bulgu commit'i engelliyordu.

## 3. Kök Neden

Doğrulama (varsayılmadan, gerçekten çalıştırılarak) — eski implementasyon:

```ts
if (!next.startsWith("/") || next.startsWith("//") || next.includes("://")) {
  return "/";
}
return next;
```

Bu, açık redirect korumasını yalnız ÜÇ string prefix kalıbına indirgiyordu.
Tarayıcı/URL çözümleme kuralları bundan çok daha zengin (backslash-slash
eşdeğerliği, percent-encoding, çift encoding) olduğu için salt prefix
kontrolü yapısal olarak yetersizdi — bir "izin listesi" (allowlist)
yaklaşımı yerine "yasak listesi" (denylist) yaklaşımı kullanılmıştı ve
denylist eksiksiz değildi.

## 4. Safe Redirect Algoritması

Yeni `apps/web/lib/auth/safe-redirect.ts` kullanıcının belirttiği 12 adımlı
algoritmayı birebir uyguluyor:

1. `typeof next !== "string"` → fallback (savunmacı: artık parametre tipi
   `unknown`, çağıran taraf yanlışlıkla non-string geçirse bile güvenli).
2. `trim()` sonrası boşsa → fallback.
3-4. Ham (trim edilmiş) değerde kontrol karakteri VEYA ters eğik çizgi varsa → fallback.
5. En fazla 3 tur sınırlı `decodeURIComponent` (bkz. §7).
6. Decode edilmiş değerde de kontrol karakteri/ters eğik çizgi varsa → fallback.
7-8. Decode edilmiş değer tam olarak TEK `/` ile başlamalı, `//` ile başlayamaz.
9-11. Sabit `TRUSTED_ORIGIN = "https://internal.invalid"` ile
   `new URL(decoded, TRUSTED_ORIGIN)` çözümlenir; sonucun `origin`'i
   `TRUSTED_ORIGIN` ile BİREBİR aynı değilse → fallback. Yalnız
   `pathname + search + hash` döndürülür — origin hiçbir zaman dışarı sızmaz.
12. Herhangi bir adımda `URL` constructor'ı hata fırlatırsa → fallback.

`TRUSTED_ORIGIN` yalnız doğrulama amaçlı; kullanıcıya asla dönmez, panelin
gerçek domain'iyle hiçbir ilişkisi yok (bilerek `.invalid` TLD'si — gerçek
bir domain gibi karışmaması için).

## 5. Backslash Koruması

Hem HAM (adım 4) hem DECODE EDİLMİŞ (adım 6) değerde `\` karakteri aranıp
bulunursa anında reddediliyor — `next.includes(BACKSLASH)` (kaynak dosyada
literal kontrol baytı bırakmamak için `String.fromCharCode(92)` ile
tanımlandı, bkz. §16 "kendi hatam" notu). Bu, Codex'in bulduğu asıl açığı
(`"/\evil.example"`) doğrudan kapatıyor: adım 4'te ham değerde backslash
tespit edilip fallback'e düşülüyor, `new URL()` çözümlemesine hiç
ulaşmıyor.

## 6. URL Origin Doğrulaması

Algoritmanın son ve en güçlü katmanı (§4 adım 9-11): decode edilmiş,
backslash'tan arındırılmış, tek-`/`-ile-başlayan değer bile YİNE DE sabit
bir trusted origin'e göre `new URL()` ile çözümlenip **origin eşitliği**
kanıtlanmadan kabul edilmiyor. Bu, önceden öngörülmemiş herhangi bir
bypass sınıfı (ör. WHATWG parser'ının gelecekte/farklı ortamlarda farklı
yorumlayabileceği edge-case karakterler) için de bir güvenlik ağıdır —
yalnız enumere edilen kalıplara değil, "sonuçta gerçekten aynı origin'e mi
çözümleniyor" sorusuna dayanır.

## 7. Encoded Varyant Koruması

`safeDecode()` en fazla 3 tur `decodeURIComponent` uygulayıp değer
DEĞİŞMEMEYE başladığında (idempotent) erken durur — sınırsız/sonsuz decode
döngüsü riski yok. Bu, çift-encode edilmiş bypass girişimlerini
(`%252F%252F...` → 1. tur `%2F%2F...` → 2. tur `//...` → reddedilir)
yakalıyor. `decodeURIComponent` throw ederse (malformed percent-encoding,
ör. `/%zz`) `safeDecode` `null` döner ve çağıran bunu doğrudan reddetme
sinyali sayar — kısmi/ham decode edilmiş bir değer ASLA "güvenli" kabul
edilmiyor.

Test edilen encoded varyantlar (§9): `%5C` (backslash), `%5c%5c`,
`%2F`, `%2F%2F`, baştan `%2F%2F` (raw `/` olmadan), çift-encode `%255C` ve
`%252F%252F`, ayrıca encode edilmiş kontrol karakterleri (`%0D%0A`, `%00`).

## 8. Kullanım Noktalarının Kontrolü

`grep -rn "getSafeRedirectPath"` ile helper'ın TÜM kullanım noktaları
tarandı: yalnız `apps/web/app/login/page.tsx` içinde, iki yerde
(`onSubmit` başarı yolu + "zaten oturumu var" `useEffect`'i) — ikisi de
`getSafeRedirectPath(searchParams.get("next"))` şeklinde, doğrudan helper
üzerinden geçiyor. Ayrıca uygulama genelinde `router.push`/`router.replace`/
`redirect(`/`window.location`/`location.href` kalıpları taranarak hiçbir
başka yerde ham `next`/`redirect`/`returnTo` değerinin doğrudan
navigasyona verilmediği doğrulandı — diğer tüm `router.push`/`replace`
çağrıları ya sabit string'ler (`"/login"`) ya da backend'den gelen kendi
entity ID'leriyle (`/leads/${row.id}` gibi, kullanıcı query param'ından
DEĞİL) oluşturulan dahili path'ler. Middleware'in `next` param'ı da
`request.nextUrl.pathname`'den (Next'in kendi URL ayrıştırması, harici
olamaz) üretiliyor, kullanıcı girdisi değil.

## 9. Vitest Testleri

`apps/web/lib/auth/safe-redirect.test.ts` — **16 test**, kullanıcının
istediği tüm gruplar dahil:

- Kabul edilenler: `/dashboard`, `/leads/123`, query+hash korunumu.
- Harici URL: `https://...`, `http://...`, `//...`, `///...`.
- **Slash+backslash (asıl bulunan açık)**: `/\evil.example`,
  `/\\evil.example`, `\evil.example`, `/foo\bar`.
- Encoded varyantlar: tek-encode (`%5C`, `%5c%5c`, `%2F`, `%2F%2F`) ve
  çift-encode (`%255C`, `%252F%252F`).
- Şema varyantları: `javascript:`, `data:`, `mailto:`.
- Hatalı girdi: boş/whitespace/`null`/`undefined`/non-string
  (`42`, `{}`, `["/leads"]`), malformed percent-encoding (`/%zz`, `/%`),
  CR/LF/boşluk/tab kontrol karakterleri (ham VE encoded), leading
  whitespace ile gizlenmiş harici URL.
- Yanlış-pozitif kontrolü: `/@evil.example` gibi "host benzeri ama aslında
  zararsız aynı-origin path" değerlerinin YANLIŞLIKLA reddedilmediği
  doğrulandı (algoritmanın aşırı agresif olmadığını kanıtlıyor).

Algoritma ayrıca uygulanmadan önce bağımsız bir Node script'iyle 32 test
vakası üzerinde manuel doğrulandı (dosyaya yazılmadan önce) — hepsi
beklenen sonucu verdi.

## 10. Playwright Testi

`tests/e2e/specs/auth-redirect.spec.ts`'e 3 yeni test eklendi (10d/10e/10f),
gerçek production login sayfası + `getSafeRedirectPath()` yolunu kullanarak,
kullanıcının istediği üç spesifik varyantı doğruluyor:

- `10d`: `/login?next=%2F%5Cevil.example` (encoded slash+backslash — asıl
  bulunan açığın tarayıcıda gerçek kanıtı) → `/`'e düşer.
- `10e`: `/login?next=%2F%2Fevil.example` (encoded protokol-göreli) → `/`'e düşer.
- `10f`: `/login?next=https%3A%2F%2Fevil.example` (tam encoded harici URL) → `/`'e düşer.

Üçü de mevcut `OWNER_STORAGE_STATE` paylaşılan oturumunu kullanıyor —
**sıfır** ek gerçek `POST /api/auth/login` çağrısı (rate limiter'a
dokunulmadı, mevcut authentication/rate-limit yaklaşımı bozulmadı).

## 11. Lint Sonucu

`apps/web`: **temiz** (0 hata, 0 uyarı). Kök `pnpm lint` (turbo): temiz.

## 12. Typecheck Sonucu

`apps/web`: **temiz** (strict + `noUncheckedIndexedAccess`). Kök `pnpm
typecheck` (turbo): temiz.

## 13. Unit Test Sonucu

`apps/web`: **33/33 passed** (5 dosya) — önceki 22 + yeni/genişletilmiş
`safe-redirect.test.ts`'in 5→16 testi (+11 net yeni test).

## 14. Build Sonucu

`apps/web`: **başarılı**, 19 route (+ `/_not-found`) derlendi. Kök `pnpm
build` (turbo): başarılı.

## 15. E2E Sonucu

Backend + Postgres + Redis + Next.js dev sunucusu bu oturumda gerçekten
ayağa kaldırıldı. `cd apps/web && pnpm exec playwright test --list` →
**23 test, 4 dosya**, sıfır Vitest dosyası karışması. `pnpm test:e2e` →
**23/23 passed** (1.2 dakika).

Not (şeffaflık için raporlanıyor, bir güvenlik bulgusu DEĞİL): İlk deneme,
backend+frontend dev sunucuları saniyeler içinde art arda yeniden
başlatıldıktan hemen sonra çalıştırıldığında, `global-setup.ts`'nin ilk
`/login`→dashboard yönlendirme beklemesi 30 saniyelik timeout'u aştı
(Next.js dev modunun `(app)` route group'unu — Radix/TanStack/Recharts
dahil ~874 modül — ilk kez derlerken kaynak rekabeti altında beklenenden
uzun sürmesi). `globalSetup`'ın kendi hata mesajı beklendiği gibi AÇIK ve
anlaşılır bir hata üretti (sahte geçiş YOKTU). Ayrı bir debug script'iyle
GERÇEK login+redirect akışının (yeni `getSafeRedirectPath()` dahil) doğru
çalıştığı doğrulandı; sunucular ısındıktan sonra tam suite tekrar
çalıştırıldı ve **23/23 geçti**. Bu, `global-setup.ts`'nin kendisiyle
ilgili bir gözlemdir (o dosya önceki fazda değiştirilmişti, bu oturumun
kapsamı DIŞINDA — dokunulmadı) ve open-redirect düzeltmesinde bir
regresyon OLMADIĞINI kanıtlar.

## 16. Değiştirilen Dosyalar

- `apps/web/lib/auth/safe-redirect.ts` — algoritma tamamen yeniden yazıldı (§4-7).
  - **Not (kendi hatam, hemen düzeltildi)**: İlk taslakta kontrol karakteri
    regex'i (`/[ -]/`) dosyaya YAZILIRKEN kaçış dizisi
    yerine HAM, görünmez kontrol baytları (gerçek NUL/0x1F/DEL baytları)
    olarak diske yazıldığı fark edildi (hex dump ile doğrulandı). Kaynak
    dosyada okunaksız/görünmez baytlar bırakmamak için bu, karakter kodu
    karşılaştırmasına (`charCodeAt` döngüsü) çevrilerek düzeltildi —
    fonksiyonel davranış aynı, ama artık dosya saf yazdırılabilir ASCII/UTF-8
    metin. Production'a hiç gitmedi (aynı turda, ilk yazımdan hemen sonra
    fark edilip düzeltildi).
- `apps/web/lib/auth/safe-redirect.test.ts` — 16 test (5'ten genişletildi).
- `tests/e2e/specs/auth-redirect.spec.ts` — 3 yeni test (10d/10e/10f).
- Kullanım noktaları (`apps/web/app/login/page.tsx`): **değiştirilmedi** —
  zaten helper üzerinden geçiyordu, doğrulaması yapıldı (§8).

## 17. Kalan Kritik Bulgular

Yok.

## 18. Kalan Yüksek Bulgular

Yok. (Codex'in tek YÜKSEK bulgusu bu oturumda kapatıldı.)

## 19. Commit Hazırlık Kararı

`FRONTEND COMMIT İÇİN HAZIR`.

## 20. Git Durumu

Commit YAPILMADI, push YAPILMADI. Çıktılar bu raporun sonunda, sohbet
mesajında ayrıca verilecek.

---

## Sonuç Kararı

**`FRONTEND COMMIT İÇİN HAZIR`**

Gerekçe: `getSafeRedirectPath()` artık `/\evil.example` ve tüm encoded
backslash/slash varyantlarını reddediyor (kanıt: §9-10, hem birim hem
uçtan-uca test). Harici URL'ler her durumda güvenli `/` fallback'ine
düşüyor. Güvenli dahili path'ler (`/leads/123?tab=calls#x` gibi
query+hash dahil) çalışmaya devam ediyor. Helper'ın tüm login-redirect
kullanım noktaları doğrulandı — hiçbiri ham değeri atlamıyor. Vitest
(33/33), lint, typecheck, build hepsi temiz. E2E gerçekten çalıştırılıp
23/23 geçti. Yeni kritik veya yüksek bulgu yok. Backend değiştirilmedi.
Commit veya push yapılmadı.
