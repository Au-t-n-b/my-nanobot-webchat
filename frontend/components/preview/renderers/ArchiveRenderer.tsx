"use client";

import type JSZip from "jszip";
import { useMemo, useRef, useState } from "react";
import type { ZipArchivePayload, ZipTreeNode } from "../previewParsers";
import type { BaseRendererProps } from "../previewTypes";
import { PreviewFileViewer } from "../PreviewFileViewer";

const MAX_ENTRY_BYTES = 10 * 1024 * 1024; // 10MB

function isDir(node: ZipTreeNode): node is Extract<ZipTreeNode, { type: "dir" }> {
  return node.type === "dir";
}

function nodeKey(node: ZipTreeNode): string {
  return `${node.type}:${node.path}`;
}

function flattenForSearch(root: ZipTreeNode, out: ZipTreeNode[] = []): ZipTreeNode[] {
  out.push(root);
  if (root.type === "dir") root.children.forEach((c) => flattenForSearch(c, out));
  return out;
}

function FileTreeNodeView({
  node,
  openPaths,
  toggleDir,
  onSelectFile,
  depth = 0,
}: {
  node: ZipTreeNode;
  openPaths: Set<string>;
  toggleDir: (path: string) => void;
  onSelectFile: (path: string) => void;
  depth?: number;
}) {
  const indent = Math.min(depth, 10) * 12;

  if (node.type === "dir") {
    const open = openPaths.has(node.path);
    return (
      <div>
        <button
          type="button"
          className="w-full text-left text-xs ui-text-secondary hover:bg-[var(--surface-2)] rounded-md px-2 py-1"
          style={{ paddingLeft: 8 + indent }}
          onClick={() => toggleDir(node.path)}
          title={node.path}
        >
          <span className="inline-flex items-center gap-1">
            <span className="ui-text-muted">{open ? "▾" : "▸"}</span>
            <span className="font-medium">{node.name || "（根目录）"}</span>
          </span>
        </button>
        {open ? (
          <div className="mt-0.5">
            {node.children.map((c) => (
              <FileTreeNodeView
                key={nodeKey(c)}
                node={c}
                openPaths={openPaths}
                toggleDir={toggleDir}
                onSelectFile={onSelectFile}
                depth={depth + 1}
              />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <button
      type="button"
      className="w-full text-left text-xs ui-text-secondary hover:bg-[var(--surface-2)] rounded-md px-2 py-1"
      style={{ paddingLeft: 8 + indent }}
      onClick={() => onSelectFile(node.path)}
      title={node.path}
    >
      {node.name}
    </button>
  );
}

async function inflateSingleFile(zip: JSZip, path: string): Promise<ArrayBuffer> {
  const file = zip.file(path);
  if (!file) throw new Error("file not found in zip");
  const buf = await file.async("arraybuffer");
  if (buf.byteLength > MAX_ENTRY_BYTES) {
    throw new Error(`entry too large (> ${(MAX_ENTRY_BYTES / (1024 * 1024)).toFixed(0)}MB)`);
  }
  return buf;
}

export function ArchiveRenderer(
  props: BaseRendererProps & {
    payload: ZipArchivePayload;
    onOpenPath: (path: string) => void;
    activeSkillName?: string | null;
    onFillInput?: (text: string) => void;
  }
) {
  const root = props.payload.tree;
  const zip = props.payload.zip;

  const [openPaths, setOpenPaths] = useState<Set<string>>(() => new Set([root.path]));
  const [activePath, setActivePath] = useState<string | null>(null);
  const [activeBuffer, setActiveBuffer] = useState<ArrayBuffer | null>(null);
  const [loadingPath, setLoadingPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  // 防竞态：每次点击生成递增 token；await 返回时必须匹配当前 token 才能落 state
  const loadSeq = useRef(0);

  const toggleDir = (path: string) => {
    setOpenPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const searchable = useMemo(() => flattenForSearch(root).filter((n) => n.type === "file"), [root]);
  const filteredFiles = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return searchable.filter((n) => n.path.toLowerCase().includes(q)).slice(0, 200);
  }, [query, searchable]);

  const selectFile = async (path: string) => {
    setError(null);
    setActivePath(path);
    setActiveBuffer(null);
    setLoadingPath(path);

    const seq = ++loadSeq.current;
    try {
      const buf = await inflateSingleFile(zip, path);
      // 竞态防御：只有“最后一次选择”的结果允许落地
      if (seq !== loadSeq.current) return;
      setActiveBuffer(buf);
    } catch (e) {
      if (seq !== loadSeq.current) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (seq === loadSeq.current) setLoadingPath(null);
    }
  };

  const backToTree = () => {
    // GC 防御：彻底丢弃 ArrayBuffer 引用
    setActiveBuffer(null);
    setActivePath(null);
    setLoadingPath(null);
    setError(null);
    loadSeq.current++;
  };

  if (activePath && activeBuffer) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <button
            type="button"
            className="ui-btn-accent rounded-md px-3 py-1.5 text-xs"
            onClick={backToTree}
          >
            ← 返回目录
          </button>
          <span className="text-xs ui-text-muted truncate max-w-[70%]" title={activePath}>
            {activePath}
          </span>
        </div>

        <div className="rounded-xl border border-[var(--border-subtle)] p-3 bg-[var(--surface-1)]">
          <PreviewFileViewer
            path={activePath}
            initialBuffer={activeBuffer}
            onOpenPath={props.onOpenPath}
            activeSkillName={props.activeSkillName}
            onFillInput={props.onFillInput}
          />
          <p className="mt-3 text-xs ui-text-muted">
            若文本出现乱码（如 GBK/ANSI），请下载原文件查看。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {props.payload.warning ? (
        <div
          className="rounded-xl border p-3 text-sm"
          style={{ borderColor: "rgba(245,158,11,0.30)", background: "rgba(245,158,11,0.08)", color: "rgb(245,158,11)" }}
        >
          {props.payload.warning}
        </div>
      ) : null}

      <div className="flex items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索 ZIP 内文件（按路径）…"
          className="w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1 text-xs ui-text-secondary focus:outline-none focus:ring-0 focus:border-[var(--accent)]"
        />
        {loadingPath ? (
          <span className="text-xs ui-text-muted shrink-0" title={loadingPath}>
            解压中…
          </span>
        ) : null}
      </div>

      {error ? (
        <div
          className="rounded-xl text-sm p-3 whitespace-pre-wrap"
          style={{ border: "1px solid rgba(239,107,115,0.24)", background: "rgba(239,107,115,0.08)", color: "var(--danger)" }}
        >
          {error}
        </div>
      ) : null}

      {filteredFiles ? (
        <div className="rounded-xl border border-[var(--border-subtle)] p-2">
          <p className="text-xs ui-text-muted px-2 py-1">搜索结果（最多 200 条）</p>
          <div className="max-h-[320px] overflow-auto">
            {filteredFiles.map((n) => (
              <button
                key={nodeKey(n)}
                type="button"
                className="w-full text-left text-xs ui-text-secondary hover:bg-[var(--surface-2)] rounded-md px-2 py-1"
                onClick={() => selectFile(n.path)}
                title={n.path}
              >
                {n.path}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="rounded-xl border border-[var(--border-subtle)] p-2 max-h-[520px] overflow-auto">
        <FileTreeNodeView node={root} openPaths={openPaths} toggleDir={toggleDir} onSelectFile={selectFile} depth={0} />
      </div>
    </div>
  );
}

