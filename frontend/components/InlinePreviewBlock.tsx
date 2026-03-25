"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { buildProxiedFileUrl } from "@/lib/apiFile";

type InlineState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "mermaid"; svg: string }
  | { status: "text"; lang: string; content: string };

const LANG_MAP: Record<string, string> = {
  ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
  py: "python", rs: "rust", sh: "bash", json: "json", yaml: "yaml", yml: "yaml",
  toml: "toml", csv: "csv", txt: "text", log: "text", xml: "xml",
};

function extOf(path: string): string {
  return (path.split(".").pop() ?? "").toLowerCase();
}

export function InlinePreviewBlock({ path, onClose }: { path: string; onClose: () => void }) {
  const [state, setState] = useState<InlineState>({ status: "loading" });
  const filename = path.replace(/\\/g, "/").split("/").pop() ?? path;
  const ext = extOf(path);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    (async () => {
      try {
        const res = await fetch(buildProxiedFileUrl(path));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const text = await res.text();
        if (cancelled) return;
        if (ext === "mmd") {
          const m = await import("mermaid");
          m.default.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
          const id = `mmd-inline-${Date.now()}`;
          const { svg } = await m.default.render(id, text);
          if (!cancelled) setState({ status: "mermaid", svg });
        } else {
          setState({ status: "text", lang: LANG_MAP[ext] ?? ext, content: text });
        }
      } catch (e) {
        if (!cancelled) setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
      }
    })();
    return () => { cancelled = true; };
  }, [path, ext]);

  return (
    <div className="my-2 rounded-xl ui-card text-xs p-2">
      <div className="flex items-center justify-between px-1 pb-1">
        <span className="font-mono ui-text-muted truncate max-w-[80%]" title={path}>
          {filename}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭内嵌预览"
          className="rounded p-1 ui-text-muted hover:bg-[var(--surface-3)] transition-colors"
        >
          <X size={12} />
        </button>
      </div>
      <div className="max-h-[300px] overflow-auto p-2">
        {state.status === "loading" && <span className="ui-text-muted">加载中…</span>}
        {state.status === "error" && <span style={{ color: "var(--danger)" }}>{state.message}</span>}
        {state.status === "mermaid" && (
          <div className="[&_svg]:max-w-full [&_svg]:h-auto" dangerouslySetInnerHTML={{ __html: state.svg }} />
        )}
        {state.status === "text" && (
          <pre className="font-mono whitespace-pre-wrap ui-text-secondary leading-relaxed">{state.content}</pre>
        )}
      </div>
    </div>
  );
}
