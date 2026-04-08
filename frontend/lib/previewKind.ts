import { normalizeSyntheticSkillUiPath } from "@/lib/skillUiRegistry";

export type PreviewKind =
  | "browser"
  | "skill-ui"
  | "image"
  | "pdf"
  | "html"
  | "md"
  | "xlsx"
  | "docx"
  | "mermaid"
  | "text"
  | "binary";

export function previewKindFromPath(path: string): PreviewKind {
  if (path.startsWith("browser://")) return "browser";
  if (normalizeSyntheticSkillUiPath(path).startsWith("skill-ui://")) return "skill-ui";

  const i = path.lastIndexOf(".");
  const ext = i >= 0 ? path.slice(i + 1).toLowerCase() : "";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) return "image";
  if (ext === "pdf") return "pdf";
  if (["html", "htm"].includes(ext)) return "html";
  if (["md", "markdown"].includes(ext)) return "md";
  if (["xlsx", "xls"].includes(ext)) return "xlsx";
  if (ext === "docx") return "docx";
  if (["mmd", "mermaid"].includes(ext)) return "mermaid";
  if (
    [
      "txt",
      "json",
      "csv",
      "ts",
      "tsx",
      "js",
      "jsx",
      "py",
      "rs",
      "toml",
      "yaml",
      "yml",
      "xml",
      "css",
      "sh",
      "ini",
      "log",
    ].includes(ext)
  ) {
    return "text";
  }
  return "binary";
}
