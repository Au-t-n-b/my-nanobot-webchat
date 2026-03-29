/**
 * 在临时目录复制项目、去掉 app/api 后执行静态导出，
 * 合并为单个 ``nanobot-frontend.html`` 写入桌面。
 */

import { execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inlineStaticDirToSingleHtml } from "./inline-static-to-single-html.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.join(__dirname, "..");

function resolveDesktopDir() {
  if (process.platform === "win32") {
    const fromProfile =
      process.env.USERPROFILE && path.join(process.env.USERPROFILE, "Desktop");
    if (fromProfile && fs.existsSync(fromProfile)) return fromProfile;
    const zh = path.join(os.homedir(), "桌面");
    if (fs.existsSync(zh)) return zh;
  }
  return path.join(os.homedir(), "Desktop");
}

function shouldCopyEntry(src) {
  const base = path.basename(src);
  if (base === "node_modules" || base === ".next" || base === "out") return false;
  return true;
}

function copyProjectFiltered(from, to) {
  fs.mkdirSync(to, { recursive: true });
  for (const name of fs.readdirSync(from, { withFileTypes: true })) {
    const srcPath = path.join(from, name.name);
    if (!shouldCopyEntry(srcPath)) continue;
    const destPath = path.join(to, name.name);
    if (name.isDirectory()) {
      copyProjectFiltered(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "nanobot-static-"));
  try {
    copyProjectFiltered(frontendRoot, tempRoot);

    const apiDir = path.join(tempRoot, "app", "api");
    if (!fs.existsSync(apiDir)) {
      console.error("临时目录中未找到 app/api");
      process.exit(1);
    }
    fs.rmSync(apiDir, { recursive: true, force: true });

    execSync("npm ci", {
      cwd: tempRoot,
      stdio: "inherit",
      env: { ...process.env },
    });

    execSync("npm run build", {
      cwd: tempRoot,
      stdio: "inherit",
      env: {
        ...process.env,
        NANOBOT_STATIC_EXPORT: "1",
        NEXT_PUBLIC_AGUI_DIRECT: "1",
        NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765",
      },
    });

    const outDir = path.join(tempRoot, "out");
    if (!fs.existsSync(outDir)) {
      console.error("构建未生成 out/ 目录");
      process.exit(1);
    }

    const desktop = resolveDesktopDir();
    const destHtml = path.join(desktop, "nanobot-frontend.html");
    const fallbackHtml = path.join(frontendRoot, "..", "nanobot-frontend.html");

    try {
      inlineStaticDirToSingleHtml(outDir, destHtml);
    } catch (e) {
      console.error("合并单文件 HTML 失败:", e);
      try {
        inlineStaticDirToSingleHtml(outDir, fallbackHtml);
        console.log("");
        console.log("已写入备用路径:", path.resolve(fallbackHtml));
        console.log("");
      } catch (e2) {
        console.error("备用路径也失败:", e2);
        process.exit(1);
      }
      process.exit(0);
    }

    console.log("");
    console.log("单文件已导出到:", destHtml);
    console.log("用法: 双击或拖到浏览器打开（需本机 AGUI 已启动，默认 127.0.0.1:8765）。");
    console.log("");
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

main();
