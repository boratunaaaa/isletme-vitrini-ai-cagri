"use client";

import { useState } from "react";
import { Settings2 } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import { useDashboardStats, useSettings, useUpdateSetting } from "@/lib/api/system";
import { IntegrationStatusCard } from "@/components/ui/integration-status-card";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/client";
import type { SettingItem } from "@/lib/api/schemas";

const SETTING_LABELS: Record<string, string> = {
  "netgsm.price_per_minute_try": "Netgsm dakika fiyatı (TRY)",
  "billing.usd_try_rate": "USD/TRY kuru",
  "calls.default_model": "Varsayılan model",
  "calls.default_voice": "Varsayılan ses",
  "calls.daily_limit_override": "Günlük limit override",
  "calls.transcript_retention_days": "Transkript saklama (gün)",
};

function SettingRow({ item }: { item: SettingItem }) {
  const updateSetting = useUpdateSetting();
  const [value, setValue] = useState(item.safe_value ?? "");
  const [error, setError] = useState<string | null>(null);
  const key = `${item.provider}.${item.setting_key}`;

  return (
    <div className="flex flex-wrap items-end justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-3">
      <div className="min-w-[220px] flex-1">
        <Label htmlFor={key}>{SETTING_LABELS[key] ?? key}</Label>
        <Input id={key} value={value} onChange={(e) => setValue(e.target.value)} />
        {error && <p className="mt-1 text-xs text-[var(--color-danger-400)]">{error}</p>}
        {item.updated_at && (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Son güncelleme: {formatDateTime(item.updated_at)}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge label={item.is_configured ? "Ayarlandı" : "Boş"} tone={item.is_configured ? "success" : "neutral"} />
        <PermissionGuard permission="settings:write">
          <Button
            size="sm"
            variant="secondary"
            loading={updateSetting.isPending}
            onClick={async () => {
              setError(null);
              try {
                await updateSetting.mutateAsync({
                  provider: item.provider,
                  setting_key: item.setting_key,
                  value: value || null,
                });
              } catch (err) {
                setError(err instanceof ApiError ? err.message : "Kaydedilemedi");
              }
            }}
          >
            Kaydet
          </Button>
        </PermissionGuard>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { data, isLoading, isError, error, refetch } = useSettings();
  const { data: dashboard } = useDashboardStats();

  return (
    <div>
      <PageHeader title="Ayarlar / Entegrasyonlar" description="Secret DEĞERLERİ burada gösterilmez/saklanmaz" />
      <div className="space-y-6 p-4 sm:p-6">
        {dashboard && (
          <div>
            <h2 className="mb-2 text-sm font-medium text-[var(--color-text-primary)]">Entegrasyon Durumu</h2>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {dashboard.integrations.map((item) => (
                <IntegrationStatusCard key={item.provider} item={item} />
              ))}
            </div>
          </div>
        )}

        <div>
          <h2 className="mb-2 text-sm font-medium text-[var(--color-text-primary)]">Panelden Düzenlenebilir Ayarlar</h2>
          {isLoading && <LoadingState />}
          {isError && (
            <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
          )}
          {data && data.length === 0 && <EmptyState icon={Settings2} title="Ayar tanımlı değil" />}
          {data && data.length > 0 && (
            <div className="space-y-2">
              {data.map((item) => (
                <SettingRow key={`${item.provider}.${item.setting_key}`} item={item} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
