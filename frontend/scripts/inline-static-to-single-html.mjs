/**
 * 将 Next.js ``out/`` 静态导出合并为单个 ``.html``（内联 CSS/JS/字体等）。
 * 依赖构建时已关闭 code splitting（见 next.config.ts + 静态导出模式）。
 */

import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

function readBin(p) {
  return fs.readFileSync(p);
}

function readUtf8(p) {
  return fs.readFileSync(p, "utf8");
}

function resolveWebPath(outDir, webPath) {
  const clean = webPath.replace(/^\//, "").replace(/^\.\//, "");
  return path.join(outDir, clean);
}

function mimeFromExt(ext) {
  const m = {
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".eot": "application/vnd.ms-fontobject",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
  };
  return m[ext.toLowerCase()] ?? "application/octet-stream";
}

function toDataUri(buf, mime) {
  return `data:${mime};base64,${buf.toString("base64")}`;
}

function inlineUrlsInCss(css, cssAbsPath, outDir) {
  const cssDir = path.dirname(cssAbsPath);
  return css.replace(/url\(\s*(['"]?)([^'")]+?)\1\s*\)/g, (full, quote, inner) => {
    const u = inner.trim();
    if (u.startsWith("data:") || u.startsWith("blob:")) return full;
    let abs;
    if (u.startsWith("/")) abs = resolveWebPath(outDir, u);
    else abs = path.resolve(cssDir, u);
    if (!fs.existsSync(abs)) return full;
    const buf = readBin(abs);
    const ext = path.extname(abs);
    const mime = mimeFromExt(ext);
    const q = quote || "";
    return `url(${q}${toDataUri(buf, mime)}${q})`;
  });
}

/** 避免内联的 ``</script>`` 提前结束标签 */
function escapeScriptContent(js) {
  return js.replace(/<\/script>/gi, "<\\/script>");
}

function inlineStylesheets(html, outDir) {
  return html.replace(/<link\s+([^>]*?)>/gi, (full, inner) => {
    if (!/rel\s*=\s*["']stylesheet["']/i.test(inner)) return full;
    const hrefM = inner.match(/href\s*=\s*["']([^"']+)["']/i);
    if (!hrefM) return full;
    const href = hrefM[1];
    if (href.startsWith("data:")) return full;
    const abs = resolveWebPath(outDir, href);
    if (!fs.existsSync(abs)) return full;
    let css = readUtf8(abs);
    css = inlineUrlsInCss(css, abs, outDir);
    return `<style>${css}</style>`;
  });
}

function stripPreloadScripts(html) {
  return html.replace(/<link\s+[^>]*rel\s*=\s*["']preload["'][^>]*as\s*=\s*["']script["'][^>]*\/?>/gi, "");
}

function inlineScriptTags(html, outDir) {
  let prev = "";
  let cur = html;
  while (cur !== prev) {
    prev = cur;
    cur = cur.replace(
      /<script([^>]*?)\ssrc\s*=\s*["']([^"']+)["']([^>]*)>\s*<\/script>/i,
      (full, before, src, after) => {
        const abs = resolveWebPath(outDir, src);
        if (!fs.existsSync(abs)) {
          throw new Error(`内联脚本缺失: ${src} -> ${abs}`);
        }
        let js = readUtf8(abs);
        js = escapeScriptContent(js);
        let attrs = `${before} ${after}`
          .replace(/\s+src\s*=\s*["'][^"']*["']/gi, "")
          .replace(/\basync\b/gi, "")
          .replace(/\bdefer\b/gi, "")
          .replace(/\s+/g, " ")
          .trim();
        return `<script${attrs ? ` ${attrs}` : ""}>${js}</script>`;
      },
    );
  }
  return cur;
}

function inlineFavicon(html, outDir) {
  return html.replace(
    /<link\s+([^>]*rel\s*=\s*["']icon["'][^>]*)\/?>/gi,
    (full, inner) => {
      const hrefM = inner.match(/href\s*=\s*["']([^"']+)["']/i);
      if (!hrefM) return full;
      const href = hrefM[1];
      if (href.startsWith("data:")) return full;
      const abs = resolveWebPath(outDir, href);
      if (!fs.existsSync(abs)) return full;
      const buf = readBin(abs);
      const mime = mimeFromExt(path.extname(abs));
      const data = toDataUri(buf, mime);
      const newInner = inner.replace(/href\s*=\s*["'][^"']*["']/i, `href="${data}"`);
      return `<link ${newInner}>`;
    },
  );
}

/**
 * @param {string} outDir Next ``out`` 目录
 * @param {string} destHtml 输出的单文件路径
 */
export function inlineStaticDirToSingleHtml(outDir, destHtml) {
  const indexPath = path.join(outDir, "index.html");
  if (!fs.existsSync(indexPath)) {
    throw new Error(`未找到 ${indexPath}`);
  }
  let html = readUtf8(indexPath);
  html = inlineStylesheets(html, outDir);
  html = stripPreloadScripts(html);
  html = inlineScriptTags(html, outDir);
  html = inlineFavicon(html, outDir);
  fs.mkdirSync(path.dirname(destHtml), { recursive: true });
  fs.writeFileSync(destHtml, html, "utf8");
}

function cli() {
  const outDir = process.argv[2];
  const dest = process.argv[3];
  if (!outDir || !dest) {
    console.error("用法: node scripts/inline-static-to-single-html.mjs <out目录> <输出.html>");
    process.exit(1);
  }
  inlineStaticDirToSingleHtml(path.resolve(outDir), path.resolve(dest));
  console.log("已写入:", path.resolve(dest));
}

const entry = process.argv[1];
if (entry && import.meta.url === pathToFileURL(path.resolve(entry)).href) {
  cli();
}
