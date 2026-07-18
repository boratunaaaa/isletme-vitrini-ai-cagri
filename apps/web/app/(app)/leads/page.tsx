"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { Download, Plus } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { FilterBar } from "@/components/ui/filter-bar";
import { Input, Select } from "@/components/ui/input";
import { DataTable } from "@/components/ui/data-table";
import { Pagination } from "@/components/ui/pagination";
import { StatusBadge } from "@/components/ui/status-badge";
import { MaskedPhone } from "@/components/ui/masked-phone";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/states";
import { useLeadFacets, useLeads, useRevealPhone, downloadLeadsExport } from "@/lib/api/leads";
import { leadPriorityMeta, leadStatusMeta } from "@/lib/enums";
import { leadStatusValues, leadPriorityValues } from "@/lib/api/schemas";
import { formatRelative } from "@/lib/format";
import type { LeadOut } from "@/lib/api/schemas";
import { PermissionGuard } from "@/components/ui/permission-guard";

function RevealCell({ leadId, masked }: { leadId: string; masked: string | null }) {
  const reveal = useRevealPhone(leadId);
  return (
    <MaskedPhone
      masked={masked}
      onReveal={async () => (await reveal.mutateAsync()).phone_e164}
    />
  );
}

export default function LeadsPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("");
  const [city, setCity] = useState("");
  const [leadStatus, setLeadStatus] = useState("");
  const [priority, setPriority] = useState("");

  const filters = useMemo(
    () => ({
      page,
      page_size: 25,
      q: q || undefined,
      sector: sector || undefined,
      city: city || undefined,
      lead_status: leadStatus || undefined,
      priority: priority || undefined,
    }),
    [page, q, sector, city, leadStatus, priority]
  );

  const { data, isLoading, isError, error, refetch } = useLeads(filters);
  const { data: facets } = useLeadFacets();

  const columns = useMemo<ColumnDef<LeadOut, unknown>[]>(
    () => [
      {
        accessorKey: "business_name",
        header: "İşletme",
        cell: ({ row }) => (
          <div>
            <p className="font-medium">{row.original.business_name}</p>
            <p className="text-xs text-[var(--color-text-muted)]">{row.original.sector ?? "—"}</p>
          </div>
        ),
      },
      {
        id: "location",
        header: "Konum",
        cell: ({ row }) => (
          <span className="text-[var(--color-text-secondary)]">
            {[row.original.city, row.original.district].filter(Boolean).join(" / ") || "—"}
          </span>
        ),
      },
      {
        id: "phone",
        header: "Telefon",
        cell: ({ row }) => <RevealCell leadId={row.original.id} masked={row.original.phone_masked} />,
      },
      {
        accessorKey: "status",
        header: "Durum",
        cell: ({ row }) => {
          const meta = leadStatusMeta(row.original.status);
          return <StatusBadge label={meta.label} tone={meta.tone} />;
        },
      },
      {
        accessorKey: "priority",
        header: "Öncelik",
        cell: ({ row }) => {
          const meta = leadPriorityMeta(row.original.priority);
          return <StatusBadge label={meta.label} tone={meta.tone} />;
        },
      },
      {
        accessorKey: "last_contacted_at",
        header: "Son İletişim",
        cell: ({ row }) => (
          <span className="text-xs text-[var(--color-text-muted)]">
            {formatRelative(row.original.last_contacted_at)}
          </span>
        ),
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
        title="Lead'ler"
        description={data ? `${data.total} kayıt` : undefined}
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                const blob = await downloadLeadsExport();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "leads-masked.csv";
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              <Download className="h-4 w-4" /> Dışa Aktar
            </Button>
            <PermissionGuard permission="leads:import">
              <Button size="sm" onClick={() => router.push("/leads/import")}>
                <Plus className="h-4 w-4" /> İçe Aktar
              </Button>
            </PermissionGuard>
          </>
        }
      />
      <FilterBar>
        <Input
          placeholder="Ara (işletme, adres, sektör)…"
          value={q}
          onChange={(e) => {
            setPage(1);
            setQ(e.target.value);
          }}
          className="max-w-xs"
        />
        <Select
          value={sector}
          onChange={(e) => {
            setPage(1);
            setSector(e.target.value);
          }}
          className="max-w-[160px]"
        >
          <option value="">Tüm Sektörler</option>
          {facets?.sectors.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
        <Select
          value={city}
          onChange={(e) => {
            setPage(1);
            setCity(e.target.value);
          }}
          className="max-w-[160px]"
        >
          <option value="">Tüm Şehirler</option>
          {facets?.cities.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
        <Select
          value={leadStatus}
          onChange={(e) => {
            setPage(1);
            setLeadStatus(e.target.value);
          }}
          className="max-w-[160px]"
        >
          <option value="">Tüm Durumlar</option>
          {leadStatusValues.map((s) => (
            <option key={s} value={s}>
              {leadStatusMeta(s).label}
            </option>
          ))}
        </Select>
        <Select
          value={priority}
          onChange={(e) => {
            setPage(1);
            setPriority(e.target.value);
          }}
          className="max-w-[140px]"
        >
          <option value="">Tüm Öncelikler</option>
          {leadPriorityValues.map((p) => (
            <option key={p} value={p}>
              {leadPriorityMeta(p).label}
            </option>
          ))}
        </Select>
      </FilterBar>
      <DataTable
        columns={columns}
        data={data?.items ?? []}
        isLoading={isLoading}
        emptyTitle="Lead bulunamadı"
        emptyMessage="Filtreleri değiştirin veya yeni lead içe aktarın."
        onRowClick={(row) => router.push(`/leads/${row.id}`)}
        getRowId={(row) => row.id}
      />
      {data && (
        <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
      )}
    </div>
  );
}
