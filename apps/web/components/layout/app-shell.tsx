"use client";

import { useState, type ReactNode } from "react";
import { DesktopSidebar, MobileSidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { useLiveEvents } from "@/lib/hooks/use-live-events";
import { SessionProvider, useSession } from "@/lib/auth/session-context";
import { LoadingState } from "@/components/ui/states";

function AppShellInner({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { isLoading, user } = useSession();
  const { status } = useLiveEvents(!isLoading && Boolean(user));

  if (isLoading || !user) {
    return (
      <div className="flex h-dvh items-center justify-center bg-[var(--color-bg-canvas)]">
        <LoadingState label="Oturum doğrulanıyor…" />
      </div>
    );
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-[var(--color-bg-canvas)]">
      <DesktopSidebar />
      <MobileSidebar open={mobileOpen} onClose={() => setMobileOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenuClick={() => setMobileOpen(true)} liveStatus={status} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <AppShellInner>{children}</AppShellInner>
    </SessionProvider>
  );
}
