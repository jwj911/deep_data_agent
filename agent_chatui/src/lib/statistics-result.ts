import { z } from "zod";

export const STATISTICS_TOOL_NAME = "analyze_file_statistics";
export const STATISTICS_UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const hash = z.string().regex(/^[0-9a-f]{64}$/);
const count = z.number().int().min(0).max(50_000);
const columnName = z
  .string()
  .min(1)
  .refine((value) => Array.from(value).length <= 128);
// Validate the encoding without converting exact values to floating point.
const decimal = z
  .string()
  .regex(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$/)
  .refine((value) => value !== "-0");

const statisticsSchema = z
  .strictObject({
    analysis_version: z.literal("column-sum-v1"),
    parser_version: z.literal("strict-table-v1"),
    parameters: z.strictObject({
      metric: z.literal("sum"),
      column: columnName,
    }),
    row_count: count.min(1),
    columns: z
      .array(
        z.strictObject({
          name: columnName,
          types: z.array(z.enum(["boolean", "number", "string"])).max(3),
          missing_count: count,
        }),
      )
      .min(1)
      .max(64),
    duplicate_row_count: count,
    result: z.strictObject({
      value: decimal,
      unit: z.literal("unspecified"),
      valid_count: count.min(1),
      missing_count: count,
      minimum: decimal,
      maximum: decimal,
    }),
    warnings: z
      .array(
        z.enum([
          "unit_unspecified",
          "missing_values_excluded",
          "duplicate_rows_included",
        ]),
      )
      .min(1)
      .max(3),
    summary: z.string(),
    source: z.strictObject({
      file_id: z.string().regex(STATISTICS_UUID),
      sha256: hash,
      size_bytes: z
        .number()
        .int()
        .min(1)
        .max(5 * 1024 * 1024),
      semantics: z.literal("current_file_at_read"),
    }),
    result_sha256: hash,
  })
  .superRefine((data, context) => {
    const selected = data.columns.find(
      (column) => column.name === data.parameters.column,
    );
    const warnings = ["unit_unspecified"];
    if (data.result.missing_count) warnings.push("missing_values_excluded");
    if (data.duplicate_row_count) warnings.push("duplicate_rows_included");
    const summary = `完整文件共 ${data.row_count} 行；列「${data.parameters.column}」的 ${data.result.valid_count} 个有效数值之和为 ${data.result.value}，缺失 ${data.result.missing_count} 行；重复行 ${data.duplicate_row_count} 行，保留参与计算；单位未指定。`;
    if (
      data.row_count * data.columns.length > 250_000 ||
      data.result.valid_count + data.result.missing_count !== data.row_count ||
      data.duplicate_row_count >= data.row_count ||
      new Set(data.columns.map((column) => column.name)).size !==
        data.columns.length ||
      data.columns.some(
        (column) =>
          column.missing_count > data.row_count ||
          (column.types.length === 0) !==
            (column.missing_count === data.row_count) ||
          column.types.join(",") !==
            [...new Set(column.types)].sort().join(","),
      ) ||
      !selected ||
      selected.types.join(",") !== "number" ||
      selected.missing_count !== data.result.missing_count ||
      data.warnings.join(",") !== warnings.join(",") ||
      data.summary !== summary
    ) {
      context.addIssue({
        code: "custom",
        message: "Inconsistent statistics data",
      });
    }
  });

export type StatisticsData = z.infer<typeof statisticsSchema>;

export function parseStatisticsData(value: unknown): StatisticsData | null {
  const parsed = statisticsSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function sameStatisticsData(
  left: StatisticsData,
  right: StatisticsData,
): boolean {
  // Both objects have the complete, strict schema's key order. This compares
  // decoded data, not Python canonical hash bytes, and does not recalculate it.
  return JSON.stringify(left) === JSON.stringify(right);
}

export type StatisticsMessageResult =
  | { status: "success"; data: StatisticsData }
  | { status: "error" | "invalid"; message: string };

const invalidResult: StatisticsMessageResult = {
  status: "invalid",
  message: "统计结果尚未完成或无法校验，请重新分析。",
};

export function parseStatisticsContent(
  content: unknown,
  callArgs: unknown,
  toolStatus?: string,
): StatisticsMessageResult {
  if (toolStatus !== undefined && toolStatus !== "success") {
    return { status: "error", message: "没有取得成功的统计结果，请重试分析。" };
  }
  if (typeof content !== "string") return invalidResult;
  let envelope: unknown;
  try {
    envelope = JSON.parse(content);
  } catch {
    return invalidResult;
  }
  const error = z
    .strictObject({
      type: z.literal("managed_file_statistics"),
      version: z.literal(1),
      status: z.literal("error"),
      error: z.strictObject({
        code: z.string().min(1),
        message: z.string().min(1),
      }),
    })
    .safeParse(envelope);
  if (error.success) {
    return {
      status: "error",
      message: ["file_not_found", "managed_file_not_found"].includes(
        error.data.error.code,
      )
        ? "源文件已不可用，请重新上传后分析。"
        : "统计未完成，请检查源文件和列名后重试。",
    };
  }
  const success = z
    .strictObject({
      type: z.literal("managed_file_statistics"),
      version: z.literal(1),
      status: z.literal("success"),
      data: statisticsSchema,
    })
    .safeParse(envelope);
  const args = z
    .strictObject({
      file_id: z.string().regex(STATISTICS_UUID),
      column: columnName,
    })
    .safeParse(callArgs);
  if (
    !success.success ||
    !args.success ||
    args.data.file_id !== success.data.data.source.file_id ||
    args.data.column !== success.data.data.parameters.column
  )
    return invalidResult;
  return { status: "success", data: success.data.data };
}
