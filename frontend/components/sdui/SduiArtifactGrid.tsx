"use client";

import { FileText, FileSpreadsheet, FileCode, Globe, Image as ImageIcon, FileJson } from "lucide-react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import type { SduiArtifactItem, SduiArtifactKind } from "@/lib/sdui";

type Props = {
  artifacts: SduiArtifactItem[];
};

type KindConfig = {
  icon: React.FC<{ size?: number; className?: string }>;
  color: string;
  bg: string;
  border: string;
};

const KIND_CONFIG: Record<SduiArtifactKind, KindConfig> = {
  docx:  { icon: FileText,        color: "text-blue-400",   bg: "bg-blue-400/10",   border: "border-blue-400/25" },
  xlsx:  { icon: FileSpreadsheet, color: "text-green-400",  bg: "bg-green-400/10",  border: "border-green-400/25" },
  pdf:   { icon: FileText,        color: "text-red-400",    bg: "bg-red-400/10",    border: "border-red-400/25" },
  html:  { icon: Globe,           color: "text-purple-400", bg: "bg-purple-400/10", border: "border-purple-400/25" },
  json:  { icon: FileJson,        color: "text-orange-400", bg: "bg-orange-400/10", border: "border-orange-400/25" },
  md:    { icon: FileCode,        color: "text-sky-400",    bg: "bg-sky-400/10",    border: "border-sky-400/25" },
  png:   { icon: ImageIcon,       color: "text-pink-400",   bg: "bg-pink-400/10",   border: "border-pink-400/25" },
  other: { icon: FileText,        color: "text-zinc-400",   bg: "bg-zinc-400/10",   border: "border-zinc-400/25" },
};

export function SduiArtifactGrid({ artifacts }: Props) {
  const runtime = useSkillUiRuntime();

  if (!artifacts || artifacts.length === 0) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] ui-text-muted">模块产物</p>
      <div className="flex flex-wrap gap-2">
        {artifacts.map((a) => {
          const cfg = KIND_CONFIG[a.kind] ?? KIND_CONFIG.other;
          const Icon = cfg.icon;
          const isGenerating = a.status === "generating";
          const isError = a.status === "error";

          if (isGenerating) {
            return (
              <div
                key={a.id}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs border animate-pulse ${cfg.bg} ${cfg.border}`}
                style={{ minWidth: 100 }}
              >
                <Icon size={12} className={`${cfg.color} opacity-50`} />
                <span className={`${cfg.color} opacity-50`}>{a.label}</span>
              </div>
            );
          }

          return (
            <button
              key={a.id}
              type="button"
              disabled={isError}
              onClick={() => {
                if (!a.path.startsWith("workspace://") && !a.path.startsWith("browser://")) return;
                runtime.openPreview(a.path);
              }}
              className={[
                "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs border transition-all",
                "hover:brightness-125 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed",
                cfg.bg, cfg.border,
              ].join(" ")}
            >
              <Icon size={12} className={cfg.color} />
              <span className={cfg.color}>{a.label}</span>
              {isError && <span className="text-[var(--error)] ml-0.5">!</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
