"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL } from "@/lib/api/client";
import { liveEventEnvelopeSchema, type LiveEventEnvelope } from "@/lib/api/schemas";

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed";

const MAX_BACKOFF_MS = 30_000;
const BASE_BACKOFF_MS = 1_000;
const RECENT_EVENT_BUFFER = 25;

/**
 * `/api/live/events` (services/api/app/api/routes/live.py) SSE akışına bağlanır.
 *
 * Backend event'i bir "message" SSE event'i olarak, `heartbeat` (20 sn'de bir,
 * bağlantıyı canlı tutmak için) ile birlikte yayınlar (bkz. live.py HEARTBEAT_SECONDS).
 * Olaylar asla tam bir `call`/`lead` nesnesi taşımaz — yalnız değişikliğin
 * OLDUĞUNU bildirir (call_id + type). Bu yüzden bu hook, ilgili React Query
 * anahtarlarını invalidate ederek gerçek veriyi normal REST uçlarından
 * yeniden çeker; SSE payload'ını doğrudan UI state'i olarak KULLANMAZ —
 * böylece SSE şeması ile REST şeması arasında sürüklenme (drift) riski olmaz.
 */
export function useLiveEvents(enabled = true) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [lastEvents, setLastEvents] = useState<LiveEventEnvelope[]>([]);
  const seenRef = useRef<string[]>([]);
  const attemptRef = useRef(0);
  const disposedRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    disposedRef.current = false;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    function scheduleReconnect() {
      if (disposedRef.current) return;
      setStatus("reconnecting");
      const delay = Math.min(BASE_BACKOFF_MS * 2 ** attemptRef.current, MAX_BACKOFF_MS);
      attemptRef.current += 1;
      reconnectTimer = setTimeout(connect, delay);
    }

    function handleMessage(raw: MessageEvent<string>) {
      let parsedJson: unknown;
      try {
        parsedJson = JSON.parse(raw.data);
      } catch {
        return;
      }
      // Aynı JSON metni art arda iki kez gelirse (reconnect replay) yok say.
      if (seenRef.current.includes(raw.data)) return;
      seenRef.current = [...seenRef.current.slice(-RECENT_EVENT_BUFFER + 1), raw.data];

      const result = liveEventEnvelopeSchema.safeParse(parsedJson);
      if (!result.success) return;
      const event = result.data;
      setLastEvents((prev) => [event, ...prev].slice(0, RECENT_EVENT_BUFFER));

      if (event.type === "call_event" || event.type === "call_completed" || event.type === "internal_call_event") {
        queryClient.invalidateQueries({ queryKey: ["calls", "live"] });
        queryClient.invalidateQueries({ queryKey: ["dashboard"] });
        if (event.call_id) {
          queryClient.invalidateQueries({ queryKey: ["calls", "detail", event.call_id] });
        }
      }
      if (event.type === "notification") {
        queryClient.invalidateQueries({ queryKey: ["callbacks"] });
        queryClient.invalidateQueries({ queryKey: ["demo-requests"] });
      }
    }

    function connect() {
      if (disposedRef.current) return;
      setStatus((prev) => (prev === "open" ? prev : "connecting"));
      source = new EventSource(`${API_BASE_URL}/api/live/events`, { withCredentials: true });
      source.addEventListener("message", handleMessage as EventListener);
      source.addEventListener("heartbeat", () => {
        attemptRef.current = 0;
      });
      source.onopen = () => {
        attemptRef.current = 0;
        setStatus("open");
      };
      source.onerror = () => {
        source?.close();
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      disposedRef.current = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      source?.close();
      setStatus("closed");
    };
  }, [queryClient, enabled]);

  return { status, lastEvents };
}
