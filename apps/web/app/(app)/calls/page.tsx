"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { PageHeader } from "@/components/layout/page-header";
import { FilterBar } from "@/components/ui/filter-bar";
import { Select } from "@/components/ui/input";
import { DataTable } from "@/components/ui/data-table";
import { Pagination } from "@/components/ui/pagination";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState } from "@/components/ui/states";
import { useCalls } from "@/lib/api/calls";
import { callOutcomeMeta, callStatusMeta } from "@/lib/enums";
import { callOutcomeValues, callStatusValues } from "@/lib/api/schemas";
import { formatDateTime, formatDuration } from "@/lib/format";
import type { CallOut } from "@/lib/api/schemas";

export default function CallsPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [callStatus, setCallStatus] = useState("");
  const [outcome, setOutcome] = useState("");

  const filters = useMemo(
    () => ({
      page,
      page_size: 25,
      call_status: callStatus || undefined,
      outcome: outcome || undefined,
    }),
    [page, callStatus, outcome]
  );

  const { data, isLoading, isError, error, refetch } = useCalls(filters);

  const columns = useMemo<ColumnDef<CallOut, unknown>[]>(
    () => [
      {
        accessorKey: "business_name",
        header: "İşletme",
        cell: ({ row }) => row.original.business_name ?? "—",
      },
      {
        accessorKey: "status",
        header: "Durum",
        cell: ({ row }) => {
          const meta = callStatusMeta(row.original.status);
          return <StatusBadge label={meta.label} tone={meta.tone} />;
        },
      },
      {
        accessorKey: "outcome",
        header: "Sonuç",
        cell: ({ row }) =>
          row.original.outcome ? (
            (() => {
              const meta = callOutcomeMeta(row.original.outcome!);
              return <StatusBadge label={meta.label} tone={meta.tone} />;
            })()
          ) : (
            <span className="text-[var(--color-text-muted)]">—</span>
          ),
      },
      {
        accessorKey: "duration_seconds",
        header: "Süre",
        cell: ({ row }) => formatDuration(row.original.duration_seconds),
      },
      {
        accessorKey: "started_at",
        header: "Başlangıç",
        cell: ({ row }) => formatDateTime(row.original.started_at),
      },
      { accessorKey: "model", header: "Model" },
    ],
    []
  );

  if (isError) {
    return <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />;
  }

  return (
    <div>
      <PageHeader title="Arama Geçmişi" description={data ? `${data.total} arama` : undefined} />
      <FilterBar>
        <Select
          value={callStatus}
          onChange={(e) => {
            setPage(1);
            setCallStatus(e.target.value);
          }}
          className="max-w-[180px]"
        >
          <option value="">Tüm Durumlar</option>
          {callStatusValues.map((s) => (
            <option key={s} value={s}>
              {callStatusMeta(s).label}
            </option>
          ))}
        </Select>
        <Select
          value={outcome}
          onChange={(e) => {
            setPage(1);
            setOutcome(e.target.value);
          }}
          className="max-w-[200px]"
        >
          <option value="">Tüm Sonuçlar</option>
          {callOutcomeValues.map((o) => (
            <option key={o} value={o}>
              {callOutcomeMeta(o).label}
            </option>
          ))}
        </Select>
      </FilterBar>
      <DataTable
        columns={columns}
        data={data?.items ?? []}
        isLoading={isLoading}
        emptyTitle="Arama bulunamadı"
        onRowClick={(row) => router.push(`/calls/${row.id}`)}
        getRowId={(row) => row.id}
      />
      {data && (
        <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
      )}
    </div>
  );
}
