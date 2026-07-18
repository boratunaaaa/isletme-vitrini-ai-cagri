"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import {
  callbackOutSchema,
  demoRequestOutSchema,
  okResponseSchema,
  suppressionOutSchema,
  waLinkResponseSchema,
  type CallbackUpdateInput,
  type SuppressionCreateInput,
} from "./schemas";
import { z } from "zod";

export const opsKeys = {
  callbacks: (includeDone: boolean) => ["callbacks", includeDone] as const,
  demoRequests: (includeSent: boolean) => ["demo-requests", includeSent] as const,
  suppression: ["suppression"] as const,
};

export function useCallbacks(includeDone = false) {
  return useQuery({
    queryKey: opsKeys.callbacks(includeDone),
    queryFn: () =>
      apiRequest("/api/callbacks", z.array(callbackOutSchema), {
        searchParams: { include_done: includeDone },
      }),
  });
}

export function useUpdateCallback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: CallbackUpdateInput }) =>
      apiRequest(`/api/callbacks/${id}`, callbackOutSchema, { method: "PATCH", body: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["callbacks"] });
    },
  });
}

export function useDemoRequests(includeSent = false) {
  return useQuery({
    queryKey: opsKeys.demoRequests(includeSent),
    queryFn: () =>
      apiRequest("/api/demo-requests", z.array(demoRequestOutSchema), {
        searchParams: { include_sent: includeSent },
      }),
  });
}

export function useDemoWaLink(demoId: string) {
  return useMutation({
    mutationFn: () =>
      apiRequest(`/api/demo-requests/${demoId}/wa-link`, waLinkResponseSchema),
  });
}

export function useMarkDemoSent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (demoId: string) =>
      apiRequest(`/api/demo-requests/${demoId}/mark-sent`, okResponseSchema, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["demo-requests"] });
    },
  });
}

export function useSuppression() {
  return useQuery({
    queryKey: opsKeys.suppression,
    queryFn: () => apiRequest("/api/suppression", z.array(suppressionOutSchema)),
  });
}

export function useCreateSuppression() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SuppressionCreateInput) =>
      apiRequest("/api/suppression", suppressionOutSchema, { method: "POST", body: input }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: opsKeys.suppression });
    },
  });
}

export function useRemoveSuppression() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) =>
      apiRequest(`/api/suppression/${entryId}`, okResponseSchema, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: opsKeys.suppression });
    },
  });
}
