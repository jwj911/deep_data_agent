import { build } from "esbuild";
import { mkdtemp, readdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

if (process.versions.node.split(".")[0] !== "22") {
  throw new Error("Behavior tests require the project's Node.js 22 runtime");
}

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const temporary = await mkdtemp(resolve(root, "../..", ".dda-chat-behavior-"));
try {
  const files = (await readdir(resolve(root, "tests"))).filter((file) =>
    file.endsWith(".test.ts"),
  );
  const outputs = [];
  for (const file of files) {
    const outfile = resolve(temporary, file.replace(/\.ts$/, ".cjs"));
    await build({
      absWorkingDir: root,
      entryPoints: [resolve(root, "tests", file)],
      outfile,
      bundle: true,
      platform: "node",
      format: "cjs",
      target: "node22",
      jsx: "automatic",
      define: {
        "process.env.NEXT_PUBLIC_REST_API_URL": JSON.stringify(
          "https://statistics.example.test/rest",
        ),
      },
    });
    outputs.push(outfile);
  }
  const result = spawnSync(
    process.execPath,
    ["--test", "--test-concurrency=1", ...outputs],
    { cwd: root, stdio: "inherit" },
  );
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally {
  await rm(temporary, { recursive: true, force: true });
}
