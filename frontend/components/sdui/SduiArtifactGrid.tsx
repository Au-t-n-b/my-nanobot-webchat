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
  docx:  { icon: FileText,        color: "text-[var(--accent)]",  bg: "bg-[var(--accent-bg-soft)]", border: "border-[var(--accent-border)]" },
  xlsx:  { icon: FileSpreadsheet, color: "text-[var(--success)]", bg: "bg-[var(--success-bg)]",     border: "border-[var(--success-border)]" },
  pdf:   { icon: FileText,        color: "text-[var(--danger)]",  bg: "bg-[var(--danger-bg)]",      border: "border-[var(--danger-border)]" },
  html:  { icon: Globe,           color: "text-[var(--accent)]",  bg: "bg-[var(--accent-bg-soft)]", border: "border-[var(--accent-border)]" },
  json:  { icon: FileJson,        color: "text-[var(--warning)]", bg: "bg-[var(--warning-bg)]",     border: "border-[var(--warning-border)]" },
  md:    { icon: FileCode,        color: "text-[var(--accent)]",  bg: "bg-[var(--accent-bg-soft)]", border: "border-[var(--accent-border)]" },
  png:   { icon: ImageIcon,       color: "text-[var(--warning)]", bg: "bg-[var(--warning-bg)]",     border: "border-[var(--warning-border)]" },
  other: { icon: FileText,        color: "ui-text-secondary",   bg: "bg-[var(--surface-2)]/40",   border: "border-[var(--border-subtle)]" },
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
      <p className="ui-text-eyebrow ui-text-muted">{heading}</p>
      <div className="flex flex-wrap gap-2">
        {normalizedArtifacts.map((a, index) => {
          const cfg = KIND_CONFIG[a.kind ?? "other"] ?? KIND_CONFIG.other;
          const Icon = cfg.icon;
          const isGenerating = a.status === "generating";
          const isError = a.status === "error";
          const key = a.id?.trim() ? `${a.id.trim()}:${index}` : `${a.path}:${index}`;
          const chipClass = isInput
            ? "border-[var(--warning-border)] bg-[var(--warning-bg)] hover:brightness-110"
            : `${cfg.bg} ${cfg.border}`;
          const textClass = isInput ? "text-[var(--text-primary)]" : cfg.color;
          const iconClass = isInput ? "text-[var(--warning)]" : cfg.color;

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
                const p = a.path?.trim();
                if (!p || !canPreview(p)) return;
                runtime.openPreview(p);
              }}
              className={[
                "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs border transition-all",
                "hover:brightness-125 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed",
                chipClass,
              ].join(" ")}
            >
              <Icon size={12} className={iconClass} />
              <span className={textClass}>{a.label}</span>
              {isError && <span className="ui-status-danger ml-0.5">!</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
