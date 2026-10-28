/** Real UI actions against an isolated deployment; no traces or credentials logged. */
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { pathToFileURL } from "node:url";

const { chromium } = await import(pathToFileURL(process.env.DDA_PLAYWRIGHT_MODULE).href);
const origin = "http://localhost:3000";
const graphOrigin = "http://localhost:2024";
const browser = await chromium.launch({ headless: true });
let stage = "anonymous_redirect";
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  await page.goto(origin + "/data_copilot/?gate=browser", { waitUntil: "domcontentloaded" });
  await page.getByLabel("用户名", { exact: true }).waitFor();
  assert.equal(new URL(page.url()).origin, origin);
  assert.equal(new URL(page.url()).pathname, "/data_copilot/login/");
  stage = "registration";
  const username = "browser-" + randomBytes(6).toString("hex");
  const password = randomBytes(20).toString("hex");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("邮箱", { exact: true }).fill(username + "@example.com");
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "注册并登录", exact: true }).click();
  await page.getByPlaceholder("Deep Data Agent 为您服务...").waitFor();
  stage = "conversation";
  await page.getByPlaceholder("Deep Data Agent 为您服务...").fill("browser controlled canary");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByText("isolated model canary", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Send", exact: true }).waitFor();
  const threadId = new URL(page.url()).searchParams.get("threadId");
  assert.ok(threadId);
  // Read the browser's own session token in memory only; do not persist it.
  const token = await page.evaluate(() => sessionStorage.getItem("auth_token"));
  assert.ok(token);
  const runs = await context.request.get(graphOrigin + "/threads/" + threadId + "/runs", {
    headers: { Authorization: "Bearer " + token },
  });
  assert.equal(runs.status(), 200);
  assert.deepEqual((await runs.json()).map(run => run.status), ["success"]);
  stage = "deep_link_refresh";
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByText("isolated model canary", { exact: true }).waitFor();
  assert.equal(new URL(page.url()).searchParams.get("threadId"), threadId);
  stage = "logout";
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).waitFor();
  assert.equal(new URL(page.url()).origin, origin);
  assert.equal(await page.evaluate(() => sessionStorage.getItem("auth_token")), null);
  stage = "wrong_password";
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password + "wrong");
  await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "用户名或密码错误" }).waitFor();
  assert.equal(await page.evaluate(() => sessionStorage.getItem("auth_token")), null);
  stage = "login_again";
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();
  await page.getByPlaceholder("Deep Data Agent 为您服务...").waitFor();
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).waitFor();
  console.log(JSON.stringify({
    gate: "browser_ui", outcome: "passed", browser: "Chromium",
    checks: ["anonymous redirect retains port", "register and login", "rendered answer and successful run",
      "deep link refresh retains history", "logout clears token", "wrong password denied", "login again"],
    model: "controlled TCP/SSE provider",
  }));
} catch {
  console.log(JSON.stringify({ gate: "browser_ui", outcome: "failed", stage }));
  process.exitCode = 1;
} finally {
  await browser.close();
}
