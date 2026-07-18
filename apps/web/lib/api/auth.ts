"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { meResponseSchema, okResponseSchema, type LoginRequestInput } from "./schemas";

export const authKeys = {
  me: ["auth", "me"] as const,
};

export function fetchMe() {
  return apiRequest("/api/auth/me", meResponseSchema);
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: fetchMe,
    enabled,
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: LoginRequestInput) =>
      apiRequest("/api/auth/login", meResponseSchema, { method: "POST", body: input }),
    onSuccess: (data) => {
      queryClient.setQueryData(authKeys.me, data);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiRequest("/api/auth/logout", okResponseSchema, { method: "POST" }),
    onSettled: () => {
      queryClient.clear();
    },
  });
}
