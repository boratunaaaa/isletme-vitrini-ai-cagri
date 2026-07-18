"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Phone, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { useSession } from "@/lib/auth/session-context";
import { NAV_SECTIONS } from "./nav-items";

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { hasPermission } = useSession();

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--color-brand-500)]">
          <Phone className="h-4 w-4 text-white" />
        </div>
        <div>
          <p className="text-sm font-semibold leading-none text-[var(--color-text-primary)]">
            İşletme Vitrini
          </p>
          <p className="text-xs text-[var(--color-text-muted)]">AI Çağrı Merkezi</p>
        </div>
      </div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-2 pb-4">
        {NAV_SECTIONS.map((section) => {
          const items = section.items.filter(
            (item) => !item.permission || hasPermission(item.permission)
          );
          if (items.length === 0) return null;
          return (
            <div key={section.label}>
              <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                {section.label}
              </p>
              <ul className="space-y-0.5">
                {items.map((item) => {
                  const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onNavigate}
                        className={cn(
                          "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                          active
                            ? "bg-[var(--color-brand-500)]/15 text-[var(--color-brand-400)] font-medium"
                            : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-primary)]"
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>
    </div>
  );
}

export function DesktopSidebar() {
  return (
    <aside className="hidden w-64 shrink-0 border-r border-[var(--color-border)] bg-[var(--color-bg-surface)] lg:block">
      <SidebarContent />
    </aside>
  );
}

export function MobileSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden="true" />
      <div className="absolute inset-y-0 left-0 w-72 bg-[var(--color-bg-surface)] shadow-xl">
        <button
          onClick={onClose}
          aria-label="Menüyü kapat"
          className="absolute right-3 top-3 rounded-md p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-bg-hover)]"
        >
          <X className="h-4 w-4" />
        </button>
        <SidebarContent onNavigate={onClose} />
      </div>
    </div>
  );
}
