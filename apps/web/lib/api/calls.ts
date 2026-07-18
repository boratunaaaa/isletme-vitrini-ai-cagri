"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import {
  callDetailOutSchema,
  callOutSchema,
  okResponseSchema,
  pageSchema,
  type CallInitiateInput,
  type QualityMetricsInput,
} from "./schemas";
import { z } from "zod";

export type CallListFilters = {
  page?: number;
  page_size?: number;
  call_status?: string;
  outcome?: string;
  campaign_id?: string;
  lead_id?: string;
};

export const callKeys = {
  all: ["calls"] as const,
  list: (filters: CallListFilters) => ["calls", "list", filters] as const,
  live: ["calls", "live"] as const,
  detail: (id: string) => ["calls", "detail", id] as const,
};

export function useCalls(filters: CallListFilters) {
  return useQuery({
    queryKey: callKeys.list(filters),
    queryFn: () =>
      apiRequest("/api/calls", pageSchema(callOutSchema), {
        searchParams: { ...filters, page: filters.page ?? 1, page_size: filters.page_size ?? 50 },
      }),
    placeholderData: (prev) => prev,
  });
}

export function useLiveCalls() {
  return useQuery({
    queryKey: callKeys.live,
    queryFn: () => apiRequest("/api/calls/live", z.array(callOutSchema)),
    refetchInterval: 5_000,
  });
}

export function useCall(callId: string | undefined) {
  return useQuery({
    queryKey: callKeys.detail(callId ?? ""),
    queryFn: () => apiRequest(`/api/calls/${callId}`, callDetailOutSchema),
    enabled: Boolean(callId),
  });
}

export function useInitiateCall() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CallInitiateInput) =>
      apiRequest("/api/calls", callOutSchema, { method: "POST", body: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: callKeys.all });
      queryClient.invalidateQueries({ queryKey: callKeys.live });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useHangupCall(callId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest(`/api/calls/${callId}/hangup`, okResponseSchema, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: callKeys.all });
      queryClient.invalidateQueries({ queryKey: callKeys.live });
      queryClient.invalidateQueries({ queryKey: callKeys.detail(callId) });
    },
  });
}

export function useRateCallQuality(callId: string) {
  return useMutation({
    mutationFn: (input: QualityMetricsInput) =>
      apiRequest(`/api/calls/${callId}/quality`, okResponseSchema, {
        method: "POST",
        body: input,
      }),
  });
}
