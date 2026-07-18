"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, apiRequestRaw } from "./client";
import {
  leadFacetsSchema,
  leadNoteOutSchema,
  leadOutSchema,
  pageSchema,
  phoneRevealResponseSchema,
  tagOutSchema,
  type LeadNoteCreateInput,
  type LeadUpdateInput,
} from "./schemas";
import { z } from "zod";

export type LeadListFilters = {
  page?: number;
  page_size?: number;
  q?: string;
  sector?: string;
  city?: string;
  district?: string;
  lead_status?: string;
  priority?: string;
  has_phone?: boolean;
  assigned_user_id?: string;
};

export const leadKeys = {
  all: ["leads"] as const,
  list: (filters: LeadListFilters) => ["leads", "list", filters] as const,
  detail: (id: string) => ["leads", "detail", id] as const,
  facets: ["leads", "facets"] as const,
  tags: ["leads", "tags"] as const,
  notes: (id: string) => ["leads", "notes", id] as const,
};

export function useLeads(filters: LeadListFilters) {
  return useQuery({
    queryKey: leadKeys.list(filters),
    queryFn: () =>
      apiRequest("/api/leads", pageSchema(leadOutSchema), {
        searchParams: { ...filters, page: filters.page ?? 1, page_size: filters.page_size ?? 50 },
      }),
    placeholderData: (prev) => prev,
  });
}

export function useLead(leadId: string | undefined) {
  return useQuery({
    queryKey: leadKeys.detail(leadId ?? ""),
    queryFn: () => apiRequest(`/api/leads/${leadId}`, leadOutSchema),
    enabled: Boolean(leadId),
  });
}

export function useLeadFacets() {
  return useQuery({
    queryKey: leadKeys.facets,
    queryFn: () => apiRequest("/api/leads/facets", leadFacetsSchema),
    staleTime: 5 * 60_000,
  });
}

export function useTags() {
  return useQuery({
    queryKey: leadKeys.tags,
    queryFn: () => apiRequest("/api/leads/tags/all", z.array(tagOutSchema)),
    staleTime: 5 * 60_000,
  });
}

export function useUpdateLead(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: LeadUpdateInput) =>
      apiRequest(`/api/leads/${leadId}`, leadOutSchema, { method: "PATCH", body: input }),
    onSuccess: (data) => {
      queryClient.setQueryData(leadKeys.detail(leadId), data);
      queryClient.invalidateQueries({ queryKey: leadKeys.all });
    },
  });
}

export function useRevealPhone(leadId: string) {
  return useMutation({
    mutationFn: () =>
      apiRequest(`/api/leads/${leadId}/reveal-phone`, phoneRevealResponseSchema, {
        method: "POST",
      }),
  });
}

export function useLeadNotes(leadId: string | undefined) {
  return useQuery({
    queryKey: leadKeys.notes(leadId ?? ""),
    queryFn: () => apiRequest(`/api/leads/${leadId}/notes`, z.array(leadNoteOutSchema)),
    enabled: Boolean(leadId),
  });
}

export function useAddLeadNote(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: LeadNoteCreateInput) =>
      apiRequest(`/api/leads/${leadId}/notes`, leadNoteOutSchema, {
        method: "POST",
        body: input,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadKeys.notes(leadId) });
    },
  });
}

export function useAssignLeadTags(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tagIds: string[]) =>
      apiRequest(`/api/leads/${leadId}/tags`, leadOutSchema, {
        method: "POST",
        body: { tag_ids: tagIds },
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(leadKeys.detail(leadId), data);
    },
  });
}

/** CSV export tarayıcıda indirilir; telefonlar backend'de zaten maskeli döner. */
export async function downloadLeadsExport(): Promise<Blob> {
  const response = await apiRequestRaw("/api/leads/export", { method: "POST" });
  return response.blob();
}
