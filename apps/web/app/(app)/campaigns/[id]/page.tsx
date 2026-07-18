"use client";

import { use } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import { useCampaign, useCampaignStats, useChangeCampaignStatus } from "@/lib/api/campaigns";
import { campaignStatusMeta, CAMPAIGN_STATUS_ACTIONS } from "@/lib/enums";
import { formatUsd } from "@/lib/format";
import { Users2, PhoneCall, RefreshCw, CheckCircle2, ShieldOff, XCircle } from "lucide-react";
import { ApiError } from "@/lib/api/client";
import { useState } from "react";

export default function CampaignDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: campaign, isLoading, isError, error, refetch } = useCampaign(id);
  const { data: stats } = useCampaignStats(id);
  const changeStatus = useChangeCampaignStatus(id);
  const [statusError, setStatusError] = useState<string | null>(null);

  if (isLoading) return <LoadingState />;
  if (isError || !campaign) {
    return <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />;
  }

  const statusMeta = campaignStatusMeta(campaign.status);
  const actions = CAMPAIGN_STATUS_ACTIONS[campaign.status] ?? [];

  return (
    <div>
      <PageHeader
        title={campaign.name}
        description={campaign.description ?? undefined}
        actions={
          <PermissionGuard permission="campaign:control">
            <div className="flex gap-2">
              {actions.map((a) => (
                <Button
                  key={a.action}
                  size="sm"
                  variant={a.action === "cancel" || a.action === "stop" ? "danger" : "primary"}
                  loading={changeStatus.isPending}
                  onClick={async () => {
                    setStatusError(null);
                    try {
                      await changeStatus.mutateAsync(a.action);
                    } catch (err) {
                      setStatusError(err instanceof ApiError ? err.message : "İşlem başarısız");
                    }
                  }}
                >
                  {a.label}
                </Button>
              ))}
            </div>
          </PermissionGuard>
        }
      />
      <div className="space-y-6 p-4 sm:p-6">
        {statusError && (
          <p className="rounded-md bg-[var(--color-danger-bg)] px-3 py-2 text-sm text-[var(--color-danger-400)]">
            {statusError}
          </p>
        )}
        <div className="flex items-center gap-2">
          <StatusBadge label={statusMeta.label} tone={statusMeta.tone} />
          <span className="text-xs text-[var(--color-text-muted)]">
            {campaign.realtime_model} · {campaign.realtime_voice}
          </span>
        </div>

        {stats && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <StatCard label="Toplam Lead" value={stats.total_leads} icon={Users2} />
            <StatCard label="Bugün Aranan" value={stats.calls_today} icon={PhoneCall} />
            <StatCard label="Aranıyor" value={stats.calling} icon={PhoneCall} tone="warning" />
            <StatCard label="Tekrar Planlandı" value={stats.retry_scheduled} icon={RefreshCw} tone="warning" />
            <StatCard label="Tamamlandı" value={stats.completed} icon={CheckCircle2} tone="success" />
            <StatCard label="Baskılanan" value={stats.suppressed} icon={ShieldOff} tone="danger" />
            <StatCard label="Tükenen" value={stats.exhausted} icon={XCircle} tone="neutral" />
            <StatCard label="Toplam Maliyet" value={formatUsd(stats.total_cost_usd)} />
          </div>
        )}

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
          <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Yapılandırma</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Arama Saatleri</dt>
              <dd>
                {campaign.call_start_hour}:00 – {campaign.call_end_hour}:00
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Maks. Görüşme Süresi</dt>
              <dd>{campaign.max_call_duration_seconds}s</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Maks. Tekrar Deneme</dt>
              <dd>{campaign.max_retry_count}</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Tekrar Gecikmesi</dt>
              <dd>{campaign.retry_delay_minutes} dk</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Günlük Limit</dt>
              <dd>{campaign.daily_limit}</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Eşzamanlı Limit</dt>
              <dd>{campaign.concurrent_call_limit}</dd>
            </div>
          </dl>
        </div>

        {stats && Object.keys(stats.outcomes).length > 0 && (
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
            <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Sonuç Dağılımı</h2>
            <div className="flex flex-wrap gap-2">
              {Object.entries(stats.outcomes).map(([outcome, count]) => (
                <StatusBadge key={outcome} label={`${outcome}: ${count}`} tone="neutral" />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
