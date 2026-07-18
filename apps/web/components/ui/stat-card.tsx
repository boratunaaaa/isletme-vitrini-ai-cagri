import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  hint?: string;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  const toneClass = {
    neutral: "text-[var(--color-text-primary)]",
    success: "text-[var(--color-success-400)]",
    warning: "text-[var(--color-warning-400)]",
    danger: "text-[var(--color-danger-400)]",
  }[tone];

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-[var(--color-text-secondary)]">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-[var(--color-text-muted)]" aria-hidden="true" />}
      </div>
      <div className={cn("mt-2 text-2xl font-semibold tabular-nums", toneClass)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-[var(--color-text-muted)]">{hint}</div>}
    </div>
  );
}
