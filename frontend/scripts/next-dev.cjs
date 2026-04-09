"use strict";

/**
 * Run `next dev` with the same sanitized NODE_OPTIONS as the repo root dev runner
 * (strip bad --localstorage-file; Node 25+ adds --no-experimental-webstorage).
 */
const { spawn } = require("child_process");
const path = require("path");
const { envForNextChild } = require("../../scripts/node-env-for-next.cjs");

const frontendRoot = path.join(__dirname, "..");
const nextBin = require.resolve("next/dist/bin/next", { paths: [frontendRoot] });

const child = spawn(process.execPath, [nextBin, "dev", "--turbopack"], {
  cwd: frontendRoot,
  env: envForNextChild(),
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code === null || code === undefined ? 1 : code);
});
