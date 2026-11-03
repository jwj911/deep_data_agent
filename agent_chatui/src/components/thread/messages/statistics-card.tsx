import { useId, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { AUTH_TOKEN_CHANGED_EVENT } from "@/lib/api-key";
import {
  StatisticsDownloadController,
  type StatisticsDownloadState,
} from "@/lib/statistics-download";
import type {
  StatisticsData,
  StatisticsMessageResult,
} from "@/lib/statistics-result";

const warningLabels = {
  unit_unspecified: "单位未指定",
  missing_values_excluded: "缺失值不参与计算",
  duplicate_rows_included: "重复行保留参与计算",
};

function StatisticsSnapshot({ data }: { data: StatisticsData }) {
  const sourceId = useId();
  const [sourceOpen, setSourceOpen] = useState(false);
  const [download, setDownload] = useState<StatisticsDownloadState>({
    status: "idle",
  });
  const controller = useRef<StatisticsDownloadController | null>(null);
  const snapshotIdentity = JSON.stringify(data);

  useLayoutEffect(() => {
    const current = new StatisticsDownloadController({ onState: setDownload });
    controller.current = current;
    setDownload({ status: "idle" });
    const cancel = () => current.cancel();
    window.addEventListener(AUTH_TOKEN_CHANGED_EVENT, cancel);
    return () => {
      window.removeEventListener(AUTH_TOKEN_CHANGED_EVENT, cancel);
      current.dispose();
      controller.current = null;
    };
  }, [snapshotIdentity]);

  return (
    <article
      data-testid="statistics-card"
      aria-label={`完整文件统计：${data.parameters.column}`}
      className="w-full min-w-0 rounded-lg border border-gray-200 bg-white text-gray-900"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 rounded-t-lg border-b border-gray-200 bg-gray-50 px-4 py-3">
        <h3 className="font-medium">完整文件统计 · 求和</h3>
        <span className="rounded border border-gray-300 px-2 py-0.5 text-xs">
          计算时快照
        </span>
      </header>
      <div className="flex min-w-0 flex-col gap-4 p-4">
        <p className="[overflow-wrap:anywhere] break-words">
          列：{data.parameters.column}
        </p>
        <div>
          <p className="text-sm text-gray-600">合计 · 单位未指定</p>
          <p
            data-testid="statistics-value"
            className="mt-1 font-mono text-xl leading-relaxed [overflow-wrap:anywhere]"
          >
            {data.result.value}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          {[
            ["总行数", data.row_count],
            ["有效数", data.result.valid_count],
            ["缺失数", data.result.missing_count],
            ["重复行数", data.duplicate_row_count],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-gray-600">{label}</dt>
              <dd className="mt-1 font-mono">{value}</dd>
            </div>
          ))}
        </dl>
        <ul
          aria-label="质量提示"
          className="list-inside list-disc text-sm text-gray-700"
        >
          {data.warnings.map((warning) => (
            <li key={warning}>{warningLabels[warning]}</li>
          ))}
        </ul>
        <p className="text-sm leading-relaxed [overflow-wrap:anywhere]">
          {data.summary}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            data-testid="statistics-source-toggle"
            aria-expanded={sourceOpen}
            aria-controls={sourceId}
            onClick={() => setSourceOpen((open) => !open)}
          >
            {sourceOpen ? "收起来源" : "查看来源"}
          </Button>
          <Button
            type="button"
            variant="outline"
            data-testid="statistics-download"
            className="h-auto min-h-9 max-w-full whitespace-normal"
            disabled={download.status === "loading"}
            onClick={() => void controller.current?.start(data)}
          >
            {download.status === "loading"
              ? "正在校验来源…"
              : "校验来源并下载 JSON"}
          </Button>
        </div>
        <div
          role="status"
          aria-live="polite"
          data-testid="statistics-download-status"
          className="text-sm [overflow-wrap:anywhere]"
        >
          {download.status === "loading" && "正在重新读取当前来源并校验结果。"}
          {download.status === "success" && "校验通过，已发起 JSON 下载。"}
          {download.status === "error" && download.message}
        </div>
        <div
          id={sourceId}
          hidden={!sourceOpen}
          data-testid="statistics-source"
        >
          <p className="mb-3 text-sm text-gray-600">
            来源为计算时读取的文件，不保证当前仍有效；下载时会重新校验。
          </p>
          <dl className="grid min-w-0 gap-3 text-sm">
            {[
              ["文件 UUID", data.source.file_id],
              ["文件 SHA-256", data.source.sha256],
              ["结果 SHA-256", data.result_sha256],
              ["文件字节数", data.source.size_bytes],
              ["来源语义", data.source.semantics],
              ["分析版本", data.analysis_version],
              ["解析版本", data.parser_version],
              ["最小值", data.result.minimum],
              ["最大值", data.result.maximum],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-gray-600">{label}</dt>
                <dd className="mt-1 font-mono [overflow-wrap:anywhere]">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </article>
  );
}

export function StatisticsCard({
  result,
}: {
  result: StatisticsMessageResult;
}) {
  if (result.status !== "success") {
    return (
      <p
        role="status"
        data-testid="statistics-result-error"
        className="rounded-lg border border-gray-200 p-4 text-sm"
      >
        {result.message}
      </p>
    );
  }
  return <StatisticsSnapshot data={result.data} />;
}
