"use client";

import { FileText, FileSpreadsheet, FileCode, Globe, Image as ImageIcon, FileJson } from "lucide-react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import type { SduiArtifactItem, SduiArtifactKind } from "@/lib/sdui";

type Props = {
  artifacts: SduiArtifactItem[];
  mode?: "input" | "output";
  title?: string;
};

type LegacyArtifactItem = Partial<SduiArtifactItem> & {
  name?: string;
  type?: string;
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

function coerceArtifactKind(item: LegacyArtifactItem): SduiArtifactKind {
  const rawKind = String(item.kind ?? item.type ?? "").trim().toLowerCase();
  if (rawKind === "document") return "md";
  if (rawKind === "image") return "png";
  if (
    rawKind === "docx" ||
    rawKind === "xlsx" ||
    rawKind === "pdf" ||
    rawKind === "html" ||
    rawKind === "json" ||
    rawKind === "md" ||
    rawKind === "png"
  ) {
    return rawKind;
  }

  const path = String(item.path ?? "").trim().toLowerCase();
  if (path.endsWith(".docx")) return "docx";
  if (path.endsWith(".xlsx")) return "xlsx";
  if (path.endsWith(".pdf")) return "pdf";
  if (path.endsWith(".html") || path.endsWith(".htm")) return "html";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".md")) return "md";
  if (path.endsWith(".png") || path.endsWith(".jpg") || path.endsWith(".jpeg") || path.endsWith(".webp")) {
    return "png";
  }
  return "other";
}

function normalizeArtifact(item: LegacyArtifactItem, index: number): SduiArtifactItem {
  const path = String(item.path ?? "").trim();
  const label =
    String(item.label ?? item.name ?? "").trim() ||
    path.split(/[\\/]/).pop() ||
    `artifact-${index + 1}`;
  const id =
    String(item.id ?? "").trim() ||
    path ||
    `${label}-${index + 1}`;

  return {
    id,
    label,
    path,
    kind: coerceArtifactKind(item),
    status: item.status,
  };
}

function canPreview(path: string): boolean {
  return path.startsWith("workspace/") || path.startsWith("workspace://") || path.startsWith("browser://");
}

export function SduiArtifactGrid({ artifacts, mode = "output", title }: Props) {
  const runtime = useSkillUiRuntime();

  if (!artifacts || artifacts.length === 0) return null;

  const normalizedArtifacts = artifacts.map((artifact, index) => normalizeArtifact(artifact, index));
  const heading = title?.trim() || (mode === "input" ? "已上传文件" : "模块产物");
  const isInput = mode === "input";

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] ui-text-muted">{heading}</p>
      <div className="flex flex-wrap gap-2">
        {normalizedArtifacts.map((a, index) => {
          const cfg = KIND_CONFIG[a.kind ?? "other"] ?? KIND_CONFIG.other;
          const Icon = cfg.icon;
          const isGenerating = a.status === "generating";
          const isError = a.status === "error";
          const key = `${a.id}:${a.path}:${a.status ?? "ready"}:${index}`;
          const chipClass = isInput
            ? "border-amber-400/30 bg-amber-400/10 hover:border-amber-300/45"
            : `${cfg.bg} ${cfg.border}`;
          const textClass = isInput ? "text-amber-100" : cfg.color;
          const iconClass = isInput ? "text-amber-300" : cfg.color;

          if (isGenerating) {
            return (
              <div
                key={key}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs border animate-pulse ${chipClass}`}
                style={{ minWidth: 100 }}
              >
                <Icon size={12} className={`${iconClass} opacity-50`} />
                <span className={`${textClass} opacity-50`}>{a.label}</span>
              </div>
            );
          }

          return (
            <button
              key={key}
              type="button"
              disabled={isError}
              onClick={() => {
                if (!canPreview(a.path)) return;
                runtime.openPreview(a.path);
              }}
              className={[
                "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs border transition-all",
                "hover:brightness-125 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed",
                chipClass,
              ].join(" ")}
            >
              <Icon size={12} className={iconClass} />
              <span className={textClass}>{a.label}</span>
              {isError && <span className="text-[var(--error)] ml-0.5">!</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
