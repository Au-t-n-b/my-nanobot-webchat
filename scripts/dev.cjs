/**
 * Root dev runner (no external deps).
 *
 * Why:
 * - Some corporate networks block npm registries → `npm install` in repo root may fail.
 * - We only need to run 2 processes in parallel: Python AGUI + Next.js dev server.
 * - Avoid relying on `concurrently` so `npm run dev` works after `npm run setup` even if root npm install is skipped.
 */
const { spawn } = require("child_process");
const net = require("net");
const path = require("path");
const { envForNextChild } = require("./node-env-for-next.cjs");

const root = path.join(__dirname, "..");

function log(prefix, line) {
  const s = String(line ?? "").replace(/\r?\n$/, "");
  if (!s) return;
  process.stdout.write(`[${prefix}] ${s}\n`);
}

function spawnProc(name, command, args, options = {}) {
  const p = spawn(command, args, {
    cwd: root,
    shell: process.platform === "win32", // allow `python` on Windows PATH
    stdio: ["inherit", "pipe", "pipe"],
    ...options,
  });
  p.stdout.on("data", (d) => String(d).split(/\r?\n/).forEach((l) => log(name, l)));
  p.stderr.on("data", (d) => String(d).split(/\r?\n/).forEach((l) => log(name, l)));
  p.on("exit", (code, sig) => {
    if (sig) log(name, `exit signal=${sig}`);
    else log(name, `exit code=${code}`);
  });
  return p;
}

function canListenOnPort(port, host = "0.0.0.0") {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", (err) => {
      if (err && (err.code === "EADDRINUSE" || err.code === "EACCES")) {
        resolve(false);
        return;
      }
      resolve(false);
    });
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, host);
  });
}

async function main() {
  const aguiPort = 8765;
  const shouldSpawnAgui = await canListenOnPort(aguiPort);
  if (!shouldSpawnAgui) {
    log("agui", `port ${aguiPort} already in use, reusing existing AGUI instance`);
  }

  const agui = shouldSpawnAgui
    ? spawnProc("agui", "python", ["-m", "nanobot", "agui", "--port", String(aguiPort)])
    : null;
  const web = spawnProc("web", "npm", ["run", "dev", "--prefix", "frontend"], {
    env: envForNextChild(),
  });

  let closing = false;
  function shutdown(reason) {
    if (closing) return;
    closing = true;
    log("dev", `shutting down (${reason})...`);

    // Best-effort terminate children.
    try {
      if (process.platform === "win32") {
        if (web) {
          spawn("taskkill", ["/pid", String(web.pid), "/T", "/F"], { stdio: "ignore", shell: true });
        }
        if (agui) {
          spawn("taskkill", ["/pid", String(agui.pid), "/T", "/F"], { stdio: "ignore", shell: true });
        }
      } else {
        web.kill("SIGINT");
        agui?.kill("SIGINT");
        setTimeout(() => {
          try { web.kill("SIGKILL"); } catch {}
          try { agui?.kill("SIGKILL"); } catch {}
        }, 1200).unref();
      }
    } catch {}
  }

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));

  // If either exits, stop the other and exit.
  function bindExit(otherName) {
    return (code) => {
      shutdown(`peer exit (${otherName})`);
      process.exit(typeof code === "number" ? code : 1);
    };
  }

  web.on("exit", bindExit("web"));
  if (agui) {
    agui.on("exit", bindExit("agui"));
  }
}

main().catch((error) => {
  log("dev", error?.stack || error?.message || String(error));
  process.exit(1);
});

