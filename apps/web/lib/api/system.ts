"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import {
  auditLogOutSchema,
  dashboardStatsSchema,
  pageSchema,
  pricingOutSchema,
  settingItemSchema,
  type PricingUpdateInput,
  type SettingUpdateInput,
} from "./schemas";
import { z } from "zod";

export const systemKeys = {
  dashboard: ["dashboard", "stats"] as const,
  pricing: ["pricing"] as const,
  settings: ["settings"] as const,
  auditLogs: (page: number, action?: string) => ["audit-logs", page, action] as const,
};

export function useDashboardStats() {
  return useQuery({
    queryKey: systemKeys.dashboard,
    queryFn: () => apiRequest("/api/dashboard/stats", dashboardStatsSchema),
    refetchInterval: 30_000,
  });
}

export function usePricing() {
  return useQuery({
    queryKey: systemKeys.pricing,
    queryFn: () => apiRequest("/api/pricing", z.array(pricingOutSchema)),
  });
}

export function useUpdatePricing() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: PricingUpdateInput }) =>
      apiRequest(`/api/pricing/${id}`, pricingOutSchema, { method: "PATCH", body: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: systemKeys.pricing }),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: systemKeys.settings,
    queryFn: () => apiRequest("/api/settings", z.array(settingItemSchema)),
  });
}

export function useUpdateSetting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SettingUpdateInput) =>
      apiRequest("/api/settings", settingItemSchema, { method: "PATCH", body: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: systemKeys.settings });
      queryClient.invalidateQueries({ queryKey: systemKeys.dashboard });
    },
  });
}

export function useAuditLogs(page = 1, action?: string) {
  return useQuery({
    queryKey: systemKeys.auditLogs(page, action),
    queryFn: () =>
      apiRequest("/api/audit-logs", pageSchema(auditLogOutSchema), {
        searchParams: { page, page_size: 50, action },
      }),
    placeholderData: (prev) => prev,
  });
}
