import { NextResponse, type NextRequest } from "next/server";

/**
 * Yalnız hızlı bir yönlendirme optimizasyonudur — GERÇEK yetkilendirme her
 * zaman backend'de (`app/deps.py::get_current_user` / `require_permission`)
 * yapılır. Burada sadece `ivac_session` çerezinin VARLIĞI kontrol edilir
 * (imzası/geçerliliği değil — o kontrol Redis'te, backend'de yapılır).
 *
 * DÜZELTME (CODEX_AUDIT_PHASE_5_FRONTEND.md YÜKSEK-1): Bu middleware daha
 * önce `hasSession && pathname === "/login"` durumunda KOŞULSUZ olarak "/"e
 * yönlendiriyordu — yani çerezin VAR OLMASINI oturumun GEÇERLİ olduğunun
 * kanıtı sayıyordu. Süresi dolmuş ama tarayıcıda silinmemiş bir çerezle:
 *   1. Kullanıcı korumalı bir sayfaya gider → middleware geçer (çerez var).
 *   2. `SessionProvider` `/api/auth/me`'den 401 alır → `/login`'e yönlendirir.
 *   3. Middleware bu isteği görür, çerez HÂLÂ var diye tekrar "/"e yönlendirir.
 *   4. 2-3 sonsuza kadar tekrarlanır (redirect loop) — kullanıcı asla login
 *      formuna ulaşamaz.
 * Düzeltme: middleware ARTIK `/login`'den asla zorla yönlendirmiyor. Geçerli
 * bir oturumu olan kullanıcının `/login`'den dashboard'a yönlendirilmesi,
 * gerçek `/api/auth/me` doğrulamasından SONRA, `app/login/page.tsx` (client)
 * tarafından yapılıyor — bkz. o dosyadaki yorum. Bu, middleware'in tek
 * sorumluluğunu "çerezsiz kullanıcıyı korumalı sayfadan uzak tut" ile sınırlı
 * tutar; "çerezli kullanıcı gerçekten giriş yapmış mı" sorusuna asla
 * middleware cevap vermez.
 */
const SESSION_COOKIE = "ivac_session";
const PUBLIC_PATHS = ["/login"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const isPublicPath = PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  if (!hasSession && !isPublicPath) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
