"use client";

import { useState } from "react";
import { MonitorPlay, MessageCircle } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { FilterBar } from "@/components/ui/filter-bar";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/states";
import { useDemoRequests, useDemoWaLink, useMarkDemoSent } from "@/lib/api/ops";
import { demoStatusMeta, type BadgeTone } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import type { DemoRequestOut } from "@/lib/api/schemas";

export default function DemoRequestsPage() {
  const [includeSent, setIncludeSent] = useState(false);
  const { data, isLoading, isError, error, refetch } = useDemoRequests(includeSent);
  const markSent = useMarkDemoSent();

  return (
    <div>
      <PageHeader title="Demo Talepleri" description={data ? `${data.length} kayıt` : undefined} />
      <FilterBar>
        <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
          <input
            type="checkbox"
            checked={includeSent}
            onChange={(e) => setIncludeSent(e.target.checked)}
            className="h-4 w-4 rounded border-[var(--color-border-strong)]"
          />
          Gönderilenleri de göster
        </label>
      </FilterBar>
      <div className="p-4 sm:p-6">
        {isLoading && <LoadingState />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
        )}
        {data && data.length === 0 && <EmptyState icon={MonitorPlay} title="Demo talebi yok" />}
        {data && data.length > 0 && (
          <div className="space-y-2">
            {data.map((demo) => {
              const meta = demoStatusMeta(demo.status);
              return <DemoRow key={demo.id} demo={demo} meta={meta} markSent={markSent} />;
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function DemoRow({
  demo,
  meta,
  markSent,
}: {
  demo: DemoRequestOut;
  meta: { label: string; tone: BadgeTone };
  markSent: ReturnType<typeof useMarkDemoSent>;
}) {
  const waLink = useDemoWaLink(demo.id);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-3">
      <div>
        <p className="text-sm font-medium text-[var(--color-text-primary)]">
          {demo.business_name ?? "Bilinmeyen"}
        </p>
        <p className="text-xs text-[var(--color-text-muted)]">{formatDateTime(demo.created_at)}</p>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge label={meta.label} tone={meta.tone} />
        {demo.status === "pending" && (
          <>
            <Button
              size="sm"
              variant="secondary"
              loading={waLink.isPending}
              onClick={async () => {
                const result = await waLink.mutateAsync();
                window.open(result.wa_link, "_blank", "noopener,noreferrer");
              }}
            >
              <MessageCircle className="h-4 w-4" /> WhatsApp Aç
            </Button>
            <Button size="sm" loading={markSent.isPending} onClick={() => markSent.mutate(demo.id)}>
              Gönderildi İşaretle
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
