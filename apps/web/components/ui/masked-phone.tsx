"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "./button";
import { useSession } from "@/lib/auth/session-context";

/**
 * Ham numara ASLA client tarafında tutulmaz/cachelenmez — her "göster"
 * tıklamasında `/api/leads/{id}/reveal-phone` tazeden çağrılır (backend her
 * çağrıyı audit'ler, bkz. leads.py::reveal_phone). Bileşen unmount olunca
 * state ile birlikte numara da bellekten düşer.
 */
export function MaskedPhone({
  masked,
  onReveal,
}: {
  masked: string | null;
  onReveal: () => Promise<string>;
}) {
  const { hasPermission } = useSession();
  const [revealed, setRevealed] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!masked) return <span className="text-[var(--color-text-muted)]">Telefon yok</span>;
  if (!hasPermission("phone:reveal")) {
    return <span className="tabular-nums text-[var(--color-text-secondary)]">{masked}</span>;
  }

  return (
    <span className="inline-flex items-center gap-2">
      <span className="tabular-nums text-[var(--color-text-primary)]">{revealed ?? masked}</span>
      <Button
        variant="ghost"
        size="icon"
        loading={loading}
        aria-label={revealed ? "Numarayı gizle" : "Numarayı göster"}
        onClick={async () => {
          if (revealed) {
            setRevealed(null);
            return;
          }
          setLoading(true);
          try {
            setRevealed(await onReveal());
          } finally {
            setLoading(false);
          }
        }}
      >
        {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </Button>
    </span>
  );
}
