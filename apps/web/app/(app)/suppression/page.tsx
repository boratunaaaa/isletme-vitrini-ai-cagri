"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldOff, Trash2, Plus } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useCreateSuppression, useRemoveSuppression, useSuppression } from "@/lib/api/ops";
import { suppressionCreateSchema, type SuppressionCreateInput } from "@/lib/api/schemas";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/client";

export default function SuppressionPage() {
  const { data, isLoading, isError, error, refetch } = useSuppression();
  const createSuppression = useCreateSuppression();
  const removeSuppression = useRemoveSuppression();
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<SuppressionCreateInput>({ resolver: zodResolver(suppressionCreateSchema) });

  async function onSubmit(values: SuppressionCreateInput) {
    setFormError(null);
    try {
      await createSuppression.mutateAsync(values);
      reset();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Eklenemedi");
    }
  }

  return (
    <div>
      <PageHeader title="Arama Engeli (Suppression)" description="Bu listedeki numaralar asla aranmaz" />
      <div className="grid grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {isLoading && <LoadingState />}
          {isError && (
            <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
          )}
          {data && data.length === 0 && <EmptyState icon={ShieldOff} title="Engel listesi boş" />}
          {data && data.length > 0 && (
            <div className="space-y-2">
              {data.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-3"
                >
                  <div>
                    <p className="text-sm font-medium text-[var(--color-text-primary)]">
                      {entry.business_name ?? `•••${entry.phone_last_four}`}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {entry.reason} · {entry.source} · {formatDateTime(entry.created_at)}
                    </p>
                  </div>
                  <PermissionGuard permission="suppression:remove">
                    <Button variant="ghost" size="icon" onClick={() => setPendingDelete(entry.id)}>
                      <Trash2 className="h-4 w-4 text-[var(--color-danger-400)]" />
                    </Button>
                  </PermissionGuard>
                </div>
              ))}
            </div>
          )}
        </div>

        <PermissionGuard permission="suppression:write">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
            <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Yeni Engel Ekle</h2>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
              <div>
                <Label htmlFor="phone">Telefon (lead yoksa)</Label>
                <Input id="phone" placeholder="+90532..." {...register("phone")} />
              </div>
              <div>
                <Label htmlFor="reason">Neden</Label>
                <Input id="reason" {...register("reason")} />
                {errors.reason && (
                  <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.reason.message}</p>
                )}
              </div>
              {formError && <p className="text-xs text-[var(--color-danger-400)]">{formError}</p>}
              <Button type="submit" size="sm" loading={isSubmitting || createSuppression.isPending}>
                <Plus className="h-4 w-4" /> Ekle
              </Button>
            </form>
          </div>
        </PermissionGuard>
      </div>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Engeli kaldır"
        description="Bu numara tekrar aranabilir hale gelecek."
        confirmLabel="Kaldır"
        destructive
        loading={removeSuppression.isPending}
        onConfirm={async () => {
          if (pendingDelete) await removeSuppression.mutateAsync(pendingDelete);
          setPendingDelete(null);
        }}
      />
    </div>
  );
}
