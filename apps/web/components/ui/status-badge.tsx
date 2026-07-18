import { cn } from "@/lib/cn";
import type { BadgeTone } from "@/lib/enums";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-[var(--color-bg-hover)] text-[var(--color-text-secondary)]",
  brand: "bg-[var(--color-brand-500)]/15 text-[var(--color-brand-400)]",
  success: "bg-[var(--color-success-bg)] text-[var(--color-success-400)]",
  warning: "bg-[var(--color-warning-bg)] text-[var(--color-warning-400)]",
  danger: "bg-[var(--color-danger-bg)] text-[var(--color-danger-400)]",
  info: "bg-[var(--color-info-bg)] text-[var(--color-info-400)]",
};

export function StatusBadge({ label, tone }: { label: string; tone: BadgeTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        TONE_CLASSES[tone]
      )}
    >
      {label}
    </span>
  );
}
