"use client";

import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { useMe } from "@/lib/api/auth";
import type { UserOut } from "@/lib/api/schemas";

type SessionContextValue = {
  user: UserOut | null;
  permissions: string[];
  isLoading: boolean;
  hasPermission: (permission: string) => boolean;
  hasRole: (...roles: string[]) => boolean;
};

const SessionContext = createContext<SessionContextValue | null>(null);

/**
 * `/api/auth/me` gerçek oturum durumunun tek doğrulama kaynağıdır. 401 alınırsa
 * (çerez yok/süresi dolmuş) `/login`'e yönlendirilir — middleware yalnız çerez
 * VARLIĞINA bakar, burası backend'in "geçerli mi" cevabına bakar.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data, isLoading, isError, error } = useMe();

  useEffect(() => {
    // `/login` yapısal olarak zaten bu provider'ın dışında (route group
    // `(app)`), ama burası hâlâ bir güvenlik ağıdır: 401 üzerine yalnız
    // /login'DE DEĞİLSEK yönlendir — aksi halde ikinci bir gereksiz
    // navigasyon (ve teorik olarak bir döngü) üretmeyiz.
    if (isError && error instanceof ApiError && error.isUnauthorized && pathname !== "/login") {
      router.replace("/login");
    }
  }, [isError, error, router, pathname]);

  const value = useMemo<SessionContextValue>(() => {
    const permissions = data?.permissions ?? [];
    return {
      user: data?.user ?? null,
      permissions,
      isLoading,
      hasPermission: (permission: string) => permissions.includes(permission),
      hasRole: (...roles: string[]) => (data?.user ? roles.includes(data.user.role) : false),
    };
  }, [data, isLoading]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
