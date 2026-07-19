"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { Phone, Plus } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Label, Select, Textarea } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { MaskedPhone } from "@/components/ui/masked-phone";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import {
  useLead,
  useUpdateLead,
  useRevealPhone,
  useLeadNotes,
  useAddLeadNote,
} from "@/lib/api/leads";
import { useInitiateCall } from "@/lib/api/calls";
import { leadPriorityMeta, leadStatusMeta } from "@/lib/enums";
import { leadPriorityValues, leadStatusValues } from "@/lib/api/schemas";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/client";

export default function LeadDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data: lead, isLoading, isError, error, refetch } = useLead(id);
  const { data: notes } = useLeadNotes(id);
  const updateLead = useUpdateLead(id);
  const reveal = useRevealPhone(id);
  const addNote = useAddLeadNote(id);
  const initiateCall = useInitiateCall();
  const [noteContent, setNoteContent] = useState("");
  const [callError, setCallError] = useState<string | null>(null);

  if (isLoading) return <LoadingState />;
  if (isError || !lead) {
    return <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />;
  }

  const statusMeta = leadStatusMeta(lead.status);
  const priorityMeta = leadPriorityMeta(lead.priority);

  return (
    <div>
      <PageHeader
        title={lead.business_name}
        description={[lead.sector, lead.city, lead.district].filter(Boolean).join(" · ")}
        actions={
          <PermissionGuard permission="call:initiate">
            <Button
              size="sm"
              loading={initiateCall.isPending}
              disabled={!lead.has_phone}
              onClick={async () => {
                setCallError(null);
                try {
                  const call = await initiateCall.mutateAsync({
                    lead_id: lead.id,
                    idempotency_key: crypto.randomUUID(),
                  });
                  router.push(`/calls/${call.id}`);
                } catch (err) {
                  setCallError(err instanceof ApiError ? err.message : "Arama başlatılamadı");
                }
              }}
            >
              <Phone className="h-4 w-4" /> Ara
            </Button>
          </PermissionGuard>
        }
      />
      <div className="grid grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {callError && (
            <p className="rounded-md bg-[var(--color-danger-bg)] px-3 py-2 text-sm text-[var(--color-danger-400)]">
              {callError}
            </p>
          )}
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatusBadge label={statusMeta.label} tone={statusMeta.tone} />
              <StatusBadge label={priorityMeta.label} tone={priorityMeta.tone} />
            </div>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Telefon</dt>
                <dd>
                  <MaskedPhone
                    masked={lead.phone_masked}
                    onReveal={async () => (await reveal.mutateAsync()).phone_e164}
                  />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Website</dt>
                <dd>{lead.website ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Puan</dt>
                <dd>{lead.rating ?? "—"} ({lead.review_count ?? 0} yorum)</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Kaynak</dt>
                <dd>{lead.source}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Son İletişim</dt>
                <dd>{formatDateTime(lead.last_contacted_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Oluşturulma</dt>
                <dd>{formatDateTime(lead.created_at)}</dd>
              </div>
            </dl>
          </div>

          <PermissionGuard permission="leads:write">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
              <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">Durumu Güncelle</h2>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="status">Durum</Label>
                  <Select
                    id="status"
                    value={lead.status}
                    onChange={(e) => updateLead.mutate({ status: e.target.value as never })}
                  >
                    {leadStatusValues.map((s) => (
                      <option key={s} value={s}>
                        {leadStatusMeta(s).label}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <Label htmlFor="priority">Öncelik</Label>
                  <Select
                    id="priority"
                    value={lead.priority}
                    onChange={(e) => updateLead.mutate({ priority: e.target.value as never })}
                  >
                    {leadPriorityValues.map((p) => (
                      <option key={p} value={p}>
                        {leadPriorityMeta(p).label}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
            </div>
          </PermissionGuard>
        </div>

        <div className="space-y-3">
          <h2 className="text-sm font-medium text-[var(--color-text-primary)]">Notlar</h2>
          <PermissionGuard permission="leads:write">
            <div className="space-y-2">
              <Textarea
                placeholder="Not ekle…"
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
              />
              <Button
                size="sm"
                variant="secondary"
                loading={addNote.isPending}
                disabled={!noteContent.trim()}
                onClick={async () => {
                  await addNote.mutateAsync({ content: noteContent });
                  setNoteContent("");
                }}
              >
                <Plus className="h-4 w-4" /> Not Ekle
              </Button>
            </div>
          </PermissionGuard>
          <ul className="space-y-2">
            {(notes ?? []).map((note) => (
              <li key={note.id} className="rounded-md border border-[var(--color-border)] p-3 text-sm">
                <p className="text-[var(--color-text-primary)]">{note.content}</p>
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  {formatDateTime(note.created_at)}
                </p>
              </li>
            ))}
            {notes?.length === 0 && (
              <p className="text-xs text-[var(--color-text-muted)]">Henüz not yok.</p>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
