"use client";

import { useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { FilterBar } from "@/components/ui/filter-bar";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/states";
import { useCallbacks, useUpdateCallback } from "@/lib/api/ops";
import { callbackStatusMeta } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { PhoneIncoming } from "lucide-react";

export default function CallbacksPage() {
  const [includeDone, setIncludeDone] = useState(false);
  const { data, isLoading, isError, error, refetch } = useCallbacks(includeDone);
  const updateCallback = useUpdateCallback();

  return (
    <div>
      <PageHeader title="Geri Aramalar" description={data ? `${data.length} kayıt` : undefined} />
      <FilterBar>
        <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
          <input
            type="checkbox"
            checked={includeDone}
            onChange={(e) => setIncludeDone(e.target.checked)}
            className="h-4 w-4 rounded border-[var(--color-border-strong)]"
          />
          Tamamlananları da göster
        </label>
      </FilterBar>
      <div className="p-4 sm:p-6">
        {isLoading && <LoadingState />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
        )}
        {data && data.length === 0 && <EmptyState icon={PhoneIncoming} title="Geri arama kaydı yok" />}
        {data && data.length > 0 && (
          <div className="space-y-2">
            {data.map((cb) => {
              const meta = callbackStatusMeta(cb.status);
              return (
                <div
                  key={cb.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-3"
                >
                  <div>
                    <p className="text-sm font-medium text-[var(--color-text-primary)]">
                      {cb.business_name ?? "Bilinmeyen"}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Planlanan: {formatDateTime(cb.callback_at)}
                    </p>
                    {cb.notes && <p className="mt-1 text-xs text-[var(--color-text-secondary)]">{cb.notes}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge label={meta.label} tone={meta.tone} />
                    {cb.status !== "done" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={updateCallback.isPending}
                        onClick={() => updateCallback.mutate({ id: cb.id, input: { status: "done" } })}
                      >
                        Tamamlandı İşaretle
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
