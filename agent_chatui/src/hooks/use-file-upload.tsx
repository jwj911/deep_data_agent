import {
  type ChangeEvent,
  type ClipboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import {
  deleteManagedFile,
  ManagedFileApiError,
  type ManagedFileReference,
  uploadManagedFiles,
  validateManagedFileSelection,
} from "@/lib/managed-file-client";

interface UseFileUploadOptions {
  initialBlocks?: ManagedFileReference[];
}

function uploadErrorMessage(error: unknown): string {
  if (!(error instanceof ManagedFileApiError)) {
    return "文件上传失败，请稍后重试。";
  }
  const messages: Record<string, string> = {
    duplicate_file: "相同内容的文件已经存在。",
    file_count_exceeded: "上传文件数量超过限制。",
    file_too_large: "单个文件超过 5 MiB。",
    file_batch_too_large: "本批文件总量超过 10 MiB。",
    upload_request_too_large: "上传请求超过限制。",
    file_quota_exceeded: "文件存储配额已用完。",
    unsafe_csv_formula: "CSV 包含不允许的公式单元格。",
    unsupported_file_type: "仅支持 TXT、Markdown、CSV 和 JSON 文件。",
    invalid_file_content: "文件内容或编码无效。",
    invalid_filename: "文件名无效。",
    network_error: "无法连接文件服务。",
  };
  return messages[error.code] ?? "文件上传失败，请检查文件后重试。";
}

export function useFileUpload({
  initialBlocks = [],
}: UseFileUploadOptions = {}) {
  const [contentBlocks, setContentBlocks] =
    useState<ManagedFileReference[]>(initialBlocks);
  const [uploading, setUploading] = useState(false);
  const contentBlocksRef = useRef(contentBlocks);
  const uploadingRef = useRef(false);
  const dropRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const dragCounter = useRef(0);

  useEffect(() => {
    contentBlocksRef.current = contentBlocks;
  }, [contentBlocks]);

  const processFiles = useCallback(async (files: File[]) => {
    if (uploadingRef.current || files.length === 0) return;
    const validation = validateManagedFileSelection(
      files,
      contentBlocksRef.current,
    );
    if (validation) {
      toast.error(validation);
      return;
    }

    uploadingRef.current = true;
    setUploading(true);
    try {
      const uploaded = await uploadManagedFiles(files);
      setContentBlocks((previous) => [...previous, ...uploaded]);
    } catch (error) {
      toast.error(uploadErrorMessage(error));
    } finally {
      uploadingRef.current = false;
      setUploading(false);
    }
  }, []);

  const handleFileUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    await processFiles(files);
  };

  useEffect(() => {
    const handleWindowDragEnter = (event: DragEvent) => {
      if (!event.dataTransfer?.types.includes("Files")) return;
      dragCounter.current += 1;
      setDragOver(true);
    };
    const handleWindowDragLeave = (event: DragEvent) => {
      if (!event.dataTransfer?.types.includes("Files")) return;
      dragCounter.current -= 1;
      if (dragCounter.current <= 0) {
        dragCounter.current = 0;
        setDragOver(false);
      }
    };
    const handleWindowDragOver = (event: DragEvent) => {
      if (!event.dataTransfer?.types.includes("Files")) return;
      event.preventDefault();
      event.stopPropagation();
    };
    const handleWindowDrop = (event: DragEvent) => {
      if (!event.dataTransfer?.types.includes("Files")) return;
      event.preventDefault();
      event.stopPropagation();
      dragCounter.current = 0;
      setDragOver(false);
      void processFiles(Array.from(event.dataTransfer.files));
    };
    const handleWindowDragEnd = () => {
      dragCounter.current = 0;
      setDragOver(false);
    };

    window.addEventListener("dragenter", handleWindowDragEnter);
    window.addEventListener("dragleave", handleWindowDragLeave);
    window.addEventListener("dragover", handleWindowDragOver);
    window.addEventListener("drop", handleWindowDrop);
    window.addEventListener("dragend", handleWindowDragEnd);
    return () => {
      window.removeEventListener("dragenter", handleWindowDragEnter);
      window.removeEventListener("dragleave", handleWindowDragLeave);
      window.removeEventListener("dragover", handleWindowDragOver);
      window.removeEventListener("drop", handleWindowDrop);
      window.removeEventListener("dragend", handleWindowDragEnd);
    };
  }, [processFiles]);

  const handlePaste = async (
    event: ClipboardEvent<HTMLTextAreaElement | HTMLInputElement>,
  ) => {
    const files = Array.from(event.clipboardData.items).flatMap((item) => {
      if (item.kind !== "file") return [];
      const file = item.getAsFile();
      return file ? [file] : [];
    });
    if (files.length === 0) return;
    event.preventDefault();
    await processFiles(files);
  };

  const removeBlock = async (index: number) => {
    if (uploadingRef.current) return;
    const file = contentBlocksRef.current[index];
    if (!file) return;
    uploadingRef.current = true;
    setUploading(true);
    try {
      await deleteManagedFile(file.fileId);
      setContentBlocks((previous) =>
        previous.filter((item) => item.fileId !== file.fileId),
      );
    } catch (error) {
      if (error instanceof ManagedFileApiError && error.status === 404) {
        setContentBlocks((previous) =>
          previous.filter((item) => item.fileId !== file.fileId),
        );
        return;
      }
      toast.error("无法删除附件，请稍后重试。");
    } finally {
      uploadingRef.current = false;
      setUploading(false);
    }
  };

  const clearSubmittedFiles = () => setContentBlocks([]);

  return {
    contentBlocks,
    handleFileUpload,
    processFiles,
    dropRef,
    fileInputRef,
    removeBlock,
    clearSubmittedFiles,
    dragOver,
    handlePaste,
    uploading,
  };
}
