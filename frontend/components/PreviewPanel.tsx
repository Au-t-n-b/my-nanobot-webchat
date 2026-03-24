"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { Eye, EyeOff, FileQuestion, Loader2 } from "lucide-react";
import * as XLSX from "xlsx";
import mammoth from "mammoth/mammoth.browser.js";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import { buildFileUrl } from "@/lib/apiFile";
import { previewKindFromPath, type PreviewKind } from "@/lib/previewKind";

type Props = {
  visible: boolean;
  onToggle: () => void;
  apiBase: string;
  filePath: string | null;
  onClearFile: () => void;
  onOpenPath: (path: string) => void;
};

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "embed"; kind: "image" | "pdf" | "html"; url: string }
  | { status: "text"; text: string; markdown: boolean }
  | { status: "html"; html: string }
  | { status: "table"; rows: string[][] }
  | { status: "mermaid"; svg: string }
  | { status: "binary"; url: string; name: string };

function FilePreviewBody({
  apiBase,
  path,
  onOpenPath,
}: {
  apiBase: string;
  path: string;
  onOpenPath: (path: string) => void;
}) {
  const [state, setState] = useState<PreviewState>({ status: "loading" });
  const url = useMemo(() => buildFileUrl(apiBase, path), [apiBase, path]);
  const kind: PreviewKind = useMemo(() => previewKindFromPath(path), [path]);
  const mermaidId = useId().replace(/:/g, "");

  useEffect(() => {
    if (kind === "binary") {
      const name = path.split(/[/\\]/).pop() ?? "file";
      setState({ status: "binary", url, name });
      return;
    }

    if (kind === "image" || kind === "pdf" || kind === "html") {
      setState({ status: "embed", kind, url });
      return;
    }

    let cancelled = false;
    setState({ status: "loading" });

    (async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) {
          const t = await res.text().catch(() => "");
          throw new Error(t || `HTTP ${res.status}`);
        }

        if (kind === "md" || kind === "text" || kind === "mermaid") {
          const text = await res.text();
          if (cancelled) return;
          if (kind === "mermaid") {
            const m = await import("mermaid");
            m.default.initialize({
              startOnLoad: false,
              theme: "dark",
              securityLevel: "strict",
            });
            const { svg } = await m.default.render(`mmd-${mermaidId}`, text);
            if (!cancelled) setState({ status: "mermaid", svg });
            return;
          }
          if (kind === "md") {
            setState({ status: "text", text, markdown: true });
            return;
          }
          setState({ status: "text", text, markdown: false });
          return;
        }

        if (kind === "xlsx") {
          const buf = await res.arrayBuffer();
          if (cancelled) return;
          const wb = XLSX.read(buf, { type: "array" });
          const sheetName = wb.SheetNames[0];
          if (!sheetName) throw new Error("empty workbook");
          const sheet = wb.Sheets[sheetName];
          const rows = XLSX.utils.sheet_to_json<string[]>(sheet, {
            header: 1,
            defval: "",
          }) as string[][];
          setState({ status: "table", rows });
          return;
        }

        if (kind === "docx") {
          const buf = await res.arrayBuffer();
          if (cancelled) return;
          const { value } = await mammoth.convertToHtml({ arrayBuffer: buf });
          setState({ status: "html", html: value });
        }
      } catch (e) {
        if (!cancelled) setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [apiBase, path, url, kind, mermaidId]);

  if (state.status === "loading") {
    return (
      <div className="flex items-center justify-center gap-2 text-zinc-400 text-sm py-8">
        <Loader2 className="animate-spin" size={18} />
        加载中…
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="rounded-md border border-red-900/60 bg-red-950/30 text-red-200 text-sm p-3 whitespace-pre-wrap">
        {state.message}
      </div>
    );
  }

  if (state.status === "embed") {
    if (state.kind === "image") {
      // eslint-disable-next-line @next/next/no-img-element
      return <img src={state.url} alt="" className="max-w-full max-h-[min(70vh,800px)] object-contain mx-auto" />;
    }
    return (
      <iframe
        title="preview"
        src={state.url}
        className="w-full flex-1 min-h-[min(70vh,800px)] rounded border border-zinc-700 bg-white"
      />
    );
  }

  if (state.status === "text" && state.markdown) {
    return (
      <div className="max-w-none overflow-auto text-sm">
        <AgentMarkdown content={state.text} onPreviewPath={onOpenPath} />
      </div>
    );
  }

  if (state.status === "text") {
    return (
      <pre className="text-xs text-zinc-300 overflow-auto whitespace-pre-wrap font-mono p-2 rounded border border-zinc-800 bg-zinc-950/80 max-h-[min(70vh,800px)]">
        {state.text}
      </pre>
    );
  }

  if (state.status === "html") {
    return (
      <div
        className="max-w-none overflow-auto text-sm text-zinc-200 p-2 border border-zinc-800 rounded bg-zinc-950/50 max-h-[min(70vh,800px)] [&_a]:text-sky-400 [&_p]:mb-2"
        dangerouslySetInnerHTML={{ __html: state.html }}
      />
    );
  }

  if (state.status === "table") {
    return (
      <div className="overflow-auto max-h-[min(70vh,800px)] border border-zinc-800 rounded">
        <table className="text-xs text-zinc-200 border-collapse w-full">
          <tbody>
            {state.rows.map((row, i) => (
              <tr key={i} className="border-b border-zinc-800">
                {row.map((cell, j) => (
                  <td key={j} className="border-r border-zinc-800 px-2 py-1 align-top">
                    {String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (state.status === "mermaid") {
    return (
      <div
        className="overflow-auto flex justify-center items-start p-2 max-h-[min(70vh,800px)]"
        dangerouslySetInnerHTML={{ __html: state.svg }}
      />
    );
  }

  if (state.status === "binary") {
    return (
      <div className="text-sm text-zinc-400 flex flex-col gap-3 items-start">
        <FileQuestion size={32} className="text-zinc-500" />
        <p>无法内联预览此类型，可通过下方链接下载。</p>
        <a
          href={state.url}
          download={state.name}
          className="rounded-md bg-sky-700/80 hover:bg-sky-600 px-3 py-1.5 text-zinc-100"
        >
          打开 / 下载 {state.name}
        </a>
      </div>
    );
  }

  return null;
}

export function PreviewPanel({
  visible,
  onToggle,
  apiBase,
  filePath,
  onClearFile,
  onOpenPath,
}: Props) {
  if (!visible) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="h-full rounded-xl border border-zinc-800 bg-zinc-900/40 text-zinc-400 text-sm px-3"
      >
        <span className="inline-flex items-center gap-2">
          <Eye size={14} /> 打开预览栏
        </span>
      </button>
    );
  }

  return (
    <aside className="h-full rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 flex flex-col gap-3 min-h-0">
      <div className="flex items-center justify-between gap-2 shrink-0">
        <h2 className="text-sm font-medium text-zinc-200 truncate">预览</h2>
        <div className="flex items-center gap-2 shrink-0">
          {filePath && (
            <button type="button" onClick={onClearFile} className="text-xs text-zinc-500 hover:text-zinc-300">
              清除
            </button>
          )}
          <button type="button" onClick={onToggle} className="text-zinc-400 hover:text-zinc-200" aria-label="收起预览">
            <EyeOff size={14} />
          </button>
        </div>
      </div>
      {filePath && (
        <p className="text-xs text-zinc-500 break-all shrink-0" title={filePath}>
          {filePath}
        </p>
      )}
      <div className="flex-1 min-h-0 overflow-auto rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
        {filePath ? (
          <FilePreviewBody key={filePath} apiBase={apiBase} path={filePath} onOpenPath={onOpenPath} />
        ) : (
          <p className="text-zinc-500 text-sm">
            点击对话里可识别的本地路径或文件链接，在此预览（HTML / PDF / 图片 / Markdown / Excel / Word / Mermaid）。
          </p>
        )}
      </div>
    </aside>
  );
}
