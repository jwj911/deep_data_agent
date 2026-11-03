/** Real UI harness. Input is private stdin; never log tokens, passwords or traces. */
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
const { origins, fixtures, mode } = config;
for (const origin of [...Object.values(origins), config.control]) {
  const url = new URL(origin);
  assert.equal(url.protocol, "http:");
  assert.equal(url.hostname, "127.0.0.1");
  assert.equal(url.username + url.password, "");
}
const modulePath = process.env.DDA_PLAYWRIGHT_MODULE;
const { chromium } = await import(pathToFileURL(modulePath).href);
const require = createRequire(pathToFileURL(modulePath));
const playwrightVersion = require("./package.json").version;
const report = {
  gate: "controlled_analysis_browser",
  outcome: "failed",
  mode,
  playwright: playwrightVersion,
  checks: [],
  injections: [],
  statistics: [],
  clarifications: [],
  pending: [
    "service cancellation/timeout, shared budgets: backend agent evidence",
  ],
};
const browser = await chromium.launch({
  headless: !config.headed,
  args: [
    "--disable-background-networking",
    "--disable-component-update",
    "--no-default-browser-check",
  ],
});
report.browser = browser.version();
let stage = "anonymous_redirect";
let context;
let page;
let downloads = 0;
let externalAttempts = 0;
let foreignAuth = 0;
let activeRelease;
const uuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const threadUuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const answer = "Controlled provider observed the actual tool result.";
const clarificationAnswer = "Please specify one file and column.";
const textbox = () => page.getByPlaceholder("Deep Data Agent 为您服务...");
const card = () => page.getByTestId("statistics-card");
const downloadButton = () => page.getByTestId("statistics-download");
const statisticsUrl = (url) => {
  const parsed = new URL(url);
  return (
    parsed.origin === origins.rest &&
    /^\/api\/files\/[0-9a-f-]+\/statistics$/.test(parsed.pathname) &&
    parsed.searchParams.get("download") === "true"
  );
};

async function token() {
  const value = await page.evaluate(() => sessionStorage.getItem("auth_token"));
  assert.ok(value);
  return value;
}

async function api(path, options = {}, graph = false) {
  const headers = {
    Authorization: "Bearer " + (await token()),
    "X-Request-ID": randomBytes(16).toString("hex"),
    ...options.headers,
  };
  return context.request.fetch((graph ? origins.graph : origins.rest) + path, {
    ...options,
    headers,
    timeout: 30000,
  });
}

async function expectText(text) {
  await page.getByText(text, { exact: true }).first().waitFor();
}

async function cardCount(count) {
  await page.waitForFunction((expected) => {
    return (
      document.querySelectorAll('[data-testid="statistics-card"]').length ===
      expected
    );
  }, count);
}

async function registerAndLogin() {
  await page.goto(origins.frontend + "/", { waitUntil: "domcontentloaded" });
  await page.getByLabel("用户名", { exact: true }).waitFor();
  assert.equal(new URL(page.url()).origin, origins.frontend);
  assert.match(new URL(page.url()).pathname, /^\/login\/?$/);
  const username = "chat-gate-" + randomBytes(6).toString("hex");
  const password = randomBytes(20).toString("hex");
  stage = "ui_register";
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page
    .getByLabel("邮箱", { exact: true })
    .fill(username + "@example.com");
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "注册并登录", exact: true }).click();
  await textbox().waitFor();
  stage = "ui_logout_login";
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).waitFor();
  assert.equal(
    await page.evaluate(() => sessionStorage.getItem("auth_token")),
    null,
  );
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page
    .locator("form")
    .getByRole("button", { name: "登录", exact: true })
    .click();
  await textbox().waitFor();
  report.checks.push("real UI anonymous redirect / register / logout / login");
}

async function upload(fixture) {
  const uploaded = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.origin === origins.rest &&
      url.pathname === "/api/files" &&
      response.request().method() === "POST"
    );
  });
  await page.locator('input[type="file"]').setInputFiles(fixture.path);
  const response = await uploaded;
  assert.equal(response.status(), 201);
  const metadata = await response.json();
  assert.equal(metadata.length, 1);
  assert.ok(uuid.test(metadata[0].file_id));
  await expectText(fixture.name);
  assert.equal(metadata[0].size_bytes, fixture.size_bytes);
  return metadata[0];
}

async function newThread() {
  await page.getByRole("button", { name: "New thread", exact: true }).click();
  await page.waitForURL((url) => !url.searchParams.has("threadId"));
  await cardCount(0);
}

async function readTool(fixture, fileId) {
  stage = "read_actual_run";
  const threadId = new URL(page.url()).searchParams.get("threadId");
  assert.ok(threadUuid.test(threadId), "invalid_actual_thread_id");
  const runsResponse = await api(`/threads/${threadId}/runs`, {}, true);
  assert.equal(runsResponse.status(), 200);
  const runs = await runsResponse.json();
  report.runStatuses = runs.map((run) => run.status);
  assert.ok(runs.length, "actual_run_missing");
  assert.ok(
    runs.every((run) => run.status === "success"),
    "actual_run_not_success",
  );
  stage = "read_actual_tool";
  const stateResponse = await api(`/threads/${threadId}/state`, {}, true);
  assert.equal(stateResponse.status(), 200);
  const state = await stateResponse.json();
  const messages = state.values.messages;
  const calls = messages.flatMap((message) => message.tool_calls ?? []);
  assert.equal(calls.length, 1, "unexpected_actual_tool_call_count");
  const call = calls.find(
    (item) =>
      item.name === "analyze_file_statistics" &&
      item.args.file_id === fileId &&
      item.args.column === fixture.column,
  );
  assert.ok(call, "actual_statistics_tool_call_missing");
  assert.deepEqual(Object.keys(call.args).sort(), ["column", "file_id"]);
  const toolMessages = messages.filter(
    (message) => message.type === "tool" && message.tool_call_id === call.id,
  );
  assert.equal(toolMessages.length, 1, "actual_tool_message_count");
  assert.ok(!toolMessages[0].id?.startsWith("do-not-render"));
  const envelope = JSON.parse(toolMessages[0].content);
  assert.equal(envelope.type, "managed_file_statistics");
  assert.equal(envelope.version, 1);
  assert.equal(envelope.status, "success");
  assert.equal(envelope.data.source.file_id, fileId);
  const reference = messages.find((message) => message.type === "human");
  assert.ok(JSON.stringify(reference.content).includes("__managed_file_v1__:"));
  assert.ok(!JSON.stringify(reference.content).includes("base64"));
  return { data: envelope.data, threadId, callId: call.id };
}

async function successfulDownload(expected, keyboard = false) {
  stage = "real_download";
  const previous = downloads;
  const downloadEvent = page.waitForEvent("download");
  const requestEvent = page.waitForRequest((request) =>
    statisticsUrl(request.url()),
  );
  if (keyboard) {
    await downloadButton().focus();
    await page.keyboard.press("Enter");
  } else {
    await downloadButton().click();
  }
  const outbound = await requestEvent;
  assert.equal(outbound.method(), "POST");
  assert.deepEqual(outbound.postDataJSON(), {
    column: expected.parameters.column,
  });
  const headers = await outbound.allHeaders();
  assert.equal(headers.authorization, "Bearer " + (await token()));
  assert.match(headers["x-request-id"], /^[a-zA-Z0-9_-]{8,128}$/);
  const download = await downloadEvent;
  assert.match(download.suggestedFilename(), /^analysis-[0-9a-f-]{36}\.json$/);
  assert.ok(download.suggestedFilename().includes(expected.source.file_id));
  assert.equal(await download.failure(), null);
  const path = await download.path();
  const data = JSON.parse(await readFile(path, "utf8"));
  assert.deepEqual(data, expected);
  await download.delete();
  await page.waitForFunction(() => {
    const observation = window.__controlledAnalysis;
    return (
      observation.created > 0 && observation.created === observation.revoked
    );
  });
  assert.equal(downloads, previous + 1);
  return data;
}

async function verifyCard(data) {
  stage = "visible_card";
  await cardCount(1);
  await expectText("计算时快照");
  // Exact decimal remains text; no Number conversion in the oracle.
  assert.equal(
    await page.getByTestId("statistics-value").innerText(),
    data.result.value,
  );
  const counts = await card()
    .locator("dl")
    .first()
    .evaluate((element) =>
      Object.fromEntries(
        Array.from(element.children, (item) => [
          item.querySelector("dt")?.textContent,
          item.querySelector("dd")?.textContent,
        ]),
      ),
    );
  assert.deepEqual(counts, {
    总行数: String(data.row_count),
    有效数: String(data.result.valid_count),
    缺失数: String(data.result.missing_count),
    重复行数: String(data.duplicate_row_count),
  });
  const warningLabels = {
    unit_unspecified: "单位未指定",
    missing_values_excluded: "缺失值不参与计算",
    duplicate_rows_included: "重复行保留参与计算",
  };
  assert.deepEqual(
    await card()
      .getByRole("list", { name: "质量提示" })
      .locator("li")
      .allTextContents(),
    data.warnings.map((warning) => warningLabels[warning]),
  );
  await card().getByText(data.summary, { exact: true }).waitFor();
  const source = page.getByTestId("statistics-source-toggle");
  await source.focus();
  await page.keyboard.press("Enter");
  for (const value of [
    data.source.file_id,
    data.source.sha256,
    data.result_sha256,
    data.parser_version,
    data.analysis_version,
  ]) {
    assert.ok(
      (await page.getByTestId("statistics-source").innerText()).includes(value),
      "source_field_not_visible",
    );
  }
  const text = await card().innerText();
  assert.match(text, /缺失/);
  assert.match(text, /重复/);
  assert.match(text, /未指定/);
  const hide = page.getByRole("switch", { name: "Hide Tool Calls" });
  if ((await hide.getAttribute("aria-checked")) !== "true") await hide.click();
  await cardCount(1);
  assert.equal(
    await page.getByTestId("statistics-value").innerText(),
    data.result.value,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await downloadButton().scrollIntoViewIfNeeded();
  const layout = await downloadButton().evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return { left: bounds.left, right: bounds.right, width: innerWidth };
  });
  assert.ok(
    layout.left >= 0 && layout.right <= layout.width,
    "narrow_download_button_clipped",
  );
  await page.setViewportSize({ width: 1280, height: 900 });
  report.checks.push(
    "exact decimal / source / warnings / hidden details / keyboard / narrow viewport",
  );
}

async function clarify(fixture, index) {
  const reason = index === 0 ? "missing_column" : "multiple_files";
  stage = "real_chat_clarification_" + reason;
  if (index === 1) await upload(fixture.alternative);
  await textbox().fill(
    index === 0
      ? "Sum the entire attached file."
      : `Sum the attached data.\ncolumn=${JSON.stringify(fixture.column)}`,
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expectText(clarificationAnswer);
  await page.getByRole("button", { name: "Send", exact: true }).waitFor();
  await cardCount(0);
  const threadId = new URL(page.url()).searchParams.get("threadId");
  assert.ok(threadUuid.test(threadId), "clarification_thread_missing");
  const runsResponse = await api(`/threads/${threadId}/runs`, {}, true);
  assert.equal(runsResponse.status(), 200);
  const runs = await runsResponse.json();
  assert.equal(runs.length, 1);
  assert.equal(runs[0].status, "success");
  const stateResponse = await api(`/threads/${threadId}/state`, {}, true);
  assert.equal(stateResponse.status(), 200);
  const messages = (await stateResponse.json()).values.messages;
  const calls = messages.flatMap((message) => message.tool_calls ?? []);
  const toolMessages = messages.filter((message) => message.type === "tool");
  assert.equal(calls.length, 0, "clarification_issued_tool_call");
  assert.equal(toolMessages.length, 0, "clarification_produced_tool_message");
  const human = messages.filter((message) => message.type === "human");
  assert.equal(human.length, 1);
  const fileRefs = JSON.stringify(human[0].content).match(
    /__managed_file_v1__:/g,
  )?.length;
  assert.equal(fileRefs, index + 1);
  assert.ok(
    messages.some(
      (message) =>
        message.type === "ai" &&
        JSON.stringify(message.content).includes(clarificationAnswer),
    ),
    "actual_clarification_message_missing",
  );
  return {
    reason,
    threadId,
    runId: runs[0].run_id,
    runStatus: runs[0].status,
    fileRefs,
    toolCalls: calls.length,
    toolMessages: toolMessages.length,
    cards: await card().count(),
    scope: "controlled provider protocol/UI behavior, NOT real-model quality",
  };
}

async function analyze(fixture, index, withClarification = false) {
  stage = "ui_upload_" + fixture.name;
  if (index) await newThread();
  const metadata = await upload(fixture);
  let clarification;
  if (withClarification) {
    clarification = await clarify(fixture, index);
  }
  stage = "real_chat_" + fixture.name;
  // Reuse the real uploaded UUID in an explicit user turn, not a duplicate upload.
  const selectedReference = clarification
    ? `\nUse only the previously uploaded ${fixture.name}.\n__managed_file_v1__:${JSON.stringify({ file_id: metadata.file_id })}`
    : "";
  await textbox().fill(
    `Public fixture ${index}: sum the entire attached file.\ncolumn=${JSON.stringify(fixture.column)}${selectedReference}`,
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expectText(answer);
  await page.getByRole("button", { name: "Send", exact: true }).waitFor();
  const actual = await readTool(fixture, metadata.file_id);
  if (clarification) {
    assert.equal(actual.threadId, clarification.threadId);
    report.clarifications.push({
      ...clarification,
      explicitFollowup: {
        fileId: metadata.file_id,
        column: fixture.column,
        callId: actual.callId,
        status: "success",
      },
    });
  }
  await verifyCard(actual.data);
  const restResponse = await api(`/api/files/${metadata.file_id}/statistics`, {
    method: "POST",
    data: { column: fixture.column },
  });
  assert.equal(restResponse.status(), 200);
  const rest = await restResponse.json();
  assert.deepEqual(actual.data, rest);
  const downloaded = await successfulDownload(actual.data, true);
  report.statistics.push({
    fixture: fixture.name,
    tool: actual.data,
    rest,
    download: downloaded,
    callId: actual.callId,
  });
  return { ...actual, fixture, fileId: metadata.file_id };
}

async function retainHistory(actual) {
  stage = "history_restore";
  const current = new URL(page.url());
  await page.reload({ waitUntil: "domcontentloaded" });
  await downloadButton().waitFor();
  await cardCount(1);
  await expectText("计算时快照");
  assert.equal(
    new URL(page.url()).searchParams.get("threadId"),
    actual.threadId,
  );
  await newThread();
  // Navigate the public deep link, not React internals or a synthetic state.
  await page.goto(current.href, { waitUntil: "domcontentloaded" });
  await downloadButton().waitFor();
  await cardCount(1);
  await expectText("计算时快照");
  report.checks.push(
    "refresh + new thread + historical deep link: one real card, no cross-thread card",
  );
}

async function injectOnce(handler) {
  const routeHandler = async (route) => handler(route);
  await page.route(statisticsUrl, routeHandler, { times: 1 });
  return () => page.unroute(statisticsUrl, routeHandler);
}

async function networkRetry(actual) {
  stage = "response_injection_network_retry";
  const before = downloads;
  const remove = await injectOnce((route) => route.abort("failed"));
  try {
    await downloadButton().click();
    await page
      .getByText(/网络|无法连接|重试/)
      .first()
      .waitFor();
    assert.equal(downloads, before);
    await successfulDownload(actual.data);
  } finally {
    await remove();
  }
  report.injections.push(
    "network abort only; manual retry uses real REST and real download",
  );
}

async function versionChanged(actual) {
  stage = "response_injection_changed_version";
  const before = downloads;
  const remove = await injectOnce(async (route) => {
    const response = await route.fetch();
    assert.equal(response.status(), 200);
    const payload = await response.json();
    payload.analysis_version += "-response-injection";
    await route.fulfill({ response, json: payload });
  });
  try {
    await downloadButton().click();
    await page
      .getByText(/结果已变化|重新分析/)
      .first()
      .waitFor();
    assert.equal(downloads, before);
    await cardCount(1);
    assert.ok(
      (await page.locator("body").innerText()).includes(
        actual.data.result.value,
      ),
    );
  } finally {
    await remove();
  }
  report.injections.push(
    "real REST response with injected analysis_version change: rejected, history retained",
  );
}

async function delayedDownload(actual, action) {
  stage = "response_injection_delayed_" + action;
  const before = downloads;
  const observation = await page.evaluate(() => ({
    ...window.__controlledAnalysis,
  }));
  let entered;
  const entry = new Promise((resolve) => {
    entered = resolve;
  });
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  activeRelease = release;
  let finished;
  const done = new Promise((resolve) => {
    finished = resolve;
  });
  const remove = await injectOnce(async (route) => {
    try {
      const response = await route.fetch();
      entered();
      await gate;
      await route.fulfill({ response });
    } catch {
      // A page navigation or fetch AbortSignal can detach this response.
    } finally {
      finished();
    }
  });
  try {
    await downloadButton().click();
    await Promise.race([
      entry,
      new Promise((_, reject) => {
        const timeout = setTimeout(
          () => reject(new Error("delayed_request_not_received")),
          30000,
        );
        timeout.unref();
      }),
    ]);
    assert.equal(await downloadButton().isDisabled(), true);
    await downloadButton().focus();
    await page.keyboard.press("Enter");
    const during = await page.evaluate(() => ({
      ...window.__controlledAnalysis,
    }));
    assert.equal(during.requests, observation.requests + 1);
    const historyUrl = page.url();
    if (action === "thread") {
      await newThread();
      await page.waitForFunction(
        (aborted) => window.__controlledAnalysis.aborted > aborted,
        observation.aborted,
      );
    } else if (action === "logout") {
      await page.getByRole("button", { name: "退出登录", exact: true }).click();
      await page.getByLabel("用户名", { exact: true }).waitFor();
      assert.equal(
        await page.evaluate(() => sessionStorage.getItem("auth_token")),
        null,
      );
      await page.waitForFunction(
        (aborted) => window.__controlledAnalysis.aborted > aborted,
        observation.aborted,
      );
    } else {
      await page.goto(origins.frontend + "/login/", {
        waitUntil: "domcontentloaded",
      });
    }
    release();
    await done;
    assert.equal(downloads, before);
    if (action === "thread" || action === "unmount") {
      await page.goto(historyUrl, { waitUntil: "domcontentloaded" });
      await downloadButton().waitFor();
      await cardCount(1);
      assert.equal(downloads, before);
    }
    report.injections.push(
      `delayed real response + ${action}: disabled duplicate, aborted/detached, no late download`,
    );
  } finally {
    release();
    activeRelease = undefined;
    await remove();
  }
}

async function lifecycle(actual) {
  stage = "real_lifecycle_" + actual.fixture.lifecycle;
  const action = actual.fixture.lifecycle;
  if (action === "delete") {
    const response = await api(`/api/files/${actual.fileId}`, {
      method: "DELETE",
    });
    assert.equal(response.status(), 204);
  } else {
    // Test-only localhost controller mutates only this run's scratch DB/bytes.
    const response = await context.request.post(config.control + "/mutate", {
      headers: { "X-Harness-Key": config.controlKey },
      data: { action, file_id: actual.fileId },
    });
    assert.equal(response.status(), 200);
  }
  const before = downloads;
  const responseEvent = page.waitForResponse((response) =>
    statisticsUrl(response.url()),
  );
  await downloadButton().click();
  const response = await responseEvent;
  const failure = await response.json();
  if (action === "drift") {
    assert.equal(response.status(), 503);
    assert.equal(failure.detail.code, "file_storage_invalid");
    await page
      .getByText(/无法校验|完整性|源文件/)
      .first()
      .waitFor();
  } else {
    assert.equal(response.status(), 404);
    await page.getByText("源文件已不可用", { exact: false }).first().waitFor();
  }
  assert.equal(downloads, before);
  await cardCount(1);
  await expectText("计算时快照");
  await retainHistory(actual);
  assert.equal(downloads, before);
  report.checks.push(
    `real ${action}: download HTTP ${response.status()}, history retained`,
  );
}

async function unauthorized() {
  stage = "response_injection_401";
  const before = downloads;
  const remove = await injectOnce((route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        detail: { code: "invalid_token", message: "Unauthorized" },
      }),
    }),
  );
  try {
    await downloadButton().click();
    await page.getByLabel("用户名", { exact: true }).waitFor();
    assert.equal(
      await page.evaluate(() => sessionStorage.getItem("auth_token")),
      null,
    );
    assert.equal(downloads, before);
    report.injections.push(
      "injected REST 401: normal auth logout, no download",
    );
  } finally {
    await remove();
  }
}

async function runBrowser() {
  context = await browser.newContext({
    acceptDownloads: true,
    viewport: { width: 1280, height: 900 },
    serviceWorkers: "block",
  });
  const permitted = new Set(Object.values(origins));
  await context.route("**/*", async (route) => {
    const outbound = route.request();
    const url = new URL(outbound.url());
    if (
      ["http:", "https:"].includes(url.protocol) &&
      !permitted.has(url.origin)
    ) {
      externalAttempts++;
      await route.abort("blockedbyclient");
      return;
    }
    if (
      outbound.headers().authorization &&
      ![origins.rest, origins.graph].includes(url.origin)
    )
      foreignAuth++;
    await route.continue();
  });
  await context.routeWebSocket(/.*/, (socket) => {
    const url = new URL(socket.url());
    const httpOrigin = url.origin.replace(/^ws/, "http");
    if (permitted.has(httpOrigin)) socket.connectToServer();
    else {
      externalAttempts++;
      socket.close();
    }
  });
  // Observe native resource APIs, do not replace application results or state.
  await context.addInitScript(() => {
    const observation = { created: 0, revoked: 0, requests: 0, aborted: 0 };
    window.__controlledAnalysis = observation;
    const create = URL.createObjectURL.bind(URL);
    const revoke = URL.revokeObjectURL.bind(URL);
    const objects = new Set();
    URL.createObjectURL = (object) => {
      const url = create(object);
      objects.add(url);
      observation.created++;
      return url;
    };
    URL.revokeObjectURL = (url) => {
      if (objects.delete(url)) observation.revoked++;
      revoke(url);
    };
    const originalFetch = window.fetch.bind(window);
    window.fetch = (resource, init) => {
      const url = String(resource instanceof Request ? resource.url : resource);
      if (/\/statistics\?download=true$/.test(url)) {
        observation.requests++;
        const signal =
          init?.signal ??
          (resource instanceof Request ? resource.signal : undefined);
        signal?.addEventListener(
          "abort",
          () => {
            observation.aborted++;
          },
          { once: true },
        );
      }
      return originalFetch(resource, init);
    };
  });
  page = await context.newPage();
  page.setDefaultTimeout(45000);
  page.on("download", () => {
    downloads++;
  });
  await registerAndLogin();
  if (mode === "prepare") {
    for (const fixture of fixtures.slice(0, 2)) {
      stage = "prepare_upload_" + fixture.name;
      await upload(fixture);
    }
    assert.equal(new URL(page.url()).searchParams.get("threadId"), null);
    await cardCount(0);
    report.checks.push(
      "real UI uploaded public CSV + JSON beyond 20k; no statistics/chat run submitted",
    );
    report.pending.push("full statistics path awaits main agent authorization");
  } else {
    const cases = [];
    for (const [index, fixture] of fixtures.entries()) {
      const actual = await analyze(fixture, index, index < 2);
      cases.push(actual);
      if (index === 0) {
        await retainHistory(actual);
        await networkRetry(actual);
        await versionChanged(actual);
        await delayedDownload(actual, "thread");
        await delayedDownload(actual, "unmount");
      }
      if (fixture.lifecycle) await lifecycle(actual);
    }
    // Restore a still-live real source before the auth/abort negative cases.
    await page.goto(origins.frontend + "/?threadId=" + cases[0].threadId, {
      waitUntil: "domcontentloaded",
    });
    await downloadButton().waitFor();
    const savedToken = await token();
    await delayedDownload(cases[0], "logout");
    // Reauthenticate through the UI with a second fresh account, then return to
    // a real result owned by that account for the independent 401 injection.
    await registerAndLogin();
    const second = await analyze(fixtures[0], 0);
    report.statistics.pop(); // The five fixture cases are the numerical gate.
    assert.notEqual(await token(), savedToken);
    await unauthorized(second);
  }
  assert.equal(externalAttempts, 0, "browser_attempted_external_request");
  assert.equal(foreignAuth, 0, "authorization_outside_fixed_api_origins");
  report.network = { externalAttempts, foreignAuth, downloads };
  report.outcome = "passed";
}

function recordFailure(error) {
  report.outcome = "failed";
  report.stage = stage;
  report.failureType = error?.name ?? "Error";
  // The fixed assertion identifiers are safe; omit arbitrary Playwright messages.
  if (error?.code === "ERR_ASSERTION" && /^[a-z_]+$/.test(error.message))
    report.reason = error.message;
  report.failureLocation = error?.stack
    ?.split("\n")
    .find((line) => /verify_controlled_analysis_chat\.mjs:\d+:\d+/.test(line))
    ?.trim();
  if (
    error?.message?.includes("Target page, context or browser has been closed")
  )
    report.reason = "browser_target_closed";
}

let rejectUnexpected;
const unexpectedFailure = new Promise((_, reject) => {
  rejectUnexpected = reject;
});
const onUnexpected = (error) => {
  recordFailure(error);
  rejectUnexpected(error);
};
// Event-handler failures must fail the gate and still close owned resources.
process.on("unhandledRejection", onUnexpected);
try {
  await Promise.race([runBrowser(), unexpectedFailure]);
} catch (error) {
  recordFailure(error);
} finally {
  activeRelease?.();
  try {
    if (context) await context.close();
  } catch (error) {
    recordFailure(error);
  }
  try {
    await browser.close();
  } catch (error) {
    recordFailure(error);
  }
  process.removeListener("unhandledRejection", onUnexpected);
}
console.log(JSON.stringify(report));
if (report.outcome !== "passed") process.exitCode = 1;
