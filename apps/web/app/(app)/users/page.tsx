"use client";

import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as Dialog from "@radix-ui/react-dialog";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus, UserX } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/ui/data-table";
import { Pagination } from "@/components/ui/pagination";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useCreateUser, useDeactivateUser, useUpdateUser, useUsers } from "@/lib/api/users";
import { roleMeta } from "@/lib/enums";
import { roleValues, userCreateSchema, type UserCreateInput, type UserOut } from "@/lib/api/schemas";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/client";
import { useSession } from "@/lib/auth/session-context";

function CreateUserDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const createUser = useCreateUser();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UserCreateInput>({ resolver: zodResolver(userCreateSchema), defaultValues: { role: "viewer" } });

  async function onSubmit(values: UserCreateInput) {
    setFormError(null);
    try {
      await createUser.mutateAsync(values);
      reset();
      onOpenChange(false);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Kullanıcı oluşturulamadı");
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-bg-surface-raised)] p-5 shadow-xl focus:outline-none">
          <Dialog.Title className="text-sm font-semibold text-[var(--color-text-primary)]">
            Yeni Kullanıcı
          </Dialog.Title>
          <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-3">
            <div>
              <Label htmlFor="full_name">Ad Soyad</Label>
              <Input id="full_name" {...register("full_name")} />
              {errors.full_name && <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.full_name.message}</p>}
            </div>
            <div>
              <Label htmlFor="email">E-posta</Label>
              <Input id="email" type="email" {...register("email")} />
              {errors.email && <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.email.message}</p>}
            </div>
            <div>
              <Label htmlFor="password">Parola (en az 10 karakter)</Label>
              <Input id="password" type="password" {...register("password")} />
              {errors.password && <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.password.message}</p>}
            </div>
            <div>
              <Label htmlFor="role">Rol</Label>
              <Select id="role" {...register("role")}>
                {roleValues.map((r) => (
                  <option key={r} value={r}>
                    {roleMeta(r).label}
                  </option>
                ))}
              </Select>
            </div>
            {formError && <p className="text-xs text-[var(--color-danger-400)]">{formError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <Dialog.Close asChild>
                <Button variant="secondary" size="sm" type="button">
                  Vazgeç
                </Button>
              </Dialog.Close>
              <Button size="sm" type="submit" loading={isSubmitting || createUser.isPending}>
                Oluştur
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function UsersPage() {
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [pendingDeactivate, setPendingDeactivate] = useState<string | null>(null);
  const { data, isLoading, isError, error, refetch } = useUsers(page);
  const updateUser = useUpdateUser();
  const deactivateUser = useDeactivateUser();
  const { user: me } = useSession();

  const columns = useMemo<ColumnDef<UserOut, unknown>[]>(
    () => [
      { accessorKey: "full_name", header: "Ad Soyad" },
      { accessorKey: "email", header: "E-posta" },
      {
        accessorKey: "role",
        header: "Rol",
        cell: ({ row }) => {
          return (
            <Select
              value={row.original.role}
              disabled={row.original.id === me?.id}
              onChange={(e) =>
                updateUser.mutate({ id: row.original.id, input: { role: e.target.value as never } })
              }
              className="h-7 w-auto py-0 text-xs"
            >
              {roleValues.map((r) => (
                <option key={r} value={r}>
                  {roleMeta(r).label}
                </option>
              ))}
            </Select>
          );
        },
      },
      {
        accessorKey: "is_active",
        header: "Durum",
        cell: ({ row }) => (
          <StatusBadge label={row.original.is_active ? "Aktif" : "Pasif"} tone={row.original.is_active ? "success" : "neutral"} />
        ),
      },
      {
        accessorKey: "last_login_at",
        header: "Son Giriş",
        cell: ({ row }) => formatDateTime(row.original.last_login_at),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) =>
          row.original.is_active &&
          row.original.id !== me?.id && (
            <Button variant="ghost" size="icon" onClick={() => setPendingDeactivate(row.original.id)}>
              <UserX className="h-4 w-4 text-[var(--color-danger-400)]" />
            </Button>
          ),
      },
    ],
    [me?.id, updateUser]
  );

  if (isError) {
    return <ErrorState message={error instanceof Error ? error.message : undefined} onRetry={() => refetch()} />;
  }

  return (
    <div>
      <PageHeader
        title="Kullanıcılar"
        description={data ? `${data.total} kullanıcı` : undefined}
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Yeni Kullanıcı
          </Button>
        }
      />
      <DataTable columns={columns} data={data?.items ?? []} isLoading={isLoading} getRowId={(row) => row.id} />
      {data && (
        <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
      )}
      <CreateUserDialog open={createOpen} onOpenChange={setCreateOpen} />
      <ConfirmDialog
        open={Boolean(pendingDeactivate)}
        onOpenChange={(open) => !open && setPendingDeactivate(null)}
        title="Kullanıcıyı pasifleştir"
        description="Kullanıcı silinmez, yalnız pasifleştirilir ve tüm oturumları sonlandırılır."
        confirmLabel="Pasifleştir"
        destructive
        loading={deactivateUser.isPending}
        onConfirm={async () => {
          if (pendingDeactivate) await deactivateUser.mutateAsync(pendingDeactivate);
          setPendingDeactivate(null);
        }}
      />
    </div>
  );
}
