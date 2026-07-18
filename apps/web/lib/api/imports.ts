"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { importJobOutSchema, importPreviewResponseSchema, importResultOutSchema } from "./schemas";
import { z } from "zod";

export const importKeys = {
  jobs: ["imports", "jobs"] as const,
};

export function useImportJobs() {
  return useQuery({
    queryKey: importKeys.jobs,
    queryFn: () => apiRequest("/api/imports", z.array(importJobOutSchema)),
  });
}

export function usePreviewImport() {
  return useMutation({
    mutationFn: ({ file, sheetName }: { file: File; sheetName?: string }) => {
      const formData = new FormData();
      formData.append("file", file);
      if (sheetName) formData.append("sheet_name", sheetName);
      return apiRequest("/api/imports/preview", importPreviewResponseSchema, {
        method: "POST",
        formData,
      });
    },
  });
}

export function useCommitImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      mapping,
      sheetName,
    }: {
      file: File;
      mapping: Record<string, string>;
      sheetName?: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("mapping_json", JSON.stringify(mapping));
      if (sheetName) formData.append("sheet_name", sheetName);
      return apiRequest("/api/imports/commit", importResultOutSchema, {
        method: "POST",
        formData,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importKeys.jobs });
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
