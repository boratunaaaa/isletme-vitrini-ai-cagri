"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import {
  campaignOutSchema,
  campaignStatsSchema,
  okResponseSchema,
  pageSchema,
  type CampaignCreateInput,
  type CampaignUpdateInput,
} from "./schemas";

export const campaignKeys = {
  all: ["campaigns"] as const,
  list: (page: number, pageSize: number) => ["campaigns", "list", page, pageSize] as const,
  detail: (id: string) => ["campaigns", "detail", id] as const,
  stats: (id: string) => ["campaigns", "stats", id] as const,
};

export function useCampaigns(page = 1, pageSize = 50) {
  return useQuery({
    queryKey: campaignKeys.list(page, pageSize),
    queryFn: () =>
      apiRequest("/api/campaigns", pageSchema(campaignOutSchema), {
        searchParams: { page, page_size: pageSize },
      }),
    placeholderData: (prev) => prev,
  });
}

export function useCampaign(campaignId: string | undefined) {
  return useQuery({
    queryKey: campaignKeys.detail(campaignId ?? ""),
    queryFn: () => apiRequest(`/api/campaigns/${campaignId}`, campaignOutSchema),
    enabled: Boolean(campaignId),
  });
}

export function useCampaignStats(campaignId: string | undefined) {
  return useQuery({
    queryKey: campaignKeys.stats(campaignId ?? ""),
    queryFn: () => apiRequest(`/api/campaigns/${campaignId}/stats`, campaignStatsSchema),
    enabled: Boolean(campaignId),
    refetchInterval: 15_000,
  });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CampaignCreateInput) =>
      apiRequest("/api/campaigns", campaignOutSchema, { method: "POST", body: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: campaignKeys.all });
    },
  });
}

export function useUpdateCampaign(campaignId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CampaignUpdateInput) =>
      apiRequest(`/api/campaigns/${campaignId}`, campaignOutSchema, {
        method: "PATCH",
        body: input,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(campaignKeys.detail(campaignId), data);
      queryClient.invalidateQueries({ queryKey: campaignKeys.all });
    },
  });
}

export function useAddLeadsToCampaign(campaignId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      lead_ids?: string[] | null;
      sector?: string | null;
      city?: string | null;
      district?: string | null;
      status?: string | null;
      limit?: number;
    }) =>
      apiRequest(`/api/campaigns/${campaignId}/leads`, okResponseSchema, {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: campaignKeys.stats(campaignId) });
    },
  });
}

export function useChangeCampaignStatus(campaignId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: string) =>
      apiRequest(`/api/campaigns/${campaignId}/status`, campaignOutSchema, {
        method: "POST",
        body: { action },
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(campaignKeys.detail(campaignId), data);
      queryClient.invalidateQueries({ queryKey: campaignKeys.all });
      queryClient.invalidateQueries({ queryKey: campaignKeys.stats(campaignId) });
    },
  });
}
