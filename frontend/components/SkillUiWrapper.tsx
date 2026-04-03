"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LayoutGrid } from "lucide-react";
import { buildProxiedFileUrl } from "@/lib/apiFile";
import {
  parseSkillUiPath,
  SKILL_UI_REGISTRY,
  type SkillUiComponentProps,
} from "@/lib/skillUiRegistry";
import { SkillUiRuntimeProvider } from "@/components/sdui/SkillUiRuntimeProvider";

const SDUI_SHELL = "SduiView";

type Props = {
  syntheticPath: string;
  /** 封装自 sendMessage，用于 Button / DataGrid 等回传 Intent */
  postToAgent?: (text: string) => void;
  /** Agent 是否在运行（用于下降沿强刷 dataFile） */
  isAgentRunning?: boolean;
  /** open_preview 动作打开预览 */
  onOpenPreview?: (path: string) => void;
};

function UnknownSkillUiPanel({ component, hint }: { component: string; hint?: string }) {
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
        <span className="text-sm font-semibold">未知或未支持的 Skill UI 外壳</span>
      </div>
      <p className="text-xs ui-text-secondary leading-relaxed">
        名称 <code className="px-1 rounded bg-[var(--surface-3)] ui-text-primary">{component}</code>{" "}
        未在 <code className="px-1 rounded bg-[var(--surface-3)]">SKILL_UI_REGISTRY</code> 中注册，或不是 SDUI 顶层外壳。
      </p>
      {hint ? (
        <p className="text-[11px] ui-text-muted leading-relaxed">{hint}</p>
      ) : (
        <p className="text-[11px] ui-text-muted">
          SDUI 请使用{" "}
          <code className="ui-text-secondary">skill-ui://SduiView?dataFile=&lt;workspace 相对路径&gt;</code>，内容由 JSON 内{" "}
          <code className="ui-text-secondary">root</code> 递归渲染。
        </p>
      )}
    </div>
  );
}

/**
 * 解析 skill-ui://，仅挂载注册表中的顶层外壳（当前 SDUI 固定为 SduiView），
 * 通过 GET /api/file 拉取 dataFile JSON，并由 SduiView 按文档递归渲染。
 */
export function SkillUiWrapper({
  syntheticPath,
  postToAgent: postToAgentProp,
  isAgentRunning = false,
  onOpenPreview,
}: Props) {
  const parsed = parseSkillUiPath(syntheticPath);
  const [data, setData] = useState<unknown>(undefined);
  const [loading, setLoading] = useState(() => Boolean(parseSkillUiPath(syntheticPath)?.dataFile));
  const [error, setError] = useState<string | null>(null);

  const componentName = parsed?.component?.trim() ?? "";
  const dataFile = parsed?.dataFile ?? null;

  const postToAgentRaw = useCallback(
    (text: string) => {
      if (postToAgentProp) {
        postToAgentProp(text);
      } else {
        console.warn("[SkillUiWrapper] postToAgent 未注入，忽略回传:", text.slice(0, 200));
      }
    },
    [postToAgentProp],
  );

  const loadData = useCallback(
    async () => {
      const p = parseSkillUiPath(syntheticPath);
      if (!p?.dataFile) {
        setData(undefined);
        setLoading(false);
        setError(null);
        return;
      }

      setLoading(true);
      setError(null);
      setData(undefined);

      const url = `${buildProxiedFileUrl(p.dataFile)}&t=${Date.now()}`;
      try {
        const res = await fetch(url, { cache: "no-store" });
        const text = await res.text();
        if (!res.ok) {
          throw new Error(text || `HTTP ${res.status}`);
        }
        let json: unknown;
        try {
          json = text.trim() === "" ? undefined : JSON.parse(text);
        } catch {
          throw new Error("dataFile 不是合法 JSON");
        }
        setData(json);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [syntheticPath],
  );

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const prevRunningRef = useRef<boolean | undefined>(undefined);
  useEffect(() => {
    const prev = prevRunningRef.current;
    if (prev === true && isAgentRunning === false) {
      void loadData();
    }
    prevRunningRef.current = isAgentRunning;
  }, [isAgentRunning, loadData]);

  if (!parsed) {
    return (
      <div className="rounded-xl p-4 text-sm" style={{ color: "var(--danger)" }}>
        无法解析 Skill UI 路径，请使用{" "}
        <code className="ui-text-secondary">skill-ui://SduiView?dataFile=路径</code> 格式。
      </div>
    );
  }

  if (componentName !== SDUI_SHELL) {
    return (
      <UnknownSkillUiPanel
        component={componentName || "(空)"}
        hint={`请改为 skill-ui://${SDUI_SHELL}?dataFile=...；内部 UI 由 JSON 的 root 定义，无需改 URL 中的组件名。`}
      />
    );
  }

  const Inner = SKILL_UI_REGISTRY[SDUI_SHELL];
  if (!Inner) {
    return <UnknownSkillUiPanel component={SDUI_SHELL} />;
  }

  const injected: SkillUiComponentProps = {
    data,
    loading,
    error,
    dataFilePath: dataFile,
  };

  return (
    <SkillUiRuntimeProvider postToAgentRaw={postToAgentRaw} onOpenPreview={onOpenPreview}>
      <div className="animate-in fade-in slide-in-from-bottom-3 duration-500 fill-mode-both ease-out">
        <Inner {...injected} />
      </div>
    </SkillUiRuntimeProvider>
  );
}
