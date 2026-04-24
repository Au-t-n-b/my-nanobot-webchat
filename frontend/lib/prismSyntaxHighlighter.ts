import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx";
import markup from "react-syntax-highlighter/dist/esm/languages/prism/markup";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import rust from "react-syntax-highlighter/dist/esm/languages/prism/rust";
import toml from "react-syntax-highlighter/dist/esm/languages/prism/toml";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import yaml from "react-syntax-highlighter/dist/esm/languages/prism/yaml";

/** 与 ``EXT_TO_LANG`` / 常见围栏语言对齐，避免 PrismAsyncLight 按语言拆 chunk */
export const PRISM_LANGUAGE_IDS = new Set([
  "bash",
  "css",
  "javascript",
  "json",
  "jsx",
  "markup",
  "python",
  "rust",
  "toml",
  "tsx",
  "typescript",
  "yaml",
]);

let prismRegistered = false;
const PRISM_REGISTERED_FLAG = "__NANOBOT_PRISM_LANGS_REGISTERED__";

type MaybeWindow = Window & { [PRISM_REGISTERED_FLAG]?: boolean };

function isAlreadyRegistered(): boolean {
  if (prismRegistered) return true;
  if (typeof window === "undefined") return false;
  return Boolean((window as MaybeWindow)[PRISM_REGISTERED_FLAG]);
}

function markRegistered(): void {
  prismRegistered = true;
  if (typeof window !== "undefined") {
    (window as MaybeWindow)[PRISM_REGISTERED_FLAG] = true;
  }
}

function registerLanguageSafe(id: string, def: unknown): void {
  try {
    SyntaxHighlighter.registerLanguage(id, def as never);
  } catch {
    // HMR / Fast Refresh may reload modules and try to re-register the
    // same Prism language; ignore duplicate-registration errors.
  }
}

/** 仅在浏览器执行注册，避免 SSR / 静态生成时 refractor 未就绪导致告警 */
export function ensurePrismLanguagesRegistered(): void {
  if (typeof window === "undefined" || isAlreadyRegistered()) return;
  registerLanguageSafe("bash", bash);
  registerLanguageSafe("css", css);
  registerLanguageSafe("javascript", javascript);
  registerLanguageSafe("json", json);
  registerLanguageSafe("jsx", jsx);
  registerLanguageSafe("markup", markup);
  registerLanguageSafe("python", python);
  registerLanguageSafe("rust", rust);
  registerLanguageSafe("toml", toml);
  registerLanguageSafe("tsx", tsx);
  registerLanguageSafe("typescript", typescript);
  registerLanguageSafe("yaml", yaml);
  markRegistered();
}

export { SyntaxHighlighter };
