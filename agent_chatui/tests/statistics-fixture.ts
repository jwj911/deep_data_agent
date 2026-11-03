import type { AIMessage, ToolMessage } from "@langchain/langgraph-sdk";
import type { StatisticsData } from "../src/lib/statistics-result";

// Public 34-byte CSV and test UUID from this iteration's canonical baseline.
export function statisticsFixture(): StatisticsData {
  return {
    analysis_version: "column-sum-v1",
    parser_version: "strict-table-v1",
    parameters: { metric: "sum", column: "amount" },
    row_count: 4,
    columns: [
      { name: "amount", types: ["number"], missing_count: 1 },
      { name: "label", types: ["string"], missing_count: 0 },
    ],
    duplicate_row_count: 1,
    result: {
      value: "0.4",
      unit: "unspecified",
      valid_count: 3,
      missing_count: 1,
      minimum: "0.1",
      maximum: "0.2",
    },
    warnings: [
      "unit_unspecified",
      "missing_values_excluded",
      "duplicate_rows_included",
    ],
    summary:
      "完整文件共 4 行；列「amount」的 3 个有效数值之和为 0.4，缺失 1 行；重复行 1 行，保留参与计算；单位未指定。",
    source: {
      file_id: "11111111-1111-4111-8111-111111111111",
      sha256:
        "b1f889c1cf3ea272f16f5d2e78b49e24514fcdeddfaf9d4e02354a47ba04e9fc",
      size_bytes: 34,
      semantics: "current_file_at_read",
    },
    result_sha256:
      "cc11dc9d7a0e12dacf9d415ab70df65cb6fd4e3526e7a19ab5f0bc69418a4c43",
  };
}

export function updateSummary(data: StatisticsData): void {
  data.summary = `完整文件共 ${data.row_count} 行；列「${data.parameters.column}」的 ${data.result.valid_count} 个有效数值之和为 ${data.result.value}，缺失 ${data.result.missing_count} 行；重复行 ${data.duplicate_row_count} 行，保留参与计算；单位未指定。`;
}

export function envelope(data: unknown = statisticsFixture()): string {
  return JSON.stringify({
    type: "managed_file_statistics",
    version: 1,
    status: "success",
    data,
  });
}

export function callMessage(ids = ["call-1"]): AIMessage {
  return {
    type: "ai",
    id: "ai-1",
    content: "",
    tool_calls: ids.map((id) => ({
      id,
      name: "analyze_file_statistics",
      args: { file_id: statisticsFixture().source.file_id, column: "amount" },
    })),
  };
}

export function toolMessage(id = "call-1", content = envelope()): ToolMessage {
  return {
    type: "tool",
    id: `tool-${id}`,
    tool_call_id: id,
    content,
    status: "success",
  };
}
