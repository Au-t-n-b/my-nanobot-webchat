import type { AgentMessage } from "@/hooks/useAgentChat";

export type IndexedFile = {
  path: string;
  fileName: string;
  sourceMessageId: string;
  sourceOrder: number;
  sourcePreview: string;
};

// Matches links injected by the backend proxy: /api/file?path=<encoded-path>
const FILE_LINK_RE = /\/api\/file\?path=([^\s)\]"'`]+)/g;

// Same extensions as AgentMarkdown.tsx normalizeAssistantLinks —
// catches backtick filenames the agent writes inline, e.g. `report.md`
const FILE_EXT_RE =
  "(?:mmd|md|markdown|txt|json|ya?ml|toml|csv|pdf|png|jpe?g|gif|webp|svg|xlsx?|docx|html?|xml|log|ini|ts|tsx|js|jsx|py|rs|sh)";
const BACKTICK_FILE_RE = new RegExp("`([^`\\n]+\\.(?:" + FILE_EXT_RE + "))`", "gi");
const WIN_PATH_RE = new RegExp(
  "(?<![`\\[(\\[])([A-Za-z]:[/\\\\][^\\s`\\]\\)\"'\\n]{3,}\\.(?:" + FILE_EXT_RE + "))",
  "gi",
);
const UNIX_PATH_RE = new RegExp(
  "(?<![`\\[(\\[])(\\/(?:home|Users|tmp|var|opt|workspace)[^\\s`\\]\\)\"'\\n]{3,}\\.(?:" + FILE_EXT_RE + "))",
  "gi",
);
// Matches skill-project relative paths: Output/xxx.xlsx, RunTime/xxx.xlsx, Input/xxx.xlsx
// The agent often writes these instead of full absolute paths in its replies.
const REL_PATH_RE = new RegExp(
  "(?<![`\\[(\\[A-Za-z0-9_/\\\\])(?:((?:Output|RunTime|Input|output|runtime|input)[/\\\\][^\\s`\\]\\)\"'\\n]{2,}\\.(?:" + FILE_EXT_RE + ")))",
  "gi",
);

function fileNameOf(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const name = normalized.split("/").filter(Boolean).pop();
  return name || path;
}

function previewOf(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > 48 ? `${normalized.slice(0, 47)}…` : normalized;
}

function addPath(
  raw: string,
  seen: Set<string>,
  out: IndexedFile[],
  meta: { sourceMessageId: string; sourceOrder: number; sourcePreview: string },
) {
  let path = raw;
  try {
    path = decodeURIComponent(raw);
  } catch {
    // keep raw
  }
  path = path.trim();
  if (!path || seen.has(path)) return;
  seen.add(path);
  out.push({ path, fileName: fileNameOf(path), ...meta });
}

export function extractFilesFromContent(content: string): string[] {
  const seen = new Set<string>();
  const paths: string[] = [];

  function add(raw: string) {
    let path = raw;
    try { path = decodeURIComponent(raw); } catch { /* keep raw */ }
    path = path.trim();
    if (!path || seen.has(path)) return;
    seen.add(path);
    paths.push(path);
  }

  FILE_LINK_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = FILE_LINK_RE.exec(content)) !== null) add(match[1] ?? "");

  BACKTICK_FILE_RE.lastIndex = 0;
  while ((match = BACKTICK_FILE_RE.exec(content)) !== null) add(match[1] ?? "");

  WIN_PATH_RE.lastIndex = 0;
  while ((match = WIN_PATH_RE.exec(content)) !== null) add(match[1] ?? "");

  UNIX_PATH_RE.lastIndex = 0;
  while ((match = UNIX_PATH_RE.exec(content)) !== null) add(match[1] ?? "");

  REL_PATH_RE.lastIndex = 0;
  while ((match = REL_PATH_RE.exec(content)) !== null) add(match[1] ?? "");

  return paths;
}

export function extractIndexedFiles(messages: AgentMessage[]): IndexedFile[] {
  const seen = new Set<string>();
  const out: IndexedFile[] = [];
  for (let i = 0; i < messages.length; i += 1) {
    const m = messages[i];
    if (m.role !== "assistant") continue;
    const meta = {
      sourceMessageId: m.id,
      sourceOrder: i,
      sourcePreview: previewOf(m.content),
    };

    if (m.content) {
      // 1. Explicit /api/file?path= links (agent or normalizer already converted them)
      FILE_LINK_RE.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = FILE_LINK_RE.exec(m.content)) !== null) {
        addPath(match[1] ?? "", seen, out, meta);
      }

      // 2. Backtick filenames the agent wrote inline, e.g. `project_gantt.mmd`
      //    normalizeAssistantLinks converts these to links only during render;
      //    we must scan the raw content ourselves here.
      BACKTICK_FILE_RE.lastIndex = 0;
      while ((match = BACKTICK_FILE_RE.exec(m.content)) !== null) {
        addPath(match[1] ?? "", seen, out, meta);
      }

      WIN_PATH_RE.lastIndex = 0;
      while ((match = WIN_PATH_RE.exec(m.content)) !== null) {
        addPath(match[1] ?? "", seen, out, meta);
      }

      UNIX_PATH_RE.lastIndex = 0;
      while ((match = UNIX_PATH_RE.exec(m.content)) !== null) {
        addPath(match[1] ?? "", seen, out, meta);
      }

      // 5. Skill-project relative paths: Output/xxx.xlsx, RunTime/xxx.xlsx, etc.
      REL_PATH_RE.lastIndex = 0;
      while ((match = REL_PATH_RE.exec(m.content)) !== null) {
        addPath(match[1] ?? "", seen, out, meta);
      }
    }

    // 3. Paths inferred from tool-execution step logs (persisted on message.artifacts)
    if (Array.isArray(m.artifacts)) {
      for (const raw of m.artifacts) {
        if (typeof raw === "string") addPath(raw, seen, out, meta);
      }
    }
  }
  return out.sort((a, b) => b.sourceOrder - a.sourceOrder);
}

