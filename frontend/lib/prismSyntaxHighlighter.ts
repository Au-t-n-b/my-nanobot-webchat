import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
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

/** 仅在浏览器执行注册，避免 SSR / 静态生成时 refractor 未就绪导致告警 */
export function ensurePrismLanguagesRegistered(): void {
  if (typeof window === "undefined" || prismRegistered) return;
  prismRegistered = true;
  SyntaxHighlighter.registerLanguage("bash", bash);
  SyntaxHighlighter.registerLanguage("css", css);
  SyntaxHighlighter.registerLanguage("javascript", javascript);
  SyntaxHighlighter.registerLanguage("json", json);
  SyntaxHighlighter.registerLanguage("jsx", jsx);
  SyntaxHighlighter.registerLanguage("markup", markup);
  SyntaxHighlighter.registerLanguage("python", python);
  SyntaxHighlighter.registerLanguage("rust", rust);
  SyntaxHighlighter.registerLanguage("toml", toml);
  SyntaxHighlighter.registerLanguage("tsx", tsx);
  SyntaxHighlighter.registerLanguage("typescript", typescript);
  SyntaxHighlighter.registerLanguage("yaml", yaml);
}

export { SyntaxHighlighter };
