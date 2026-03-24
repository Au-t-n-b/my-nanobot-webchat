"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, Cpu, ExternalLink, FileText, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import type { AgentMessage } from "@/hooks/useAgentChat";
import { extractIndexedFiles } from "@/lib/fileIndex";

type Props = {
  threadId: string;
  apiBase: string;
  onClear: () => void;
  onPreviewPath: (path: string) => void;
  messages: AgentMessage[];
};

type SkillItem = {
  name: string;
  skillDir: string;
  skillFile: string;
  mtimeMs: number;
};

type SkillsResp = { items: SkillItem[] };
type TrashModalState = { open: boolean; mode: "one" | "all"; targets: string[] };

function apiPath(path: string, apiBase: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    return `${apiBase.replace(/\/$/, "")}${path}`;
  }
  return path;
}

export function Sidebar({ threadId, apiBase, onClear, onPreviewPath, messages }: Props) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const [selectedSkillName, setSelectedSkillName] = useState<string | null>(null);
  const [removedPaths, setRemovedPaths] = useState<Set<string>>(new Set());
  const [trashError, setTrashError] = useState<string | null>(null);
  const [trashBusy, setTrashBusy] = useState(false);
  const [trashModal, setTrashModal] = useState<TrashModalState>({ open: false, mode: "one", targets: [] });
  const [previewPathInput, setPreviewPathInput] = useState("");

  const selected = useMemo(
    () => skills.find((s) => s.name === selectedSkillName) ?? null,
    [skills, selectedSkillName],
  );
  const indexedFiles = useMemo(() => {
    const all = extractIndexedFiles(messages);
    return all.filter((f) => !removedPaths.has(f.path));
  }, [messages, removedPaths]);

  const loadSkills = useCallback(async () => {
    setSkillsLoading(true);
    setSkillsError(null);
    try {
      const res = await fetch(apiPath("/api/skills", apiBase));
      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(txt || `HTTP ${res.status}`);
      }
      const j = (await res.json()) as SkillsResp;
      setSkills(j.items ?? []);
      if (selectedSkillName && !(j.items ?? []).some((x) => x.name === selectedSkillName)) {
        setSelectedSkillName(null);
      }
    } catch (e) {
      setSkillsError(e instanceof Error ? e.message : String(e));
    } finally {
      setSkillsLoading(false);
    }
  }, [apiBase, selectedSkillName]);

  useEffect(() => {
    void loadSkills();
  }, [loadSkills]);

  const openFolder = useCallback(async () => {
    if (!selected) return;
    try {
      const res = await fetch(apiPath("/api/open-folder", apiBase), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: selected.skillFile }),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(txt || `HTTP ${res.status}`);
      }
    } catch (e) {
      setSkillsError(e instanceof Error ? e.message : String(e));
    }
  }, [apiBase, selected]);

  const submitTrash = useCallback(async () => {
    if (!trashModal.targets.length) return;
    setTrashBusy(true);
    setTrashError(null);
    try {
      const res = await fetch(apiPath("/api/trash-files", apiBase), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: trashModal.targets }),
      });
      const txt = await res.text();
      let payload: {
        deleted?: string[];
        failed?: Array<{ path?: string; reason?: string }>;
        error?: { message?: string };
      } = {};
      try {
        payload = txt ? (JSON.parse(txt) as typeof payload) : {};
      } catch {
        payload = {};
      }
      if (!res.ok) {
        throw new Error(payload.error?.message || txt || `HTTP ${res.status}`);
      }
      const deleted = payload.deleted ?? [];
      const failed = payload.failed ?? [];
      setRemovedPaths((prev) => {
        const next = new Set(prev);
        for (const p of deleted) next.add(p);
        return next;
      });
      if (failed.length > 0) {
        setTrashError(`已删 ${deleted.length} 项，失败 ${failed.length} 项（失败项保留）。`);
      } else {
        setTrashModal({ open: false, mode: "one", targets: [] });
      }
    } catch (e) {
      setTrashError(e instanceof Error ? e.message : String(e));
    } finally {
      setTrashBusy(false);
    }
  }, [apiBase, trashModal.targets]);

  return (
    <aside className="h-full rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 flex flex-col gap-4">
      <div className="flex items-center gap-2 text-zinc-100 font-semibold">
        <Bot size={16} />
        <span>Nanobot AGUI</span>
      </div>

      <div className="text-xs text-zinc-500 space-y-2">
        <p>threadId</p>
        <p className="break-all text-zinc-300">{threadId || "…"}</p>
        <p className="pt-1">AGUI 后端（供 rewrites / 直连）</p>
        <p className="break-all text-zinc-400">{apiBase}</p>
      </div>

      <div className="space-y-2 text-xs">
        <div className="flex items-center gap-2 text-zinc-400">
          <Cpu size={14} /> 模型：当前后端配置
        </div>
        <div className="flex items-center gap-2 text-zinc-400">
          <Sparkles size={14} /> 流式 / HITL / 选择题
        </div>
        <div className="flex items-center gap-2 text-zinc-400">
          <FileText size={14} /> 文件：Markdown 链接 + 侧栏路径
        </div>
      </div>

      <section className="rounded-md border border-zinc-800 bg-zinc-950/40 p-2 flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between text-xs text-zinc-300">
          <span>Skills</span>
          <button
            type="button"
            onClick={() => void loadSkills()}
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 hover:bg-zinc-800 text-zinc-400"
            aria-label="刷新技能列表"
            title="刷新技能列表"
          >
            <RefreshCw size={12} className={skillsLoading ? "animate-spin" : ""} />
            刷新
          </button>
        </div>

        {skillsError && (
          <p className="text-[11px] text-red-300 break-all rounded bg-red-950/40 border border-red-900/50 px-2 py-1">
            {skillsError}
          </p>
        )}

        <div className="max-h-44 overflow-auto space-y-1 pr-1">
          {!skillsLoading && skills.length === 0 && (
            <p className="text-[11px] text-zinc-500">暂无技能（已自动创建 skills 目录）。</p>
          )}
          {skills.map((s) => (
            <button
              key={s.name}
              type="button"
              onClick={() => {
                setSelectedSkillName(s.name);
                onPreviewPath(s.skillFile);
              }}
              className={
                "w-full text-left text-xs rounded px-2 py-1.5 border " +
                (selectedSkillName === s.name
                  ? "border-sky-700 bg-sky-950/40 text-sky-200"
                  : "border-zinc-800 hover:border-zinc-700 text-zinc-300")
              }
              title={s.skillDir}
            >
              {s.name}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => void openFolder()}
          disabled={!selected}
          className="mt-1 rounded border border-zinc-700 px-2 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-40 inline-flex items-center justify-center gap-1"
          aria-label="打开技能文件夹"
          title="打开技能文件夹"
        >
          <ExternalLink size={12} />
          打开文件夹
        </button>
      </section>

      <section className="rounded-md border border-zinc-800 bg-zinc-950/40 p-2 flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between text-xs text-zinc-300">
          <span>文件索引</span>
          <button
            type="button"
            disabled={indexedFiles.length === 0}
            onClick={() => {
              setTrashError(null);
              setTrashModal({ open: true, mode: "all", targets: indexedFiles.map((f) => f.path) });
            }}
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 hover:bg-zinc-800 text-zinc-400 disabled:opacity-40"
            aria-label="清空文件索引并移入回收站"
          >
            <Trash2 size={12} />
            清空
          </button>
        </div>

        <div className="max-h-44 overflow-auto space-y-1 pr-1">
          {indexedFiles.length === 0 ? (
            <p className="text-[11px] text-zinc-500">暂无从会话中识别出的文件链接。</p>
          ) : (
            indexedFiles.map((f) => (
              <div key={f.path} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onPreviewPath(f.path)}
                  className="flex-1 text-left text-xs rounded px-2 py-1.5 border border-zinc-800 hover:border-zinc-700 text-zinc-300 truncate"
                  title={f.path}
                >
                  {f.fileName}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTrashError(null);
                    setTrashModal({ open: true, mode: "one", targets: [f.path] });
                  }}
                  className="rounded p-1.5 border border-zinc-800 hover:border-zinc-700 text-zinc-400"
                  aria-label={`删除 ${f.fileName}`}
                  title={`删除 ${f.fileName}`}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))
          )}
        </div>
      </section>

      {trashModal.open && (
        <div className="rounded-md border border-amber-800 bg-amber-950/40 p-2 text-xs text-amber-100 space-y-2">
          <p>
            {trashModal.mode === "all"
              ? `确认将 ${trashModal.targets.length} 个文件移入回收站？`
              : "确认将该文件移入回收站？"}
          </p>
          {trashError && <p className="text-red-300 break-all">{trashError}</p>}
          <div className="flex gap-2">
            <button
              type="button"
              disabled={trashBusy}
              onClick={() => void submitTrash()}
              className="rounded bg-amber-700/70 hover:bg-amber-700 px-2 py-1 disabled:opacity-50"
            >
              {trashBusy ? "处理中..." : "确认"}
            </button>
            <button
              type="button"
              disabled={trashBusy}
              onClick={() => setTrashModal({ open: false, mode: "one", targets: [] })}
              className="rounded bg-zinc-700/70 hover:bg-zinc-700 px-2 py-1"
            >
              取消
            </button>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3 space-y-2 text-xs">
        <div className="flex items-center gap-2 text-zinc-400 font-medium">
          <FileText size={14} />
          按路径预览
        </div>
        <p className="text-zinc-500 leading-relaxed">
          相对工作区的路径，或后端可解析的绝对路径（与 <code className="text-zinc-400">/api/file</code> 一致）。
        </p>
        <input
          className="w-full rounded-md bg-zinc-900 border border-zinc-700 px-2 py-1.5 text-zinc-200 outline-none focus:border-zinc-500"
          placeholder="例如 notes/readme.md"
          value={previewPathInput}
          onChange={(e) => setPreviewPathInput(e.target.value)}
        />
        <button
          type="button"
          onClick={() => {
            const t = previewPathInput.trim();
            if (t) onPreviewPath(t);
          }}
          className="w-full rounded-md bg-sky-800/60 hover:bg-sky-700/70 text-zinc-100 py-1.5 text-xs"
        >
          打开预览
        </button>
      </div>

      <button
        type="button"
        onClick={onClear}
        className="mt-auto rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-800"
      >
        清空当前对话
      </button>
    </aside>
  );
}
