"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import {
  okResponseSchema,
  pageSchema,
  userOutSchema,
  type UserCreateInput,
  type UserUpdateInput,
} from "./schemas";

export const userKeys = {
  list: (page: number) => ["users", "list", page] as const,
};

export function useUsers(page = 1, pageSize = 50) {
  return useQuery({
    queryKey: userKeys.list(page),
    queryFn: () =>
      apiRequest("/api/users", pageSchema(userOutSchema), {
        searchParams: { page, page_size: pageSize },
      }),
    placeholderData: (prev) => prev,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: UserCreateInput) =>
      apiRequest("/api/users", userOutSchema, { method: "POST", body: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UserUpdateInput }) =>
      apiRequest(`/api/users/${id}`, userOutSchema, {
        method: "PATCH",
        body: { ...input, password: input.password || undefined },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useDeactivateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/users/${id}`, okResponseSchema, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}
