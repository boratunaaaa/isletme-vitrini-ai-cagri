"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { PageHeader } from "@/components/layout/page-header";
import { FilterBar } from "@/components/ui/filter-bar";
import { Input } from "@/components/ui/input";
import { DataTable } from "@/components/ui/data-table";
import { Pagination } from "@/components/ui/pagination";
import { ErrorState } from "@/components/ui/states";
import { useAuditLogs } from "@/lib/api/system";
import { formatDateTime } from "@/lib/format";
import type { AuditLogOut } from "@/lib/api/schemas";

export default function AuditLogsPage() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const { data, isLoading, isError, error, refetch } = useAuditLogs(page, action || undefined);

  const columns = useMemo<ColumnDef<AuditLogOut, unknown>[]>(
    () => [
      {
        accessorKey: "created_at",
        header: "Zaman",
        cell: ({ row }) => formatDateTime(row.original.created_at),
      },
      { accessorKey: "action", header: "Eylem" },
      { accessorKey: "resource_type", header: "Kaynak Türü", cell: ({ row }) => row.original.resource_type ?? "—" },
      { accessorKey: "resource_id", header: "Kaynak ID", cell: ({ row }) => row.original.resource_id ?? "—" },
      { accessorKey: "ip_address", header: "IP", cell: ({ row }) => row.original.ip_address ?? "—" },
    ],
    []
  );

  if (isError) {
    return <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />;
  }

  return (
    <div>
      <PageHeader title="Audit Log" description={data ? `${data.total} kayıt` : undefined} />
      <FilterBar>
        <Input
          placeholder="Eylem filtrele (ör. leads.update)"
          value={action}
          onChange={(e) => {
            setPage(1);
            setAction(e.target.value);
          }}
          className="max-w-xs"
        />
      </FilterBar>
      <DataTable columns={columns} data={data?.items ?? []} isLoading={isLoading} emptyTitle="Kayıt bulunamadı" />
      {data && (
        <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
      )}
    </div>
  );
}
