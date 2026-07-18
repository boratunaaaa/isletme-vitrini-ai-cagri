"use client";

import type { ReactNode } from "react";
import { useSession } from "@/lib/auth/session-context";

/**
 * YALNIZ UI'ı gizler/gösterir — gerçek yetki kontrolü her zaman backend'de
 * yapılır (app/deps.py::require_permission). Bu bileşen atlanabilir bir DevTools
 * hilesiyle gizli bir aksiyon çalıştırılamaz; sunucu 403 döner.
 */
export function PermissionGuard({
  permission,
  role,
  fallback = null,
  children,
}: {
  permission?: string;
  role?: string[];
  fallback?: ReactNode;
  children: ReactNode;
}) {
  const { hasPermission, hasRole } = useSession();
  const permissionOk = permission ? hasPermission(permission) : true;
  const roleOk = role ? hasRole(...role) : true;
  if (!permissionOk || !roleOk) return <>{fallback}</>;
  return <>{children}</>;
}
