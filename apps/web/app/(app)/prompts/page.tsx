"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { FileText, Plus, CheckCircle2 } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/states";
import { PermissionGuard } from "@/components/ui/permission-guard";
import { useActivatePrompt, useCreatePrompt, usePrompts } from "@/lib/api/content";
import { promptVersionCreateSchema, type PromptVersionCreateInput } from "@/lib/api/schemas";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/client";

export default function PromptsPage() {
  const { data, isLoading, isError, error, refetch } = usePrompts();
  const createPrompt = useCreatePrompt();
  const activate = useActivatePrompt();
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PromptVersionCreateInput>({ resolver: zodResolver(promptVersionCreateSchema) });

  async function onSubmit(values: PromptVersionCreateInput) {
    setFormError(null);
    try {
      await createPrompt.mutateAsync(values);
      reset();
      setShowForm(false);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Versiyon oluşturulamadı");
    }
  }

  return (
    <div>
      <PageHeader
        title="Prompt Versiyonları"
        description={data ? `${data.length} versiyon` : undefined}
        actions={
          <PermissionGuard permission="prompt:write">
            <Button size="sm" onClick={() => setShowForm((v) => !v)}>
              <Plus className="h-4 w-4" /> Yeni Versiyon
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
            <div>
              <Label htmlFor="name">İsim</Label>
              <Input id="name" {...register("name")} />
              {errors.name && <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.name.message}</p>}
            </div>
            <div>
              <Label htmlFor="system_prompt">Sistem Promptu</Label>
              <Textarea id="system_prompt" rows={4} {...register("system_prompt")} />
            </div>
            <div>
              <Label htmlFor="opening_script">Açılış Cümlesi</Label>
              <Textarea id="opening_script" rows={2} {...register("opening_script")} />
            </div>
            <div>
              <Label htmlFor="objective">Amaç</Label>
              <Textarea id="objective" rows={2} {...register("objective")} />
            </div>
            <div>
              <Label htmlFor="objection_rules">İtiraz Kuralları</Label>
              <Textarea id="objection_rules" rows={3} {...register("objection_rules")} />
            </div>
            {formError && <p className="text-xs text-[var(--color-danger-400)]">{formError}</p>}
            <Button type="submit" size="sm" loading={isSubmitting || createPrompt.isPending}>
              Kaydet
            </Button>
          </form>
        )}

        {isLoading && <LoadingState />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />
        )}
        {data && data.length === 0 && <EmptyState icon={FileText} title="Prompt versiyonu yok" />}
        {data && data.length > 0 && (
          <div className="space-y-2">
            {data.map((prompt) => (
              <div
                key={prompt.id}
                className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-[var(--color-text-primary)]">{prompt.name}</p>
                    {prompt.is_active && <StatusBadge label="Aktif" tone="success" />}
                  </div>
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                    {formatDateTime(prompt.created_at)}
                  </p>
                </div>
                {!prompt.is_active && (
                  <PermissionGuard permission="prompt:write">
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={activate.isPending}
                      onClick={() => activate.mutate(prompt.id)}
                    >
                      <CheckCircle2 className="h-4 w-4" /> Aktif Et
                    </Button>
                  </PermissionGuard>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
