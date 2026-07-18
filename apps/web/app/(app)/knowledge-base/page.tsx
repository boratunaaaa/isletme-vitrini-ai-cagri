"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { BookOpen, Plus, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import { useCreateKbEntry, useDeactivateKbEntry, useKbEntries } from "@/lib/api/content";
import { kbEntryCreateSchema, type KbEntryCreateInput } from "@/lib/api/schemas";
import { ApiError } from "@/lib/api/client";

export default function KnowledgeBasePage() {
  const { data, isLoading, isError, error, refetch } = useKbEntries();
  const createEntry = useCreateKbEntry();
  const deactivate = useDeactivateKbEntry();
  const [formError, setFormError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<KbEntryCreateInput>({
    resolver: zodResolver(kbEntryCreateSchema),
    defaultValues: { is_active: true },
  });

  async function onSubmit(values: KbEntryCreateInput) {
    setFormError(null);
    try {
      await createEntry.mutateAsync(values);
      reset();
      setShowForm(false);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Kayıt oluşturulamadı");
    }
  }

  return (
    <div>
      <PageHeader
        title="Bilgi Bankası"
        description={data ? `${data.length} kayıt` : undefined}
        actions={
          <PermissionGuard permission="kb:write">
            <Button size="sm" onClick={() => setShowForm((v) => !v)}>
              <Plus className="h-4 w-4" /> Yeni Kayıt
            </Button>
          </PermissionGuard>
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        {showForm && (
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4"
          >
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="category">Kategori</Label>
                <Input id="category" {...register("category")} />
              </div>
              <div>
                <Label htmlFor="title">Başlık</Label>
                <Input id="title" {...register("title")} />
              </div>
            </div>
            <div>
              <Label htmlFor="content">İçerik</Label>
              <Textarea id="content" rows={4} {...register("content")} />
              {errors.content && (
                <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.content.message}</p>
              )}
            </div>
            {formError && <p className="text-xs text-[var(--color-danger-400)]">{formError}</p>}
            <Button type="submit" size="sm" loading={isSubmitting || createEntry.isPending}>
              Kaydet
            </Button>
          </form>
        )}

        {isLoading && <LoadingState />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
        )}
        {data && data.length === 0 && <EmptyState icon={BookOpen} title="Bilgi bankası boş" />}
        {data && data.length > 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {data.map((entry) => (
              <div key={entry.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
                <div className="mb-2 flex items-center justify-between">
                  <StatusBadge label={entry.category} tone="info" />
                  <div className="flex items-center gap-2">
                    {!entry.is_active && <StatusBadge label="Pasif" tone="neutral" />}
                    <PermissionGuard permission="kb:write">
                      <Button variant="ghost" size="icon" onClick={() => deactivate.mutate(entry.id)}>
                        <Trash2 className="h-4 w-4 text-[var(--color-danger-400)]" />
                      </Button>
                    </PermissionGuard>
                  </div>
                </div>
                <h3 className="text-sm font-medium text-[var(--color-text-primary)]">{entry.title}</h3>
                <p className="mt-1 text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap">
                  {entry.content}
                </p>
                <p className="mt-2 text-xs text-[var(--color-text-muted)]">v{entry.version}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
