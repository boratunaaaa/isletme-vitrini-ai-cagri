import type { ReactNode } from "react";
import { AlertTriangle, Inbox, Loader2, PlugZap } from "lucide-react";
import { Button } from "./button";

export function LoadingState({ label = "Yükleniyor…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-[var(--color-text-muted)]">
      <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function ErrorState({
  title = "Bir şeyler ters gitti",
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <AlertTriangle className="h-8 w-8 text-[var(--color-danger-400)]" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium text-[var(--color-text-primary)]">{title}</p>
        {message && <p className="mt-1 text-xs text-[var(--color-text-muted)]">{message}</p>}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Tekrar dene
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
  icon: Icon = Inbox,
}: {
  title: string;
  message?: string;
  action?: ReactNode;
  icon?: typeof Inbox;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Icon className="h-8 w-8 text-[var(--color-text-muted)]" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium text-[var(--color-text-primary)]">{title}</p>
        {message && <p className="mt-1 text-xs text-[var(--color-text-muted)]">{message}</p>}
      </div>
      {action}
    </div>
  );
}

/** Backend'de henüz bir uç/özellik yoksa fabrikasyon veri göstermek yerine bu kullanılır. */
export function NotWiredState({ feature }: { feature: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[var(--color-border-strong)] py-16 text-center">
      <PlugZap className="h-8 w-8 text-[var(--color-text-muted)]" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium text-[var(--color-text-primary)]">
          {feature} henüz backend&apos;e bağlı değil
        </p>
        <p className="mt-1 max-w-sm text-xs text-[var(--color-text-muted)]">
          Bu özellik için gerçek bir backend endpoint&apos;i bulunmuyor. Sahte veri gösterilmiyor.
        </p>
      </div>
    </div>
  );
}
