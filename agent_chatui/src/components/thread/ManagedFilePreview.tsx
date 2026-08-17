import { FileText, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ManagedFileReference } from "@/lib/managed-file-client";

interface ManagedFilePreviewProps {
  file: ManagedFileReference;
  removable?: boolean;
  onRemove?: () => void;
  className?: string;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

export function ManagedFilePreview({
  file,
  removable = false,
  onRemove,
  className,
}: ManagedFilePreviewProps) {
  return (
    <div
      className={cn(
        "flex max-w-72 min-w-0 items-center gap-2 rounded-md border bg-gray-50 px-3 py-2",
        className,
      )}
    >
      <FileText className="size-5 shrink-0 text-teal-700" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{file.originalName}</p>
        <p className="text-muted-foreground text-xs">
          {formatBytes(file.sizeBytes)}
        </p>
      </div>
      {removable && (
        <button
          type="button"
          className="shrink-0 rounded-full p-1 text-gray-500 hover:bg-gray-200 hover:text-gray-800"
          onClick={onRemove}
          aria-label={`移除 ${file.originalName}`}
        >
          <X className="size-4" />
        </button>
      )}
    </div>
  );
}
