"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { usePreviewImport, useCommitImport } from "@/lib/api/imports";
import { ApiError } from "@/lib/api/client";
import type { ImportPreviewResponse } from "@/lib/api/schemas";

const TARGET_FIELDS = [
  "business_name",
  "sector",
  "city",
  "district",
  "address",
  "phone",
  "website",
  "rating",
  "review_count",
] as const;

export default function LeadImportPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const previewImport = usePreviewImport();
  const commitImport = useCommitImport();

  async function handleFileSelected(selected: File) {
    setError(null);
    setFile(selected);
    try {
      const result = await previewImport.mutateAsync({ file: selected });
      setPreview(result);
      setMapping(result.guessed_mapping);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Önizleme oluşturulamadı");
    }
  }

  return (
    <div>
      <PageHeader
        title="Lead İçe Aktar"
        description="CSV, JSON veya XLSX dosyasından toplu lead içe aktarın (30 MB sınır)"
      />
      <div className="space-y-6 p-4 sm:p-6">
        {error && <ErrorState title="İşlem başarısız" message={error} />}

        {!preview && (
          <div
            className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[var(--color-border-strong)] bg-[var(--color-bg-surface)] p-10 text-center"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const dropped = e.dataTransfer.files[0];
              if (dropped) handleFileSelected(dropped);
            }}
          >
            <Upload className="h-8 w-8 text-[var(--color-text-muted)]" />
            <p className="text-sm text-[var(--color-text-primary)]">
              Dosyayı buraya sürükleyin veya seçin
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.json,.xlsx"
              className="hidden"
              onChange={(e) => {
                const selected = e.target.files?.[0];
                if (selected) handleFileSelected(selected);
              }}
            />
            <Button
              variant="secondary"
              size="sm"
              loading={previewImport.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              Dosya Seç
            </Button>
          </div>
        )}

        {preview && file && (
          <div className="space-y-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-4">
              <h2 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">
                Sütun Eşleme ({preview.total_rows} satır bulundu)
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {preview.headers.map((header) => (
                  <div key={header}>
                    <label className="mb-1 block text-xs text-[var(--color-text-muted)]">
                      {header}
                    </label>
                    <Select
                      value={mapping[header] ?? ""}
                      onChange={(e) =>
                        setMapping((prev) => ({ ...prev, [header]: e.target.value }))
                      }
                    >
                      <option value="">— Eşleme yok —</option>
                      {TARGET_FIELDS.map((field) => (
                        <option key={field} value={field}>
                          {field}
                        </option>
                      ))}
                    </Select>
                  </div>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)]">
                    {preview.headers.map((h) => (
                      <th key={h} className="px-3 py-2 text-left text-xs text-[var(--color-text-muted)]">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.preview_rows.slice(0, 10).map((row, idx) => (
                    <tr key={idx} className="border-b border-[var(--color-border)] last:border-0">
                      {preview.headers.map((h) => (
                        <td key={h} className="px-3 py-2 text-[var(--color-text-secondary)]">
                          {String(row[h] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex gap-2">
              <Button
                variant="secondary"
                onClick={() => {
                  setPreview(null);
                  setFile(null);
                }}
              >
                Vazgeç
              </Button>
              <Button
                loading={commitImport.isPending}
                onClick={async () => {
                  if (!file) return;
                  setError(null);
                  try {
                    await commitImport.mutateAsync({ file, mapping });
                    router.push("/leads");
                  } catch (err) {
                    setError(err instanceof ApiError ? err.message : "İçe aktarma başarısız");
                  }
                }}
              >
                İçe Aktarmayı Tamamla
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
