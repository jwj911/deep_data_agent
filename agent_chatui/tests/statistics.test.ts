import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { afterEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Message } from "@langchain/langgraph-sdk";
import {
  DO_NOT_RENDER_ID_PREFIX,
  ensureToolCallsHaveResponses,
  MissingToolCallIdError,
} from "../src/lib/ensure-tool-responses";
import { buildMessageViews } from "../src/lib/statistics-messages";
import {
  parseStatisticsContent,
  parseStatisticsData,
  sameStatisticsData,
} from "../src/lib/statistics-result";
import {
  fetchFileStatistics,
  ManagedFileApiError,
} from "../src/lib/managed-file-client";
import {
  AUTH_TOKEN_CHANGED_EVENT,
  clearAuthToken,
  setAuthToken,
} from "../src/lib/api-key";
import { AUTH_UNAUTHORIZED_EVENT } from "../src/lib/auth-client";
import {
  saveStatisticsJson,
  StatisticsDownloadController,
  type StatisticsDownloadState,
} from "../src/lib/statistics-download";
import { StatisticsCard } from "../src/components/thread/messages/statistics-card";
import {
  callMessage,
  envelope,
  statisticsFixture,
  toolMessage,
  updateSummary,
} from "./statistics-fixture";

const originals = {
  fetch: globalThis.fetch,
  window: Object.getOwnPropertyDescriptor(globalThis, "window"),
  document: Object.getOwnPropertyDescriptor(globalThis, "document"),
  createObjectURL: URL.createObjectURL,
  revokeObjectURL: URL.revokeObjectURL,
};

afterEach(() => {
  globalThis.fetch = originals.fetch;
  URL.createObjectURL = originals.createObjectURL;
  URL.revokeObjectURL = originals.revokeObjectURL;
  for (const name of ["window", "document"] as const) {
    const descriptor = originals[name];
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else Reflect.deleteProperty(globalThis, name);
  }
});

function browserIdentity() {
  const storage = new Map<string, string>([
    ["auth_token", "public-test-session"],
  ]);
  const target = new EventTarget();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: Object.assign(target, {
      sessionStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
        removeItem: (key: string) => storage.delete(key),
      },
    }),
  });
  return { target, storage };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function successes(messages: Message[]) {
  return buildMessageViews(messages).filter(
    (view) => view.statistics?.status === "success",
  );
}

test("baseline includes the complete canonical payload and exact Python ASCII hash", () => {
  const data = statisticsFixture();
  const { result_sha256: hash, ...unhashed } = data;
  function canonical(value: unknown): string {
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
    if (value !== null && typeof value === "object") {
      return `{${Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b, "en"))
        .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
        .join(",")}}`;
    }
    return JSON.stringify(value).replace(
      /[\u007f-\uffff]/g,
      (character) =>
        `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`,
    );
  }
  assert.equal(
    createHash("sha256").update(canonical(unhashed), "ascii").digest("hex"),
    hash,
  );
  assert.deepEqual(parseStatisticsData(data), data);
  assert.equal(successes([callMessage(), toolMessage()]).length, 1);
});

for (const field of Object.keys(statisticsFixture())) {
  test(`reject missing canonical field: ${field}`, () => {
    const value: Record<string, unknown> = statisticsFixture();
    delete value[field];
    assert.equal(parseStatisticsData(value), null);
  });
}

for (const parent of ["result", "source", "parameters"] as const) {
  for (const field of Object.keys(statisticsFixture()[parent])) {
    test(`reject missing nested field: ${parent}.${field}`, () => {
      const data = statisticsFixture();
      Reflect.deleteProperty(data[parent], field);
      assert.equal(parseStatisticsData(data), null);
    });
  }
}

for (const [label, mutate] of Object.entries({
  "number instead of decimal": (d: any) => {
    d.result.value = 0.4;
  },
  "boolean count": (d: any) => {
    d.result.valid_count = true;
  },
  "string count": (d: any) => {
    d.row_count = "4";
  },
  "unsafe count": (d: any) => {
    d.row_count = Number.MAX_SAFE_INTEGER + 1;
  },
  "negative count": (d: any) => {
    d.duplicate_row_count = -1;
  },
  "fractional count": (d: any) => {
    d.result.missing_count = 0.5;
  },
  "inconsistent counts": (d: any) => {
    d.result.valid_count = 4;
  },
  "inconsistent summary": (d: any) => {
    d.summary = "模型解释";
  },
  "inconsistent warnings": (d: any) => {
    d.warnings = ["unit_unspecified"];
  },
  "missing warning": (d: any) => {
    d.warnings = [];
  },
  "unknown warning": (d: any) => {
    d.warnings.push("unknown");
  },
  "unknown analysis version": (d: any) => {
    d.analysis_version = "v2";
  },
  "unknown parser version": (d: any) => {
    d.parser_version = "v2";
  },
  "URL in source": (d: any) => {
    d.source.url = "https://untrusted.invalid/";
  },
  "extra top level": (d: any) => {
    d.url = "https://untrusted.invalid/";
  },
  "noncanonical UUID": (d: any) => {
    d.source.file_id = "../outside";
  },
  "bad hash": (d: any) => {
    d.result_sha256 = "abc";
  },
  "unsupported unit": (d: any) => {
    d.result.unit = "USD";
  },
  "missing columns": (d: any) => {
    d.columns = [];
  },
  "unknown type": (d: any) => {
    d.columns[1].types = ["object"];
  },
  "duplicate columns": (d: any) => {
    d.columns[1].name = "amount";
  },
  "selected nonnumeric": (d: any) => {
    d.columns[0].types = ["string"];
  },
  "column count mismatch": (d: any) => {
    d.columns[0].missing_count = 0;
  },
  "source semantics changed": (d: any) => {
    d.source.semantics = "cached";
  },
  "empty source": (d: any) => {
    d.source.size_bytes = 0;
  },
})) {
  test(`strict validation: ${label}`, () => {
    const data = statisticsFixture();
    mutate(data);
    assert.equal(parseStatisticsData(data), null);
  });
}

for (const value of [
  "0",
  "-0.2",
  "2799.123456789012345678",
  "199999999999999999999999999999999999998.000000000000000001",
]) {
  test(`preserve exact decimal string: ${value}`, () => {
    const data = statisticsFixture();
    data.result.value = value;
    updateSummary(data);
    assert.equal(parseStatisticsData(data)?.result.value, value);
    const html = renderToStaticMarkup(
      createElement(StatisticsCard, { result: { status: "success", data } }),
    );
    assert.ok(html.includes(value));
    for (const text of [
      "计算时快照",
      "单位未指定",
      "缺失值不参与计算",
      "重复行保留参与计算",
      data.source.file_id,
      data.source.sha256,
      data.result_sha256,
      data.analysis_version,
      data.parser_version,
    ]) {
      assert.ok(html.includes(text), text);
    }
    assert.ok(html.includes('data-testid="statistics-download"'));
    assert.ok(html.includes('aria-expanded="false"'));
  });
}

for (const value of [
  "NaN",
  "Infinity",
  "1e6",
  "+1",
  "01",
  "-0",
  "0.40",
  "",
  " 1",
]) {
  test(`reject noncanonical decimal: ${value}`, () => {
    const data = statisticsFixture();
    data.result.value = value;
    updateSummary(data);
    assert.equal(parseStatisticsData(data), null);
  });
}

test("dynamic columns render as text, never HTML", () => {
  const data = statisticsFixture();
  data.parameters.column = "<img src=x onerror=alert(1)>";
  data.columns[0].name = data.parameters.column;
  updateSummary(data);
  assert.ok(parseStatisticsData(data));
  const html = renderToStaticMarkup(
    createElement(StatisticsCard, { result: { status: "success", data } }),
  );
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img"));
});

for (const patch of [
  { type: "other" },
  { version: 2 },
  { version: "1" },
  { status: "pending" },
  { status: "error" },
  { data: {} },
]) {
  test(`reject malformed envelope: ${JSON.stringify(patch)}`, () => {
    const content = JSON.stringify({ ...JSON.parse(envelope()), ...patch });
    assert.equal(
      successes([callMessage(), toolMessage("call-1", content)]).length,
      0,
    );
  });
}

test("ordinary text, synthetic, unrelated and error messages never become successful cards", () => {
  for (const messages of [
    [{ type: "ai", id: "text", content: envelope() }],
    [callMessage(), { ...toolMessage(), id: `${DO_NOT_RENDER_ID_PREFIX}test` }],
    [callMessage(), { ...toolMessage(), status: "error" }],
    [callMessage(), toolMessage("unrelated")],
    [toolMessage(), callMessage()],
    [callMessage(), { ...toolMessage(), id: undefined }],
    [callMessage(), toolMessage("call-1", '{"type":')],
    [callMessage(), toolMessage("call-1", "")],
    [
      callMessage(),
      { ...toolMessage(), content: [{ type: "text", text: envelope() }] },
    ],
  ] satisfies Message[][]) {
    assert.equal(successes(messages).length, 0);
  }
  const other = callMessage();
  other.tool_calls![0].name = "analyze_document";
  assert.equal(successes([other, toolMessage()]).length, 0);
  const wrongArgs = callMessage();
  wrongArgs.tool_calls![0].args.column = "label";
  assert.equal(successes([wrongArgs, toolMessage()]).length, 0);
});

test("safe tool error is visible with no success data, error HTML stays nonexecuting", () => {
  const result = parseStatisticsContent(
    JSON.stringify({
      type: "managed_file_statistics",
      version: 1,
      status: "error",
      error: { code: "file_not_found", message: "<script>secret</script>" },
    }),
    {},
  );
  assert.equal(result.status, "error");
  const html = renderToStaticMarkup(createElement(StatisticsCard, { result }));
  assert.ok(html.includes("源文件已不可用"));
  assert.ok(!html.includes("secret"));
  assert.ok(!html.includes('data-testid="statistics-card"'));
});

test("message and call identity deduplicate replays, latest update wins at stable position", () => {
  const first = toolMessage("c1");
  const second = toolMessage("c2");
  const messages = [
    callMessage(["c1", "c2"]),
    second,
    first,
    second,
    { ...first, id: "replayed-c1" },
  ];
  const views = successes(messages);
  assert.equal(views.length, 2);
  assert.deepEqual(
    views.map((view) => view.message.id),
    ["tool-c2", "replayed-c1"],
  );
  assert.deepEqual(buildMessageViews(messages), buildMessageViews(messages));
  const changed = [
    ...messages,
    { ...first, id: "replayed-c1", status: "error" as const },
  ];
  assert.equal(successes(changed).length, 1);
  assert.equal(successes([]).length, 0);
  assert.equal(successes([callMessage(), toolMessage()]).length, 1);
});

test("partial, unrelated and out-of-order real responses are preserved; only missing IDs are filled", () => {
  const real3 = toolMessage("c3");
  const real1 = {
    ...toolMessage("c1"),
    status: "error" as const,
    content: "actual failure",
  };
  const messages = [
    callMessage(["c1", "c2", "c3"]),
    real3,
    toolMessage("unrelated"),
    real1,
  ];
  const before = structuredClone(messages);
  const added = ensureToolCallsHaveResponses(messages);
  assert.equal(added.length, 1);
  assert.deepEqual(messages, before);
  assert.strictEqual(messages[1], real3);
  assert.strictEqual(messages[3], real1);
  assert.equal(added[0].type, "tool");
  if (added[0].type !== "tool") assert.fail("expected ToolMessage");
  assert.equal(added[0].tool_call_id, "c2");
  assert.equal(added[0].status, "error");
  assert.equal(added[0].content, "没有取得工具结果");
  assert.ok(added[0].id?.startsWith(DO_NOT_RENDER_ID_PREFIX));
  assert.deepEqual(ensureToolCallsHaveResponses([...messages, ...added]), []);
  assert.equal(successes([...messages, ...added]).length, 1);
});

test("ambiguous reused call IDs cannot associate a successful card with either call", () => {
  const reused = { ...callMessage(), id: "second-ai" };
  assert.equal(
    successes([
      callMessage(),
      toolMessage(),
      reused,
      { ...toolMessage(), id: "second-tool" },
    ]).length,
    0,
  );
  assert.equal(
    successes([callMessage(), callMessage(), toolMessage()]).length,
    1,
  );
});

test("different columns on the same file are separate calls, never merged by file ID", () => {
  const secondData = statisticsFixture();
  secondData.parameters.column = "second_amount";
  secondData.columns[0].name = secondData.parameters.column;
  updateSummary(secondData);
  const calls = callMessage(["c1", "c2"]);
  calls.tool_calls![1].args.column = secondData.parameters.column;
  const cards = successes([
    calls,
    toolMessage("c1"),
    toolMessage("c2", envelope(secondData)),
  ]);
  assert.equal(cards.length, 2);
  assert.notEqual(cards[0].key, cards[1].key);
});

test("a preceding or arbitrary following tool result does not complete a call group", () => {
  const added = ensureToolCallsHaveResponses([
    toolMessage("c1"),
    callMessage(["c1", "c2"]),
    toolMessage("other"),
  ]);
  assert.equal(added.length, 2);
  assert.deepEqual(
    ensureToolCallsHaveResponses([callMessage(), toolMessage()]),
    [],
  );
});

for (const id of [undefined, "", "  "]) {
  test(`missing call ID blocks continuation without modifying the input messages: ${String(id)}`, () => {
    const message = callMessage();
    message.tool_calls![0].id = id;
    const before = structuredClone(message);
    assert.throws(
      () => ensureToolCallsHaveResponses([message]),
      MissingToolCallIdError,
    );
    assert.deepEqual(message, before);
  });
}

test("fixed REST target, POST, JWT, request ID, no redirect, column only; return complete data", async () => {
  browserIdentity();
  const requests: RequestInit[] = [];
  globalThis.fetch = async (input, init) => {
    assert.equal(
      String(input),
      "https://statistics.example.test/rest/api/files/11111111-1111-4111-8111-111111111111/statistics?download=true",
    );
    assert.equal(init?.method, "POST");
    assert.equal(init?.redirect, "error");
    assert.equal(init?.cache, "no-store");
    assert.equal(init?.body, '{"column":"amount"}');
    const headers = new Headers(init?.headers);
    assert.equal(headers.get("Authorization"), "Bearer public-test-session");
    assert.equal(headers.get("Content-Type"), "application/json");
    assert.match(headers.get("X-Request-ID") ?? "", /^[a-f0-9]{32}$/);
    requests.push(init!);
    return Response.json(statisticsFixture(), {
      headers: {
        "Content-Disposition": 'attachment; filename="../../untrusted.json"',
      },
    });
  };
  for (let i = 0; i < 2; i++) {
    const result = await fetchFileStatistics(
      statisticsFixture(),
      new AbortController().signal,
    );
    assert.deepEqual(result, statisticsFixture());
    assert.ok(sameStatisticsData(result, statisticsFixture()));
  }
  assert.notEqual(
    new Headers(requests[0].headers).get("X-Request-ID"),
    new Headers(requests[1].headers).get("X-Request-ID"),
  );
});

test("invalid snapshot, injected URL and pre-aborted request never reach fetch", async () => {
  browserIdentity();
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return Response.json(statisticsFixture());
  };
  const invalid = statisticsFixture();
  invalid.source.file_id = "../outside?target=https://untrusted.invalid";
  await assert.rejects(
    fetchFileStatistics(invalid, new AbortController().signal),
  );
  const injected = {
    ...statisticsFixture(),
    url: "https://untrusted.invalid/download",
  };
  await assert.rejects(
    fetchFileStatistics(injected, new AbortController().signal),
  );
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    fetchFileStatistics(statisticsFixture(), controller.signal),
    { name: "AbortError" },
  );
  assert.equal(calls, 0);
});

for (const mutate of [
  (d: any) => {
    delete d.source;
  },
  (d: any) => {
    d.result.value = 0.4;
  },
  (d: any) => {
    d.row_count = true;
  },
  (d: any) => {
    d.parameters.metric = "average";
  },
  (d: any) => {
    d.source.semantics = "cached";
  },
]) {
  test(`200 with invalid canonical data cannot create a Blob or deliver a download: ${mutate.toString()}`, async () => {
    browserIdentity();
    const data = statisticsFixture();
    mutate(data);
    globalThis.fetch = async () => Response.json(data);
    let deliveries = 0;
    const states: StatisticsDownloadState[] = [];
    const controller = new StatisticsDownloadController({
      onState: (state) => states.push(state),
      deliver: () => {
        deliveries++;
      },
    });
    await controller.start(statisticsFixture());
    assert.equal(deliveries, 0);
    assert.equal(states.at(-1)?.status, "error");
    controller.dispose();
  });
}

for (const [label, mutate] of Object.entries({
  UUID: (d: any) => {
    d.source.file_id = "22222222-2222-4222-8222-222222222222";
  },
  fileHash: (d: any) => {
    d.source.sha256 = "b".repeat(64);
  },
  size: (d: any) => {
    d.source.size_bytes++;
  },
  resultHash: (d: any) => {
    d.result_sha256 = "a".repeat(64);
  },
  analysisVersion: (d: any) => {
    d.analysis_version = "column-sum-v2";
  },
  parserVersion: (d: any) => {
    d.parser_version = "strict-table-v2";
  },
  column: (d: any) => {
    d.parameters.column = "other";
    d.columns[0].name = "other";
    updateSummary(d);
  },
  exactValue: (d: any) => {
    d.result.value = "0.5";
    updateSummary(d);
  },
  minimum: (d: any) => {
    d.result.minimum = "0.01";
  },
})) {
  test(`download refuses changed ${label} and never delivers cached snapshot`, async () => {
    browserIdentity();
    const changed = statisticsFixture();
    mutate(changed);
    globalThis.fetch = async () => Response.json(changed);
    await assert.rejects(
      fetchFileStatistics(statisticsFixture(), new AbortController().signal),
      (error: unknown) =>
        error instanceof ManagedFileApiError &&
        error.code === "statistics_changed",
    );
  });
}

for (const body of ["{", "null", "[]", "{}", '{"result": {"value": 0.4}}']) {
  test(`malformed download response is refused: ${body}`, async () => {
    browserIdentity();
    globalThis.fetch = async () => new Response(body);
    await assert.rejects(
      fetchFileStatistics(statisticsFixture(), new AbortController().signal),
      (error: unknown) =>
        error instanceof ManagedFileApiError &&
        error.code === "invalid_response",
    );
  });
}

for (const [status, code, expected] of [
  [404, "file_not_found", "源文件已不可用"],
  [503, "file_storage_invalid", "无法校验"],
  [503, "file_storage_unavailable", "无法校验"],
  [503, "analysis_timeout", "超时"],
  [422, "analysis_non_numeric", "检查源文件和列名"],
  [413, "analysis_table_limit", "超过统计限制"],
  [400, "unsafe_csv_formula", "检查源文件和列名"],
] as const) {
  test(`HTTP ${status}/${code} safely fails, allows manual retry, no old download`, async () => {
    browserIdentity();
    let fail = true;
    let deliveries = 0;
    const states: StatisticsDownloadState[] = [];
    globalThis.fetch = async () =>
      fail
        ? Response.json(
            { detail: { code, message: "private path must not be shown" } },
            { status },
          )
        : Response.json(statisticsFixture());
    const controller = new StatisticsDownloadController({
      onState: (state) => states.push(state),
      deliver: () => {
        deliveries++;
      },
    });
    await controller.start(statisticsFixture());
    const error = states.at(-1);
    assert.equal(error?.status, "error");
    if (error?.status !== "error") assert.fail("expected safe error");
    assert.ok(error.message.includes(expected));
    assert.ok(!error.message.includes("private"));
    assert.equal(deliveries, 0);
    fail = false;
    await controller.start(statisticsFixture());
    assert.equal(deliveries, 1);
    assert.deepEqual(
      states.map((state) => state.status),
      ["loading", "error", "loading", "success"],
    );
    controller.dispose();
  });
}

test("401 clears the current session and invokes existing unauthorized authentication flow", async () => {
  const { target, storage } = browserIdentity();
  let unauthorized = 0;
  target.addEventListener(AUTH_UNAUTHORIZED_EVENT, () => {
    unauthorized++;
  });
  globalThis.fetch = async () =>
    Response.json({ detail: "unauthorized" }, { status: 401 });
  await assert.rejects(
    fetchFileStatistics(statisticsFixture(), new AbortController().signal),
    (error: unknown) =>
      error instanceof ManagedFileApiError && error.status === 401,
  );
  assert.equal(unauthorized, 1);
  assert.equal(storage.has("auth_token"), false);
});

test("late 401 from a prior identity cannot clear a new session", async () => {
  const { target, storage } = browserIdentity();
  let unauthorized = 0;
  target.addEventListener(AUTH_UNAUTHORIZED_EVENT, () => {
    unauthorized++;
  });
  const response = deferred<Response>();
  globalThis.fetch = () => response.promise;
  const request = fetchFileStatistics(
    statisticsFixture(),
    new AbortController().signal,
  );
  setAuthToken("new-public-test-session");
  response.resolve(new Response("", { status: 401 }));
  await assert.rejects(request, { name: "AbortError" });
  assert.equal(unauthorized, 0);
  assert.equal(storage.get("auth_token"), "new-public-test-session");
});

test("download deduplicates rapid clicks and releases the request after delivery", async () => {
  browserIdentity();
  const response = deferred<Response>();
  let calls = 0;
  let signal: AbortSignal | null | undefined;
  let deliveries = 0;
  globalThis.fetch = (_url, init) => {
    calls++;
    signal = init?.signal;
    return response.promise;
  };
  const controller = new StatisticsDownloadController({
    onState: () => {},
    deliver: () => {
      deliveries++;
    },
  });
  const first = controller.start(statisticsFixture());
  await controller.start(statisticsFixture());
  assert.equal(calls, 1);
  response.resolve(Response.json(statisticsFixture()));
  await first;
  assert.equal(deliveries, 1);
  assert.equal(signal?.aborted, true);
  controller.dispose();
});

for (const action of [
  "cancel",
  "thread-change",
  "unmount",
  "logout",
  "identity-change",
] as const) {
  test(`${action} aborts/discards late success, without new download or stale status`, async () => {
    const { target } = browserIdentity();
    const response = deferred<Response>();
    let signal: AbortSignal | null | undefined;
    let deliveries = 0;
    const states: StatisticsDownloadState[] = [];
    globalThis.fetch = (_url, init) => {
      signal = init?.signal;
      return response.promise;
    };
    const controller = new StatisticsDownloadController({
      onState: (state) => states.push(state),
      deliver: () => {
        deliveries++;
      },
    });
    target.addEventListener(AUTH_TOKEN_CHANGED_EVENT, () =>
      controller.cancel(),
    );
    const request = controller.start(statisticsFixture());
    if (action === "cancel") controller.cancel();
    if (action === "thread-change" || action === "unmount")
      controller.dispose();
    if (action === "logout") clearAuthToken();
    if (action === "identity-change") setAuthToken("different-public-session");
    const before = [...states];
    assert.equal(signal?.aborted, true);
    response.resolve(Response.json(statisticsFixture()));
    await request;
    assert.equal(deliveries, 0);
    assert.deepEqual(states, before);
    controller.dispose();
  });
}

test("a late old failure cannot overwrite a retry's success", async () => {
  browserIdentity();
  const old = deferred<Response>();
  let calls = 0;
  const states: StatisticsDownloadState[] = [];
  globalThis.fetch = () =>
    ++calls === 1
      ? old.promise
      : Promise.resolve(Response.json(statisticsFixture()));
  const controller = new StatisticsDownloadController({
    onState: (state) => states.push(state),
    deliver: () => {},
  });
  const pending = controller.start(statisticsFixture());
  controller.cancel();
  await controller.start(statisticsFixture());
  old.reject(new Error("old network failure"));
  await pending;
  assert.equal(states.at(-1)?.status, "success");
  controller.dispose();
});

test("network failure is retriable; AbortError is not turned into a network error", async () => {
  browserIdentity();
  globalThis.fetch = async () => {
    throw new Error("network down");
  };
  const states: StatisticsDownloadState[] = [];
  const controller = new StatisticsDownloadController({
    onState: (state) => states.push(state),
    deliver: () => {},
  });
  await controller.start(statisticsFixture());
  const error = states.at(-1);
  assert.equal(error?.status, "error");
  if (error?.status === "error")
    assert.ok(error.message.includes("网络连接失败"));
  globalThis.fetch = async () => {
    throw new DOMException("aborted", "AbortError");
  };
  await assert.rejects(
    fetchFileStatistics(statisticsFixture(), new AbortController().signal),
    { name: "AbortError" },
  );
  globalThis.fetch = async () => Response.json(statisticsFixture());
  await controller.start(statisticsFixture());
  assert.equal(states.at(-1)?.status, "success");
  controller.dispose();
});

test("abort during response decoding prevents download even when fetch already completed", async () => {
  browserIdentity();
  const body = deferred<unknown>();
  const response = Response.json({});
  response.json = () => body.promise;
  globalThis.fetch = async () => response;
  const abort = new AbortController();
  const request = fetchFileStatistics(statisticsFixture(), abort.signal);
  await Promise.resolve();
  abort.abort();
  body.resolve(statisticsFixture());
  await assert.rejects(request, { name: "AbortError" });
});

for (const throws of [false, true]) {
  test(`Blob download uses a UUID-only filename and always releases URL/link (click throws=${throws})`, async () => {
    let blob: Blob | undefined;
    const revoked: string[] = [];
    let removed = false;
    const link = {
      href: "",
      download: "",
      click: () => {
        if (throws) throw new Error("blocked click");
      },
      remove: () => {
        removed = true;
      },
    };
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: { createElement: () => link, body: { appendChild: () => {} } },
    });
    URL.createObjectURL = (value) => {
      assert.ok(value instanceof Blob);
      blob = value;
      return "blob:controlled";
    };
    URL.revokeObjectURL = (url) => {
      revoked.push(url);
    };
    if (throws)
      assert.throws(
        () => saveStatisticsJson(statisticsFixture()),
        /blocked click/,
      );
    else saveStatisticsJson(statisticsFixture());
    assert.equal(
      link.download,
      "analysis-11111111-1111-4111-8111-111111111111.json",
    );
    assert.deepEqual(JSON.parse(await blob!.text()), statisticsFixture());
    assert.deepEqual(revoked, ["blob:controlled"]);
    assert.equal(removed, true);
  });
}
