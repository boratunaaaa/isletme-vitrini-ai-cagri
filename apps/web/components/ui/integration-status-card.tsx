import { CheckCircle2, XCircle } from "lucide-react";
import type { IntegrationStatus } from "@/lib/api/schemas";

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI Realtime",
  livekit: "LiveKit",
  netgsm: "Netgsm SIP",
  sip_trunk: "SIP Trunk",
  google_places: "Google Places",
};

export function IntegrationStatusCard({ item }: { item: IntegrationStatus }) {
  const label = PROVIDER_LABELS[item.provider] ?? item.provider;
  return (
    <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] px-4 py-3">
      <div>
        <p className="text-sm font-medium text-[var(--color-text-primary)]">{label}</p>
        <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{item.detail}</p>
      </div>
      {item.configured ? (
        <CheckCircle2 className="h-5 w-5 text-[var(--color-success-400)]" aria-label="Yapılandırıldı" />
      ) : (
        <XCircle className="h-5 w-5 text-[var(--color-text-muted)]" aria-label="Yapılandırılmadı" />
      )}
    </div>
  );
}
