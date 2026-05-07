"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

const CLAW_PLATFORM = "claw-platform";
const CLAW_IFRAME = "claw-iframe";
const CLAW_UPDATE = "CLAW_UPDATE_STATE";
const CLAW_EVENT = "CLAW_EVENT";
const SKILL_WEB_INTENT = "skill_web_intent";

type Props = {
  src: string;
  /** 与 SDUI 节点 id、postMessage embedId 一致 */
  id: string;
  /** 下发给 iframe 的状态（任意可结构化 JSON） */
  state: unknown;
  /** 除 iframe 自身 origin 外，额外允许的 message 来源（通常为空，仅用 iframe origin） */
  allowedOrigins?: string[];
  className?: string;
  /** 可视区域最小高度，如 320 或 "40vh" */
  minHeight?: number | string;
  /** 为 false 时不设置 sandbox，便于内网业务页或部分视频站嵌入 */
  embedSandbox?: boolean;
};

function stableStringify(value: unknown): string {
  const seen = new WeakSet<object>();
  const walk = (v: unknown): unknown => {
    if (v === null || typeof v !== "object") return v;
    if (seen.has(v as object)) return "[Circular]";
    if (Array.isArray(v)) return (v as unknown[]).map(walk);
    seen.add(v as object);
    const o = v as Record<string, unknown>;
    const keys = Object.keys(o).sort();
    const out: Record<string, unknown> = {};
    for (const k of keys) {
      out[k] = walk(o[k]);
    }
    return out;
  };
  try {
    return JSON.stringify(walk(value));
  } catch {
    return String(value);
  }
}

/**
 * 仪表盘内嵌外部网页（iframe），与 claw-bridge.js 通过 postMessage 双向通信。
 * 上行事件写入 syncState，避免与下行同 key 环路：使用专用 key，且下行用 ref 去重。
 */
export function EmbeddedWeb({
  src,
  id,
  state,
  allowedOrigins,
  className,
  minHeight,
  embedSandbox = true,
}: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [loaded, setLoaded] = useState(false);
  const lastSentJsonRef = useRef<string | null>(null);
  const runtime = useSkillUiRuntime();
  const syncState = runtime.syncState;
  const postToAgentRef = useRef(runtime.postToAgent);
  postToAgentRef.current = runtime.postToAgent;

  const targetOrigin = useMemo(() => {
    try {
      return new URL(src, typeof window !== "undefined" ? window.location.href : "http://localhost").origin;
    } catch {
      return "*";
    }
  }, [src]);

  const originAllowList = useMemo(() => {
    const extra = Array.isArray(allowedOrigins) ? allowedOrigins.filter((x) => typeof x === "string" && x.trim()) : [];
    const set = new Set(extra);
    if (targetOrigin && targetOrigin !== "*") set.add(targetOrigin);
    return set;
  }, [allowedOrigins, targetOrigin]);

  const embedId = id.trim() || "embedded-web";

  // 下行：state 变化且 iframe 已加载 → postMessage（与同内容去重）
  useEffect(() => {
    if (!loaded) return;
    const win = iframeRef.current?.contentWindow;
    if (!win) return;

    const json = stableStringify(state);
    if (lastSentJsonRef.current === json) return;
    lastSentJsonRef.current = json;

    const msg = {
      source: CLAW_PLATFORM,
      type: CLAW_UPDATE,
      embedId,
      payload: state,
    };
    try {
      win.postMessage(msg, targetOrigin === "*" ? "*" : targetOrigin);
    } catch {
      win.postMessage(msg, "*");
    }
  }, [state, loaded, embedId, targetOrigin]);

  // 加载完成后补发一次当前 state（避免首帧错过）
  const onLoad = useCallback(() => {
    setLoaded(true);
    lastSentJsonRef.current = null;
  }, []);

  // 上行：message 监听，cleanup 移除；handler 用 ref 保持最新 syncState/embedId，避免 Strict Mode 双绑
  const syncStateRef = useRef(syncState);
  syncStateRef.current = syncState;
  const embedIdRef = useRef(embedId);
  embedIdRef.current = embedId;

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data || typeof data !== "object") return;
      const d = data as Record<string, unknown>;

      // Skill-First: generic "web intent" bridge.
      // iframe can send: { type: "skill_web_intent", text: "<string>" } and the host will
      // forward the text to /api/chat through the injected postToAgent.
      if (d.type === SKILL_WEB_INTENT) {
        const text = typeof d.text === "string" ? d.text.trim() : "";
        if (!text) return;
        if (originAllowList.size > 0 && !originAllowList.has(event.origin)) return;
        // Best-effort: avoid megabyte payloads freezing the UI.
        if (text.length > 1_800_000) return;
        postToAgentRef.current?.(text);
        return;
      }

      if (d.source !== CLAW_IFRAME || d.type !== CLAW_EVENT) return;

      if (originAllowList.size > 0 && !originAllowList.has(event.origin)) return;

      const mid = typeof d.embedId === "string" ? d.embedId.trim() : "";
      if (mid && mid !== embedIdRef.current) return;

      const eventName = typeof d.eventName === "string" ? d.eventName : "";
      if (!eventName) return;

      syncStateRef.current({
        key: `claw.embedded.${embedIdRef.current}.lastEvent`,
        value: {
          eventName,
          payload: d.payload ?? null,
          origin: event.origin,
          at: Date.now(),
        },
        behavior: "immediate",
      });
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [originAllowList]);

  const minH =
    typeof minHeight === "number"
      ? `${minHeight}px`
      : typeof minHeight === "string" && minHeight.trim()
        ? minHeight.trim()
        : "min(420px, 55vh)";

  return (
    <div
      className={["relative w-full overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-0)]", className ?? ""].join(" ")}
      style={{ minHeight: minH }}
    >
      {!loaded ? (
        <div
          className="absolute inset-0 z-[1] flex flex-col gap-3 p-4 animate-pulse"
          aria-busy="true"
          aria-label="加载嵌入页面"
        >
          <div className="h-4 w-1/3 max-w-xs rounded-md bg-[var(--surface-3)]/40 dark:bg-white/10" />
          <div className="flex-1 min-h-[200px] rounded-lg bg-[var(--surface-2)]/30 dark:bg-white/[0.06]" />
          <div className="h-3 w-2/3 rounded-md bg-[var(--surface-3)]/30 dark:bg-white/[0.07]" />
        </div>
      ) : null}
      <iframe
        ref={iframeRef}
        title={embedId}
        src={src}
        className="h-full w-full min-h-[200px] rounded-xl bg-[var(--surface-0)]"
        // ``colorScheme`` 必须显式设给 iframe：iframe 是独立 document，不会自动继承父级
        // ``[data-theme="dark"]`` 上声明的 ``color-scheme: dark``；当 iframe 内部 ``html/body``
        // 是 transparent（如 job_workbench.html / gantt_editor.html）时，浏览器会用 user agent
        // 默认 light 底色填充，从而出现「右侧大块白屏」。声明 ``dark light`` 后浏览器优先使用 dark
        // 调色板，与父级 ``--surface-0`` 一致。
        style={{ minHeight: minH, colorScheme: "dark light", backgroundColor: "var(--surface-0)" }}
        onLoad={onLoad}
        {...(embedSandbox
          ? { sandbox: "allow-scripts allow-same-origin allow-forms allow-popups allow-presentation" as const }
          : {})}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
        allowFullScreen
        referrerPolicy="no-referrer-when-downgrade"
      />
    </div>
  );
}
