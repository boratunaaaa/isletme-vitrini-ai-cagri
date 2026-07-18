"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as Dialog from "@radix-ui/react-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/ui/data-table";
import { Pagination } from "@/components/ui/pagination";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import { useCampaigns, useCreateCampaign } from "@/lib/api/campaigns";
import { campaignStatusMeta } from "@/lib/enums";
import { formatDate } from "@/lib/format";
import { campaignBaseSchema, type CampaignCreateInput, type CampaignOut } from "@/lib/api/schemas";
import { ApiError } from "@/lib/api/client";

function CreateCampaignDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const createCampaign = useCreateCampaign();
  const router = useRouter();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<CampaignCreateInput>({
    resolver: zodResolver(campaignBaseSchema),
    defaultValues: {
      name: "",
      daily_limit: 10,
      concurrent_call_limit: 1,
      call_start_hour: 10,
      call_end_hour: 17,
      max_call_duration_seconds: 300,
      max_retry_count: 2,
      retry_delay_minutes: 120,
      conversation_engine: "openai_realtime",
    },
  });

  async function onSubmit(values: CampaignCreateInput) {
    try {
      const campaign = await createCampaign.mutateAsync(values);
      reset();
      onOpenChange(false);
      router.push(`/campaigns/${campaign.id}`);
    } catch {
      // ApiError alan hataları formun altında gösterilir (bkz. formError state'i gerekirse eklenir)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-bg-surface-raised)] p-5 shadow-xl focus:outline-none">
          <Dialog.Title className="text-sm font-semibold text-[var(--color-text-primary)]">
            Yeni Kampanya
          </Dialog.Title>
          <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-3">
            <div>
              <Label htmlFor="name">Kampanya Adı</Label>
              <Input id="name" {...register("name")} />
              {errors.name && <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.name.message}</p>}
            </div>
            <div>
              <Label htmlFor="description">Açıklama</Label>
              <Textarea id="description" {...register("description")} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="daily_limit">Günlük Limit</Label>
                <Input id="daily_limit" type="number" {...register("daily_limit", { valueAsNumber: true })} />
              </div>
              <div>
                <Label htmlFor="concurrent_call_limit">Eşzamanlı Limit</Label>
                <Input
                  id="concurrent_call_limit"
                  type="number"
                  {...register("concurrent_call_limit", { valueAsNumber: true })}
                />
              </div>
              <div>
                <Label htmlFor="call_start_hour">Başlangıç Saati</Label>
                <Input id="call_start_hour" type="number" {...register("call_start_hour", { valueAsNumber: true })} />
              </div>
              <div>
                <Label htmlFor="call_end_hour">Bitiş Saati</Label>
                <Input id="call_end_hour" type="number" {...register("call_end_hour", { valueAsNumber: true })} />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close asChild>
                <Button variant="secondary" size="sm" type="button">
                  Vazgeç
                </Button>
              </Dialog.Close>
              <Button size="sm" type="submit" loading={isSubmitting || createCampaign.isPending}>
                Oluştur
              </Button>
            </div>
            {createCampaign.isError && (
              <p className="text-xs text-[var(--color-danger-400)]">
                {createCampaign.error instanceof ApiError
                  ? createCampaign.error.message
                  : "Kampanya oluşturulamadı"}
              </p>
            )}
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function CampaignsPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const { data, isLoading, isError, error, refetch } = useCampaigns(page, 25);

  const columns = useMemo<ColumnDef<CampaignOut, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Kampanya" },
      {
        accessorKey: "status",
        header: "Durum",
        cell: ({ row }) => {
          const meta = campaignStatusMeta(row.original.status);
          return <StatusBadge label={meta.label} tone={meta.tone} />;
        },
      },
      { accessorKey: "daily_limit", header: "Günlük Limit" },
      { accessorKey: "realtime_model", header: "Model" },
      {
        accessorKey: "created_at",
        header: "Oluşturulma",
        cell: ({ row }) => formatDate(row.original.created_at),
      },
    ],
    []
  );

  if (isError) {
    return <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />;
  }

  return (
    <div>
      <PageHeader
        title="Kampanyalar"
        description={data ? `${data.total} kampanya` : undefined}
        actions={
          <PermissionGuard permission="campaign:write">
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> Yeni Kampanya
            </Button>
          </PermissionGuard>
        }
      />
      <DataTable
        columns={columns}
        data={data?.items ?? []}
        isLoading={isLoading}
        emptyTitle="Kampanya yok"
        emptyMessage="İlk kampanyanızı oluşturun."
        onRowClick={(row) => router.push(`/campaigns/${row.id}`)}
        getRowId={(row) => row.id}
      />
      {data && (
        <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
      )}
      <CreateCampaignDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
