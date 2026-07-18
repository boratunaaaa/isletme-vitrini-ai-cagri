"use client";

import { useEffect, useRef, useState, Suspense } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter, useSearchParams } from "next/navigation";
import { Phone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { useLogin, useMe } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { getSafeRedirectPath } from "@/lib/auth/safe-redirect";
import { loginRequestSchema, type LoginRequestInput } from "@/lib/api/schemas";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();
  const [formError, setFormError] = useState<string | null>(null);

  // DÜZELTME (CODEX_AUDIT_PHASE_5_FRONTEND.md YÜKSEK-1): `/login`'den
  // dashboard'a yönlendirme artık middleware'de çerez varlığına bakarak değil,
  // burada GERÇEK `/api/auth/me` sonucuna bakarak yapılıyor. Süresi dolmuş
  // bir çerezle bu sorgu 401 döner (`retry:false`) ve `data` hiç dolmaz —
  // bu durumda hiçbir yönlendirme olmaz, form normal şekilde render edilir.
  const { data: session } = useMe();
  const redirectedRef = useRef(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginRequestInput>({ resolver: zodResolver(loginRequestSchema) });

  useEffect(() => {
    if (session && !redirectedRef.current) {
      redirectedRef.current = true;
      router.replace(getSafeRedirectPath(searchParams.get("next")));
    }
  }, [session, router, searchParams]);

  async function onSubmit(values: LoginRequestInput) {
    setFormError(null);
    try {
      await login.mutateAsync(values);
      router.replace(getSafeRedirectPath(searchParams.get("next")));
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError("Beklenmeyen bir hata oluştu");
      }
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-[var(--color-bg-canvas)] px-4">
      <div className="w-full max-w-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-[var(--color-brand-500)]">
            <Phone className="h-5 w-5 text-white" />
          </div>
          <h1 className="text-base font-semibold text-[var(--color-text-primary)]">
            İşletme Vitrini AI Çağrı Merkezi
          </h1>
          <p className="text-sm text-[var(--color-text-muted)]">Yönetim paneline giriş yapın</p>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
          <div>
            <Label htmlFor="email">E-posta</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              {...register("email")}
              aria-invalid={Boolean(errors.email)}
            />
            {errors.email && (
              <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.email.message}</p>
            )}
          </div>
          <div>
            <Label htmlFor="password">Parola</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register("password")}
              aria-invalid={Boolean(errors.password)}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-[var(--color-danger-400)]">{errors.password.message}</p>
            )}
          </div>
          {formError && (
            <p role="alert" className="rounded-md bg-[var(--color-danger-bg)] px-3 py-2 text-sm text-[var(--color-danger-400)]">
              {formError}
            </p>
          )}
          <Button type="submit" className="w-full" loading={isSubmitting || login.isPending}>
            Giriş Yap
          </Button>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
