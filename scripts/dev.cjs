/**
 * Root dev runner (no external deps).
 *
 * Why:
 * - Some corporate networks block npm registries → `npm install` in repo root may fail.
 * - We only need to run 2 processes in parallel: Python AGUI + Next.js dev server.
 * - Avoid relying on `concurrently` so `npm run dev` works after `npm run setup` even if root npm install is skipped.
 */
const { spawn, execSync } = require("child_process");
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

/** 启动 AGUI 前打印 PATH 上实际会用的 python，便于与「手动开终端」时的解释器对比。 */
function resolvePythonExecutableHint() {
  try {
    if (process.platform === "win32") {
      const out = execSync("where python", {
        encoding: "utf8",
        shell: true,
        cwd: root,
        timeout: 8000,
        stdio: ["ignore", "pipe", "pipe"],
      }).trim();
      const line = out
        .split(/\r?\n/)
        .map((s) => s.trim())
        .find((s) => s && !s.toLowerCase().includes("information"));
      return line || "python（未解析到路径，将依赖 PATH）";
    }
    let out = "";
    try {
      out = execSync("command -v python3 2>/dev/null", {
        encoding: "utf8",
        shell: true,
        cwd: root,
        timeout: 8000,
        stdio: ["ignore", "pipe", "pipe"],
      }).trim();
    } catch {
      /* ignore */
    }
    if (out) return out;
    out = execSync("command -v python 2>/dev/null", {
      encoding: "utf8",
      shell: true,
      cwd: root,
      timeout: 8000,
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
    return out || "python（未解析到路径，将依赖 PATH）";
  } catch {
    return "python（解析失败，将使用 PATH 中的 python）";
  }
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
    log("agui", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    log("agui", `警告：端口 ${aguiPort} 已被占用，本脚本不会启动新的 AGUI。`);
    log("agui", "前端仍会启动，但请求会打到「当前已在监听该端口」的进程（可能是旧实例或其它程序）。");
    log("agui", "若模型连不上或行为异常：请先结束占用端口的进程，再重新执行 npm run dev。");
    if (process.platform === "win32") {
      log("agui", "Windows 可执行: netstat -ano | findstr :8765   再用 taskkill /PID <pid> /F");
    } else {
      log("agui", "POSIX 可查: ss -lntp | grep 8765  或  lsof -i :8765");
    }
    log("agui", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  } else {
    const py = resolvePythonExecutableHint();
    log("dev", `将用此 Python 启动 AGUI: ${py}`);
    log(
      "dev",
      "若内网访问外网模型需代理，请在本终端已配置 HTTPS_PROXY/HTTP_PROXY，或写入系统环境变量后再运行 npm run dev。",
    );
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

