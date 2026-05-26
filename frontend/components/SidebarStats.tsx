"use client";

import { Building2, FileText, MessageSquare, Zap } from "lucide-react";
import type { ComponentType, SVGProps } from "react";

type SidebarStatsProps = {
  sessionCount: number;
  artifactCount: number;
  skillCount: number;
  orgAssetCount: number;
};

type StatCard = {
  icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  count: number;
  label: string;
  color: string;
};

export function SidebarStats({ sessionCount, artifactCount, skillCount, orgAssetCount }: SidebarStatsProps) {
  const cards: StatCard[] = [
    { icon: MessageSquare, count: sessionCount, label: "会话", color: "#60a5fa" },
    { icon: FileText, count: artifactCount, label: "产物", color: "#34d399" },
    { icon: Zap, count: skillCount, label: "技能", color: "#fbbf24" },
    { icon: Building2, count: orgAssetCount, label: "资产", color: "#a78bfa" },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 shrink-0 mt-3 mb-1">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.label}
            className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 ui-motion-fast"
            style={{
              background: "var(--surface-1)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <Icon size={16} style={{ color: card.color, flexShrink: 0 }} />
            <div className="min-w-0">
              <div className="ui-text-title font-bold tabular-nums leading-tight" style={{ color: "var(--text-primary)" }}>
                {card.count}
              </div>
              <div className="ui-text-eyebrow ui-text-muted leading-tight">{card.label}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
