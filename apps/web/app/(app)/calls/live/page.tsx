"use client";

import { useRouter } from "next/navigation";
import { Radio } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useLiveCalls } from "@/lib/api/calls";
import { callStatusMeta } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";

export default function LiveCallsPage() {
  const router = useRouter();
  const { data, isLoading, isError, error, refetch } = useLiveCalls();

  return (
    <div>
      <PageHeader
        title="Canlı Aramalar"
        description="5 saniyede bir yenilenir; SSE olayı gelince anında tazelenir"
      />
      <div className="p-4 sm:p-6">
        {isLoading && <LoadingState />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
        )}
        {data && data.length === 0 && (
          <EmptyState icon={Radio} title="Şu anda aktif arama yok" />
        )}
        {data && data.length > 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.map((call) => {
              const meta = callStatusMeta(call.status);
              return (
                <button
                  key={call.id}
                  onClick={() => router.push(`/calls/${call.id}`)}
                  className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4 text-left transition-colors hover:bg-[var(--color-bg-hover)]"
                >
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-[var(--color-text-primary)]">
                      {call.business_name ?? "Bilinmeyen"}
                    </p>
                    <StatusBadge label={meta.label} tone={meta.tone} />
                  </div>
                  <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                    Başlangıç: {formatDateTime(call.started_at)}
                  </p>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {call.model} · {call.voice}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
