import type { AgentMessage } from "@/hooks/useAgentChat";

export type IndexedFile = {
  path: string;
  fileName: string;
};

const FILE_LINK_RE = /\/api\/file\?path=([^\s)\]"'`]+)/g;

function fileNameOf(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const name = normalized.split("/").filter(Boolean).pop();
  return name || path;
}

export function extractIndexedFiles(messages: AgentMessage[]): IndexedFile[] {
  const seen = new Set<string>();
  const out: IndexedFile[] = [];
  for (const m of messages) {
    if (m.role !== "assistant" || !m.content) continue;
    FILE_LINK_RE.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = FILE_LINK_RE.exec(m.content)) !== null) {
      const raw = match[1] ?? "";
      let path = raw;
      try {
        path = decodeURIComponent(raw);
      } catch {
        // keep raw
      }
      path = path.trim();
      if (!path || seen.has(path)) continue;
      seen.add(path);
      out.push({ path, fileName: fileNameOf(path) });
    }
  }
  return out;
}

