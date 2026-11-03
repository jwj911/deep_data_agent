import { getAuthToken } from "./api-key";
import {
  fetchFileStatistics,
  ManagedFileApiError,
} from "./managed-file-client";
import { parseStatisticsData, type StatisticsData } from "./statistics-result";

export type StatisticsDownloadState =
  | { status: "idle" | "loading" | "success" }
  | { status: "error"; message: string };

export function statisticsDownloadError(error: unknown): string {
  if (error instanceof ManagedFileApiError) {
    if (error.status === 401) return "登录已过期，请重新登录。";
    if (error.status === 404) return "源文件已不可用。";
    if (error.code === "statistics_changed") return "结果已变化，请重新分析。";
    if (error.code === "network_error") return "网络连接失败，请重试。";
    if (error.status === 413) return "文件超过统计限制，无法下载。";
    if (error.status === 422 || error.status === 400)
      return "统计未完成，请检查源文件和列名后重新分析。";
    if (error.code === "analysis_timeout") return "统计校验超时，请重试。";
  }
  return "无法校验来源或统计结果，请重试。";
}

export function saveStatisticsJson(data: StatisticsData): void {
  if (!parseStatisticsData(data))
    throw new Error("Invalid statistics download");
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  try {
    link.href = url;
    link.download = `analysis-${data.source.file_id}.json`;
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(url);
  }
}

interface DownloadOptions {
  onState: (state: StatisticsDownloadState) => void;
  load?: typeof fetchFileStatistics;
  deliver?: typeof saveStatisticsJson;
  identity?: typeof getAuthToken;
}

export class StatisticsDownloadController {
  private active?: { controller: AbortController; identity: string | null };
  private disposed = false;
  private readonly load: typeof fetchFileStatistics;
  private readonly deliver: typeof saveStatisticsJson;
  private readonly identity: typeof getAuthToken;

  constructor(private readonly options: DownloadOptions) {
    this.load = options.load ?? fetchFileStatistics;
    this.deliver = options.deliver ?? saveStatisticsJson;
    this.identity = options.identity ?? getAuthToken;
  }

  async start(data: StatisticsData): Promise<void> {
    if (this.disposed || this.active) return;
    const request = {
      controller: new AbortController(),
      identity: this.identity(),
    };
    this.active = request;
    const current = () =>
      !this.disposed &&
      this.active === request &&
      !request.controller.signal.aborted &&
      request.identity === this.identity();
    this.options.onState({ status: "loading" });
    try {
      const verified = await this.load(data, request.controller.signal);
      if (!current()) return;
      this.deliver(verified);
      this.options.onState({ status: "success" });
    } catch (error) {
      if (!current()) return;
      this.options.onState(
        error instanceof Error && error.name === "AbortError"
          ? { status: "idle" }
          : { status: "error", message: statisticsDownloadError(error) },
      );
    } finally {
      if (this.active === request) {
        this.active = undefined;
        request.controller.abort();
      }
    }
  }

  cancel(): void {
    this.active?.controller.abort();
    this.active = undefined;
    if (!this.disposed) this.options.onState({ status: "idle" });
  }

  dispose(): void {
    this.disposed = true;
    this.cancel();
  }
}
