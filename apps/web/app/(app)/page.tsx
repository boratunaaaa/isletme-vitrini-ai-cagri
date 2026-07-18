"use client";

import { PageHeader } from "@/components/layout/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { IntegrationStatusCard } from "@/components/ui/integration-status-card";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { StatusBadge } from "@/components/ui/status-badge";
import { useDashboardStats } from "@/lib/api/system";
import { formatDuration, formatPercent, formatUsd } from "@/lib/format";
import {
  Phone,
  PhoneCall,
  Percent,
  Megaphone,
  Radio,
  DollarSign,
  MonitorPlay,
  PhoneIncoming,
  Ban,
} from "lucide-react";

export default function DashboardPage() {
  const { data, isLoading, isError, error, refetch } = useDashboardStats();

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Bugünün özet metrikleri (Europe/Istanbul günü, 00:00'dan itibaren)"
      />
      <div className="p-4 sm:p-6">
        {isLoading && <LoadingState />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : undefined}
            onRetry={() => refetch()}
          />
        )}
        {data && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              <StatCard label="Bugünkü Aramalar" value={data.calls_today} icon={Phone} />
              <StatCard label="Cevaplanan" value={data.answered_today} icon={PhoneCall} />
              <StatCard
                label="Başarı Oranı"
                value={formatPercent(data.success_rate)}
                icon={Percent}
                tone={data.success_rate > 0.2 ? "success" : "neutral"}
              />
              <StatCard
                label="Ort. Süre"
                value={formatDuration(data.avg_duration_seconds)}
                icon={Phone}
              />
              <StatCard label="İlgilenen" value={data.interested_count} icon={PhoneCall} tone="success" />
              <StatCard label="Demo İsteyen" value={data.demo_requested_count} icon={MonitorPlay} tone="success" />
              <StatCard label="Bekleyen Geri Arama" value={data.callback_count} icon={PhoneIncoming} tone="warning" />
              <StatCard label="Aranmasın Listesi" value={data.do_not_call_count} icon={Ban} tone="danger" />
              <StatCard label="Aktif Kampanya" value={data.active_campaigns} icon={Megaphone} />
              <StatCard label="Canlı Arama" value={data.live_calls} icon={Radio} tone={data.live_calls > 0 ? "success" : "neutral"} />
              <StatCard label="AI Maliyeti (bugün)" value={formatUsd(data.ai_cost_today_usd)} icon={DollarSign} />
              <StatCard label="Toplam Maliyet (bugün)" value={formatUsd(data.total_cost_today_usd)} icon={DollarSign} />
            </div>

            <div>
              <h2 className="mb-2 text-sm font-medium text-[var(--color-text-primary)]">
                Güvenlik Kapıları
              </h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(data.gates).map(([key, value]) => (
                  <StatusBadge
                    key={key}
                    label={`${key}: ${value ? "açık" : "kapalı"}`}
                    tone={value ? "success" : "neutral"}
                  />
                ))}
              </div>
            </div>

            <div>
              <h2 className="mb-2 text-sm font-medium text-[var(--color-text-primary)]">
                Entegrasyon Durumu
              </h2>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {data.integrations.map((item) => (
                  <IntegrationStatusCard key={item.provider} item={item} />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
