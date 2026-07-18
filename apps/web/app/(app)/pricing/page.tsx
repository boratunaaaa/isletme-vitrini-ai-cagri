"use client";

import { useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import { usePricing, useUpdatePricing } from "@/lib/api/system";
import { DollarSign } from "lucide-react";
import type { PricingOut } from "@/lib/api/schemas";
import { ApiError } from "@/lib/api/client";

const PRICE_FIELDS: { key: keyof PricingOut; label: string }[] = [
  { key: "input_audio_price_per_million", label: "Giriş Ses ($/1M token)" },
  { key: "cached_audio_price_per_million", label: "Önbellek Ses ($/1M token)" },
  { key: "output_audio_price_per_million", label: "Çıkış Ses ($/1M token)" },
  { key: "input_text_price_per_million", label: "Giriş Metin ($/1M token)" },
  { key: "cached_text_price_per_million", label: "Önbellek Metin ($/1M token)" },
  { key: "output_text_price_per_million", label: "Çıkış Metin ($/1M token)" },
];

function PricingRow({ pricing }: { pricing: PricingOut }) {
  const updatePricing = useUpdatePricing();
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(PRICE_FIELDS.map((f) => [f.key, pricing[f.key] as string]))
  );
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const dirty = PRICE_FIELDS.some((f) => values[f.key] !== pricing[f.key]);

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
      <div className="mb-3">
        <p className="text-sm font-medium text-[var(--color-text-primary)]">{pricing.model}</p>
        <p className="text-xs text-[var(--color-text-muted)]">{pricing.provider}</p>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {PRICE_FIELDS.map((f) => (
          <div key={f.key}>
            <Label htmlFor={`${pricing.id}-${f.key}`}>{f.label}</Label>
            <Input
              id={`${pricing.id}-${f.key}`}
              value={values[f.key]}
              onChange={(e) => {
                setSaved(false);
                setValues((prev) => ({ ...prev, [f.key]: e.target.value }));
              }}
            />
          </div>
        ))}
      </div>
      {saveError && <p className="mt-2 text-xs text-[var(--color-danger-400)]">{saveError}</p>}
      {saved && <p className="mt-2 text-xs text-[var(--color-success-400)]">Kaydedildi</p>}
      <PermissionGuard permission="pricing:write">
        <div className="mt-3">
          <Button
            size="sm"
            variant="secondary"
            disabled={!dirty}
            loading={updatePricing.isPending}
            onClick={async () => {
              setSaveError(null);
              try {
                await updatePricing.mutateAsync({ id: pricing.id, input: values });
                setSaved(true);
              } catch (err) {
                setSaveError(err instanceof ApiError ? err.message : "Kaydedilemedi");
              }
            }}
          >
            Kaydet
          </Button>
        </div>
      </PermissionGuard>
    </div>
  );
}

export default function PricingPage() {
  const { data, isLoading, isError, error, refetch } = usePricing();

  return (
    <div>
      <PageHeader title="Fiyatlandırma" description="Sağlayıcı bazlı token/dakika fiyatları" />
      <div className="space-y-4 p-4 sm:p-6">
        {isLoading && <LoadingState />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
        )}
        {data && data.length === 0 && <EmptyState icon={DollarSign} title="Fiyatlandırma kaydı yok" />}
        {data?.map((pricing) => (
          <PricingRow key={pricing.id} pricing={pricing} />
        ))}
      </div>
    </div>
  );
}
