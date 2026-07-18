import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-4 sm:px-6">
      <div>
        <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">{title}</h1>
        {description && (
          <p className="mt-0.5 text-sm text-[var(--color-text-secondary)]">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
