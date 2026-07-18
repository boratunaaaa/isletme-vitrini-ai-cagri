"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import {
  kbEntryOutSchema,
  okResponseSchema,
  promptVersionOutSchema,
  type KbEntryCreateInput,
  type KbEntryUpdateInput,
  type PromptVersionCreateInput,
} from "./schemas";
import { z } from "zod";

export const contentKeys = {
  kb: ["kb"] as const,
  prompts: ["prompts"] as const,
};

export function useKbEntries() {
  return useQuery({
    queryKey: contentKeys.kb,
    queryFn: () => apiRequest("/api/kb", z.array(kbEntryOutSchema)),
  });
}

export function useCreateKbEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: KbEntryCreateInput) =>
      apiRequest("/api/kb", kbEntryOutSchema, { method: "POST", body: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: contentKeys.kb }),
  });
}

export function useUpdateKbEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: KbEntryUpdateInput }) =>
      apiRequest(`/api/kb/${id}`, kbEntryOutSchema, { method: "PATCH", body: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: contentKeys.kb }),
  });
}

export function useDeactivateKbEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/kb/${id}`, okResponseSchema, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: contentKeys.kb }),
  });
}

export function usePrompts() {
  return useQuery({
    queryKey: contentKeys.prompts,
    queryFn: () => apiRequest("/api/prompts", z.array(promptVersionOutSchema)),
  });
}

export function useCreatePrompt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PromptVersionCreateInput) =>
      apiRequest("/api/prompts", promptVersionOutSchema, { method: "POST", body: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: contentKeys.prompts }),
  });
}

export function useActivatePrompt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/prompts/${id}/activate`, promptVersionOutSchema, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: contentKeys.prompts }),
  });
}
