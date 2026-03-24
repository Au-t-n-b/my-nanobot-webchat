"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, Cpu, ExternalLink, FileText, RefreshCw, Sparkles } from "lucide-react";

type Props = {
  threadId: string;
  apiBase: string;
  onClear: () => void;
  onPreviewPath: (path: string) => void;
};

type SkillItem = {
  name: string;
  skillDir: string;
  skillFile: string;
  mtimeMs: number;
};

type SkillsResp = { items: SkillItem[] };

function apiPath(path: string, apiBase: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    return `${apiBase.replace(/\/$/, "")}${path}`;
  }
  return path;
}

export function Sidebar({ threadId, apiBase, onClear, onPreviewPath }: Props) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const [selectedSkillName, setSelectedSkillName] = useState<string | null>(null);

  const selected = useMemo(
    () => skills.find((s) => s.name === selectedSkillName) ?? null,
    [skills, selectedSkillName],
  );

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

  return (
    <aside className="h-full rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 flex flex-col gap-4">
      <div className="flex items-center gap-2 text-zinc-100 font-semibold">
        <Bot size={16} />
        <span>Nanobot AGUI</span>
      </div>

      <div className="text-xs text-zinc-500 space-y-2">
        <p>threadId</p>
        <p className="break-all text-zinc-300">{threadId || "..."}</p>
        <p className="pt-1">API</p>
        <p className="break-all text-zinc-400">{apiBase}</p>
      </div>

      <div className="space-y-2 text-xs">
        <div className="flex items-center gap-2 text-zinc-400"><Cpu size={14} /> 模型：当前后端配置</div>
        <div className="flex items-center gap-2 text-zinc-400"><Sparkles size={14} /> 技能：Phase 3 联动中</div>
        <div className="flex items-center gap-2 text-zinc-400"><FileText size={14} /> 文件索引：Task6 预览接入</div>
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
                onPreviewPath(s.skillFile); // only SKILL.md
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
