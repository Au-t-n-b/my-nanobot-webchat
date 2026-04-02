"use client";

import { useEffect, useState } from "react";
import { LayoutGrid } from "lucide-react";
import { buildProxiedFileUrl } from "@/lib/apiFile";
import {
  parseSkillUiPath,
  SKILL_UI_REGISTRY,
  type SkillUiComponentProps,
} from "@/lib/skillUiRegistry";

type Props = {
  syntheticPath: string;
};

function UnknownSkillUiPanel({ component }: { component: string }) {
  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-3 items-start"
      style={{
        border: "1px solid rgba(245,158,11,0.35)",
        background: "rgba(245,158,11,0.06)",
      }}
    >
      <div className="flex items-center gap-2 text-amber-200/90">
        <LayoutGrid size={20} />
        <span className="text-sm font-semibold">未知 Skill UI 组件</span>
      </div>
      <p className="text-xs ui-text-secondary leading-relaxed">
        名称 <code className="px-1 rounded bg-[var(--surface-3)] ui-text-primary">{component}</code>{" "}
        未在 <code className="px-1 rounded bg-[var(--surface-3)]">SKILL_UI_REGISTRY</code> 中注册。
      </p>
      <p className="text-[11px] ui-text-muted">
        请在 <code className="ui-text-secondary">frontend/lib/skillUiRegistry.ts</code> 中注册对应 React 组件后刷新。
      </p>
    </div>
  );
}

/**
 * 解析 skill-ui:// 路径，按注册表挂载组件，并通过 GET /api/file 拉取 dataFile JSON。
 */
export function SkillUiWrapper({ syntheticPath }: Props) {
  const parsed = parseSkillUiPath(syntheticPath);
  const [data, setData] = useState<unknown>(undefined);
  const [loading, setLoading] = useState(() => Boolean(parseSkillUiPath(syntheticPath)?.dataFile));
  const [error, setError] = useState<string | null>(null);

  const componentName = parsed?.component ?? "";
  const dataFile = parsed?.dataFile ?? null;
  const Inner = componentName ? SKILL_UI_REGISTRY[componentName] : undefined;

  useEffect(() => {
    if (!parsed || !dataFile) {
      setData(undefined);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(undefined);

    const url = buildProxiedFileUrl(dataFile);
    void (async () => {
      try {
        const res = await fetch(url);
        const text = await res.text();
        if (cancelled) return;
        if (!res.ok) {
          throw new Error(text || `HTTP ${res.status}`);
        }
        let json: unknown;
        try {
          json = text.trim() === "" ? undefined : JSON.parse(text);
        } catch {
          throw new Error("dataFile 不是合法 JSON");
        }
        if (!cancelled) setData(json);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [parsed, dataFile]);

  if (!parsed) {
    return (
      <div className="rounded-xl p-4 text-sm" style={{ color: "var(--danger)" }}>
        无法解析 Skill UI 路径，请使用{" "}
        <code className="ui-text-secondary">skill-ui://组件名?dataFile=路径</code> 格式。
      </div>
    );
  }

  if (!Inner) {
    return <UnknownSkillUiPanel component={componentName} />;
  }

  const injected: SkillUiComponentProps = {
    data,
    loading,
    error,
    dataFilePath: dataFile,
  };

  return <Inner {...injected} />;
}
