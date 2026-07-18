"use client";

import { use, useState } from "react";
import { PhoneOff } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useCall, useHangupCall } from "@/lib/api/calls";
import { callOutcomeMeta, callStatusMeta, ACTIVE_CALL_STATUSES } from "@/lib/enums";
import { formatDateTime, formatDuration, formatUsd } from "@/lib/format";

export default function CallDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, isLoading, isError, error, refetch } = useCall(id);
  const hangup = useHangupCall(id);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (isLoading) return <LoadingState />;
  if (isError || !data) {
    return <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />;
  }

  const { call, events, usage, transcript } = data;
  const statusMeta = callStatusMeta(call.status);
  const outcomeMeta = call.outcome ? callOutcomeMeta(call.outcome) : null;
  const isActive = (ACTIVE_CALL_STATUSES as readonly string[]).includes(call.status);

  return (
    <div>
      <PageHeader
        title={call.business_name ?? "Arama Detayı"}
        description={`${call.model} · ${call.voice}`}
        actions={
          isActive && (
            <PermissionGuard permission="call:terminate">
              <Button variant="danger" size="sm" onClick={() => setConfirmOpen(true)}>
                <PhoneOff className="h-4 w-4" /> Sonlandır
              </Button>
            </PermissionGuard>
          )
        }
      />
      <div className="grid grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={statusMeta.label} tone={statusMeta.tone} />
            {outcomeMeta && <StatusBadge label={outcomeMeta.label} tone={outcomeMeta.tone} />}
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
            <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Zaman Çizelgesi</h2>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Başladı</dt>
                <dd>{formatDateTime(call.started_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Cevaplandı</dt>
                <dd>{formatDateTime(call.answered_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Bitti</dt>
                <dd>{formatDateTime(call.ended_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Süre</dt>
                <dd>{formatDuration(call.duration_seconds)}</dd>
              </div>
              {call.disconnect_reason && (
                <div>
                  <dt className="text-xs text-[var(--color-text-muted)]">Bağlantı Kesilme Nedeni</dt>
                  <dd>{call.disconnect_reason}</dd>
                </div>
              )}
              {call.error_code && (
                <div>
                  <dt className="text-xs text-[var(--color-text-muted)]">Hata Kodu</dt>
                  <dd className="text-[var(--color-danger-400)]">{call.error_code}</dd>
                </div>
              )}
            </dl>
            {call.safe_summary && (
              <div className="mt-3 border-t border-[var(--color-border)] pt-3">
                <dt className="text-xs text-[var(--color-text-muted)]">Özet</dt>
                <dd className="mt-1 text-sm">{call.safe_summary}</dd>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
            <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Transkript</h2>
            {transcript === null && (
              <p className="text-xs text-[var(--color-text-muted)]">
                Transkript saklama kapalı (TRANSCRIPT_STORAGE_ENABLED=false) veya bu arama için kayıt yok.
              </p>
            )}
            {transcript && transcript.length === 0 && (
              <p className="text-xs text-[var(--color-text-muted)]">Bu arama için transkript kaydı yok.</p>
            )}
            {transcript && transcript.length > 0 && (
              <ul className="space-y-2 text-sm">
                {transcript.map((turn, idx) => (
                  <li key={idx} className="rounded-md bg-[var(--color-bg-hover)] p-2">
                    <pre className="whitespace-pre-wrap break-words text-xs text-[var(--color-text-secondary)]">
                      {JSON.stringify(turn, null, 2)}
                    </pre>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
            <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Olaylar</h2>
            <ul className="space-y-1.5 text-sm">
              {events.map((event) => (
                <li key={event.id} className="flex justify-between text-xs">
                  <span className="text-[var(--color-text-secondary)]">{event.event_type}</span>
                  <span className="text-[var(--color-text-muted)]">
                    {formatDateTime(event.event_timestamp)}
                  </span>
                </li>
              ))}
              {events.length === 0 && (
                <p className="text-xs text-[var(--color-text-muted)]">Olay kaydı yok.</p>
              )}
            </ul>
          </div>
        </div>

        <div className="space-y-4">
          {usage && (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
              <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Kullanım / Maliyet</h2>
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-[var(--color-text-muted)]">AI Maliyeti</dt>
                  <dd>{formatUsd(usage.estimated_ai_cost)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-[var(--color-text-muted)]">Telefon Maliyeti</dt>
                  <dd>{formatUsd(usage.estimated_telephony_cost)}</dd>
                </div>
                <div className="flex justify-between border-t border-[var(--color-border)] pt-2 font-medium">
                  <dt>Toplam</dt>
                  <dd>{formatUsd(usage.estimated_total_cost)}</dd>
                </div>
                <div className="flex justify-between text-xs text-[var(--color-text-muted)]">
                  <dt>Kaynak</dt>
                  <dd>{usage.usage_source}</dd>
                </div>
              </dl>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Aramayı sonlandır"
        description="Bu arama hemen sonlandırılacak. Bu işlem geri alınamaz."
        confirmLabel="Sonlandır"
        destructive
        loading={hangup.isPending}
        onConfirm={async () => {
          await hangup.mutateAsync();
          setConfirmOpen(false);
        }}
      />
    </div>
  );
}
