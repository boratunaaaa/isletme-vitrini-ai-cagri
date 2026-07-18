"use client";

import { useState } from "react";
import { LogOut, Menu, User as UserIcon, Wifi, WifiOff } from "lucide-react";
import { useSession } from "@/lib/auth/session-context";
import { useLogout } from "@/lib/api/auth";
import { roleMeta } from "@/lib/enums";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import type { ConnectionStatus } from "@/lib/hooks/use-live-events";

export function Topbar({
  onMenuClick,
  liveStatus,
}: {
  onMenuClick: () => void;
  liveStatus?: ConnectionStatus;
}) {
  const { user } = useSession();
  const logout = useLogout();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);

  const role = user ? roleMeta(user.role) : null;

  return (
    <header className="flex h-14 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-surface)] px-4">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          aria-label="Menüyü aç"
          className="rounded-md p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-bg-hover)] lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        {liveStatus && (
          <span
            className="hidden items-center gap-1.5 text-xs text-[var(--color-text-muted)] sm:flex"
            title={`Canlı bağlantı: ${liveStatus}`}
          >
            {liveStatus === "open" ? (
              <Wifi className="h-3.5 w-3.5 text-[var(--color-success-400)]" />
            ) : (
              <WifiOff className="h-3.5 w-3.5 text-[var(--color-warning-400)]" />
            )}
            {liveStatus === "open" ? "Canlı" : liveStatus === "reconnecting" ? "Yeniden bağlanıyor" : "Bağlanıyor"}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {user && (
          <div className="flex items-center gap-2 text-sm">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-bg-hover)]">
              <UserIcon className="h-3.5 w-3.5 text-[var(--color-text-secondary)]" />
            </div>
            <div className="hidden text-right sm:block">
              <p className="leading-none text-[var(--color-text-primary)]">{user.full_name}</p>
              {role && (
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{role.label}</p>
              )}
            </div>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label="Çıkış yap"
          loading={loggingOut}
          onClick={async () => {
            setLoggingOut(true);
            try {
              await logout.mutateAsync();
            } finally {
              router.replace("/login");
            }
          }}
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
