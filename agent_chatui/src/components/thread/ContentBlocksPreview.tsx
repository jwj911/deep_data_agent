import React from "react";

import type { ManagedFileReference } from "@/lib/managed-file-client";
import { cn } from "@/lib/utils";

import { ManagedFilePreview } from "./ManagedFilePreview";

interface ContentBlocksPreviewProps {
  blocks: ManagedFileReference[];
  onRemove: (idx: number) => void;
  className?: string;
}

/**
 * Renders a preview of content blocks with optional remove functionality.
 * Uses cn utility for robust class merging.
 */
export const ContentBlocksPreview: React.FC<ContentBlocksPreviewProps> = ({
  blocks,
  onRemove,
  className,
}) => {
  if (!blocks.length) return null;
  return (
    <div className={cn("flex flex-wrap gap-2 p-3.5 pb-0", className)}>
      {blocks.map((file, idx) => (
        <ManagedFilePreview
          key={file.fileId}
          file={file}
          removable
          onRemove={() => onRemove(idx)}
        />
      ))}
    </div>
  );
};
