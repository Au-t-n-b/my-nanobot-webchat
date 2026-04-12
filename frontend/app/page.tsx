"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileText, Menu, PanelRightClose, PanelRightOpen, Plus, Settings, Sidebar as SidebarIcon, X, Zap } from "lucide-react";
import { ChatArea } from "@/components/ChatArea";
import { ErrorToast } from "@/components/ErrorToast";
import { PreviewPanel } from "@/components/PreviewPanel";
import { RemoteAssetDetailPanel } from "@/components/RemoteAssetDetailPanel";
import { RemoteAssetUploadPanel } from "@/components/RemoteAssetUploadPanel";
import { SearchOverlay } from "@/components/SearchOverlay";
import { SystemShellModal } from "@/components/SystemShellModal";
import { Sidebar } from "@/components/Sidebar";
import { ModelSelector } from "@/components/ModelSelector";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useAgentChat, type ChoiceItem } from "@/hooks/useAgentChat";
import { DashboardNavigator } from "@/components/DashboardNavigator";
import { ControlCenterPanel } from "@/components/ControlCenterPanel";
import {
  hydrateProjectOverview,
  resetProjectOverviewSessionState,
} from "@/lib/projectOverviewStore";
import { previewKindFromPath } from "@/lib/previewKind";
import {
  isBaseLayerDashboardSkillUi,
  isBlockingActionSkillUi,
  normalizeSyntheticSkillUiPath,
} from "@/lib/skillUiRegistry";

const RIGHT_PANEL_MAX = typeof window !== "undefined"
  ? Math.floor(window.innerWidth * 0.62)
  : 900;

const CHAT_COLUMN_MIN_PX = 180;
/** 导航 + 大盘最小宽 + 分隔条 + 预览条近似总宽；会话列最大 = 视口 − 该预留 */
const CHAT_COLUMN_LAYOUT_RESERVE_PX = 480;

function getChatColumnMaxPx(): number {
  if (typeof window === "undefined") return 960;
  return Math.max(CHAT_COLUMN_MIN_PX + 80, window.innerWidth - CHAT_COLUMN_LAYOUT_RESERVE_PX);
}

type SystemModal = null | "controlCenter" | "remoteAssetDetail" | "remoteUpload";
type ControlCenterTab = "config" | "settings";

function previewTabLabel(path: string): string {
  if (path.startsWith("browser://")) return "浏览器";
  const base = path.split(/[/\\]/).pop() ?? path;
  return base.length > 36 ? `${base.slice(0, 34)}…` : base;
}

const headerIconButtonClass =
  "inline-flex h-9 w-9 items-center justify-center rounded-xl border transition-colors " +
  "border-[var(--border-subtle)] bg-[var(--surface-1)] ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary";

export default function Home() {
  const {
    threadId,
    sessions,
    messages,
    stepLogs,
    isLoading,
    error,
    pendingTool,
    pendingChoices,
    runStatus,
    statusMessage,
    effectiveModel,
    skillUiPatchEvent,
    skillUiBootstrapEvent,
    activeModuleIds,
    sendMessage,
    sendSilentMessage,
    stopGenerating,
    approveTool,
    clearPendingChoices,
    clearChat,
    deleteMessage,
    deleteSession,
    createSession,
    switchSession,
  } = useAgentChat();
  const [inputPrefill, setInputPrefill] = useState("");
  /** 右栏业务视窗：预览类 Tab + 强阻断 Action SDUI */
  const [blockingActionPath, setBlockingActionPath] = useState<string | null>(null);
  const [previewTabs, setPreviewTabs] = useState<Array<{ id: string; path: string; label: string }>>([]);
  /** 右栏当前激活 Tab：__blocking__ / 具体 previewTab.id(path) */
  const [activeRightTabId, setActiveRightTabId] = useState<string | null>(null);
  const [systemModal, setSystemModal] = useState<SystemModal>(null);
  const [controlCenterTab, setControlCenterTab] = useState<ControlCenterTab>("config");
  const [activeSkillName, setActiveSkillName] = useState<string | null>(null);
  const [selectedOrgAssetId, setSelectedOrgAssetId] = useState<string | null>(null);
  const [sidebarRefreshNonce, setSidebarRefreshNonce] = useState(0);
  const [inputFocusSignal, setInputFocusSignal] = useState(0);
  const [toastDismissed, setToastDismissed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [navExpanded, setNavExpanded] = useState(false);
  const [chatWidth, setChatWidth] = useState(240);
  const [previewWidth, setPreviewWidth] = useState(32);
  const [previewAnimating, setPreviewAnimating] = useState(false);
  const CHAT_MIN = CHAT_COLUMN_MIN_PX;
  const PREVIEW_OPEN_DEFAULT = 460;
  const [selectedModel, setSelectedModel] = useState<string>("glm-4");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [agentProfiles, setAgentProfiles] = useState<Array<{ name: string; provider: string; model: string; models: string[] }>>([]);
  const lastInputRef = useRef("");
  const draggingRef = useRef<null | "chat" | "preview">(null);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const headerRef = useRef<HTMLDivElement>(null);
  const [headerWidth, setHeaderWidth] = useState(9999);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765";
  const [runtimeMode, setRuntimeMode] = useState<"configured" | "unconfigured" | "fake" | null>(null);

  const isAgentRunning =
    isLoading || runStatus === "running" || runStatus === "awaitingApproval";

  const configUrl = useMemo(() => {
    return process.env.NEXT_PUBLIC_AGUI_DIRECT === "1" ? `${apiBase}/api/config` : "/api/config";
  }, [apiBase]);

  // Load provider/model + common models (and profiles) from config on mount
  const loadModelFromConfig = useCallback(async () => {
    try {
      const res = await fetch(configUrl);
      if (!res.ok) return;
      const cfg = (await res.json()) as {
        agents?: {
          defaults?: { model?: string; provider?: string };
          models?: string[];
          profiles?: Array<{ name?: string; provider?: string; model?: string; models?: string[] }>;
        };
      };
      const p = cfg?.agents?.defaults?.provider;
      const m = cfg?.agents?.defaults?.model;

      const profiles = Array.isArray(cfg?.agents?.profiles)
        ? cfg.agents.profiles
            .map((x) => ({
              name: String(x?.name || "").trim(),
              provider: String(x?.provider || "").trim(),
              model: String(x?.model || "").trim(),
              models: Array.isArray(x?.models) ? x!.models!.map((mm) => String(mm || "").trim()).filter((mm) => mm) : [],
            }))
            .filter((x) => x.name && x.provider)
        : [];
      setAgentProfiles(profiles);

      const provider = typeof p === "string" && p.trim() ? p.trim() : "";
      const model = typeof m === "string" && m.trim() ? m.trim() : "";

      // If we have a profile for the current provider, prefer it as the source
      // of common models for the header selector.
      const prof = provider ? profiles.find((x) => x.provider === provider || x.name === provider) : undefined;
      const list = prof?.models ?? (Array.isArray(cfg?.agents?.models) ? cfg.agents.models : []);
      const cleaned = Array.isArray(list) ? list.map((x) => (typeof x === "string" ? x.trim() : "")).filter((x) => x) : [];
      setModelOptions(cleaned);
      if (provider) setSelectedProvider(provider);
      if (model) setSelectedModel(model);
    } catch {
      // keep default
    }
  }, [configUrl]);

  useEffect(() => {
    void loadModelFromConfig();
  }, [loadModelFromConfig]);

  useEffect(() => {
    void hydrateProjectOverview();
  }, []);

  useEffect(() => {
    resetProjectOverviewSessionState();
    void hydrateProjectOverview();
  }, [threadId]);

  const refreshRuntimeMode = useCallback(async () => {
    const base = apiBase.replace(/\/$/, "");
    try {
      const r = await fetch(`${base}/api/runtime`);
      if (!r.ok) return;
      const j = (await r.json()) as { mode?: unknown };
      const mode = j?.mode;
      if (mode === "configured" || mode === "unconfigured" || mode === "fake") setRuntimeMode(mode);
    } catch {
      // ignore
    }
  }, [apiBase]);

  // Detect backend runtime mode (for "unconfigured" banner).
  useEffect(() => {
    void refreshRuntimeMode();
  }, [refreshRuntimeMode]);

  const providerOptions = useMemo(() => {
    const names = agentProfiles.map((p) => p.provider);
    const unique = Array.from(new Set(names)).filter((x) => x);
    return unique;
  }, [agentProfiles]);

  const applyProviderProfile = useCallback(
    async (providerName: string) => {
      const provider = providerName.trim();
      if (!provider) return;
      const prof = agentProfiles.find((x) => x.provider === provider || x.name === provider);
      const nextModel = prof?.model || "";
      const nextModels = prof?.models || [];

      // Persist provider+model so chat uses the correct provider server-side.
      try {
        const patch = { agents: { defaults: { provider, model: nextModel || undefined }, models: nextModels } };
        await fetch(configUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
      } catch {
        // best effort; still update local state
      }

      setSelectedProvider(provider);
      if (nextModel) setSelectedModel(nextModel);
      setModelOptions(nextModels);
    },
    [agentProfiles, configUrl],
  );

  const closeBlockingAction = useCallback(() => {
    setBlockingActionPath(null);
    setActiveRightTabId((cur) => {
      if (cur !== "__blocking__") return cur;
      return previewTabs[0]?.id ?? null;
    });
  }, [previewTabs]);

  const closePreviewTab = useCallback((id: string) => {
    setPreviewTabs((prev) => {
      const next = prev.filter((t) => t.id !== id);
      setActiveRightTabId((cur) => {
        if (cur !== id) return cur;
        if (blockingActionPath) return "__blocking__";
        return next[0]?.id ?? null;
      });
      return next;
    });
  }, [blockingActionPath]);

  const openFilePreview = useCallback((path: string) => {
    const p = normalizeSyntheticSkillUiPath(path);
    if (isBaseLayerDashboardSkillUi(p)) {
      return;
    }
    if (isBlockingActionSkillUi(p)) {
      setBlockingActionPath(p);
      setActiveRightTabId("__blocking__");
      return;
    }
    const id = p;
    setPreviewTabs((prev) => {
      const exists = prev.some((t) => t.id === id);
      if (exists) {
        setActiveRightTabId(id);
        return prev;
      }
      const label = previewTabLabel(p);
      setActiveRightTabId(id);
      return [...prev, { id, path: p, label }];
    });
  }, []);

  const wakePreview = useCallback((path: string) => {
    const normalized = normalizeSyntheticSkillUiPath(path);
    if (isBaseLayerDashboardSkillUi(normalized)) {
      openFilePreview(normalized);
      return;
    }
    openFilePreview(normalized);
    if (previewWidth <= 32) {
      setPreviewAnimating(true);
      setPreviewWidth(PREVIEW_OPEN_DEFAULT);
      setTimeout(() => setPreviewAnimating(false), 260);
    }
  }, [previewWidth, openFilePreview]);

  // ── AUTO_OPEN detector ────────────────────────────────────────────────────
  // Scans assistant messages for [AUTO_OPEN](browser://URL) markers emitted by
  // the Agent. Each unique (messageId, URL) pair triggers exactly one auto-open
  // so that streaming updates and re-renders don't re-fire it.
  const autoOpenedRef = useRef(new Set<string>());
  useEffect(() => {
    const AUTO_OPEN_RE = /\[AUTO_OPEN\]\(browser:\/\/([^)\s]+)\)/g;
    for (const msg of messages) {
      if (msg.role !== "assistant") continue;
      AUTO_OPEN_RE.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = AUTO_OPEN_RE.exec(msg.content)) !== null) {
        const dedupeKey = `${msg.id}::${match[1]}`;
        if (!autoOpenedRef.current.has(dedupeKey)) {
          autoOpenedRef.current.add(dedupeKey);
          wakePreview(`browser://${match[1]}`);
        }
      }
    }
  }, [messages, wakePreview]);

  // ── RENDER_UI detector (skill-ui://...) ─────────────────────────────────
  const renderUiOpenedRef = useRef(new Set<string>());
  useEffect(() => {
    const RENDER_UI_RE = /\[RENDER_UI\]\((skill-ui:\/\/[^)]+)\)/g;
    for (const msg of messages) {
      if (msg.role !== "assistant") continue;
      RENDER_UI_RE.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = RENDER_UI_RE.exec(msg.content)) !== null) {
        const uri = match[1].trim();
        const dedupeKey = `${msg.id}::${uri}`;
        if (!renderUiOpenedRef.current.has(dedupeKey)) {
          renderUiOpenedRef.current.add(dedupeKey);
          wakePreview(uri);
        }
      }
    }
  }, [messages, wakePreview]);
  // ─────────────────────────────────────────────────────────────────────────

  const closeSystemModal = useCallback(() => {
    setSystemModal(null);
  }, []);

  const openControlCenter = useCallback((tab: ControlCenterTab = "config") => {
    setControlCenterTab(tab);
    setSystemModal("controlCenter");
  }, []);

  const openSettings = useCallback(() => {
    openControlCenter("settings");
  }, [openControlCenter]);

  const openRemoteAssetDetail = useCallback((assetId: string) => {
    setSelectedOrgAssetId(assetId);
    setSystemModal("remoteAssetDetail");
  }, []);

  const openRemoteAssetUpload = useCallback(() => {
    setSystemModal("remoteUpload");
  }, []);

  const refreshSidebarAssets = useCallback(() => {
    setSidebarRefreshNonce((value) => value + 1);
  }, []);

  const handleSkillSelect = useCallback((skillName: string) => {
    setActiveSkillName(skillName);
  }, []);

  /** 从会话文本解析 moduleId（支持 payload.moduleId 或顶层 moduleId，不要求整段为合法 JSON） */
  const moduleIdInferredFromMessages = useMemo(() => {
    const re = /"moduleId"\s*:\s*"([^"]+)"/g;
    for (let i = messages.length - 1; i >= 0; i--) {
      const raw = messages[i]?.content ?? "";
      if (!raw.includes("moduleId")) continue;
      re.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(raw)) !== null) {
        const t = m[1]?.trim();
        if (t) return t;
      }
    }
    return null;
  }, [messages]);

  const dashboardActiveSkillName = activeSkillName?.trim() || moduleIdInferredFromMessages;

  const handleFillInput = useCallback((text: string) => {
    setInputPrefill(text);
    setInputFocusSignal((n) => n + 1);
  }, []);

  const handleSend = useCallback((v: string) => {
    lastInputRef.current = v;
    setInputPrefill("");
    setToastDismissed(false);
    void sendMessage(v, selectedModel);
  }, [selectedModel, sendMessage]);

  const handlePendingChoiceSelect = useCallback(
    (choice: ChoiceItem) => {
      clearPendingChoices();
      void sendMessage(choice.value, selectedModel);
    },
    [clearPendingChoices, sendMessage, selectedModel],
  );

  const expandPreviewPanel = useCallback(() => {
    if (previewWidth > 32) return;
    setPreviewAnimating(true);
    setPreviewWidth(PREVIEW_OPEN_DEFAULT);
    setTimeout(() => setPreviewAnimating(false), 260);
  }, [previewWidth]);

  const handleRetry = useCallback(() => {
    if (!lastInputRef.current) return;
    setToastDismissed(false);
    void sendMessage(lastInputRef.current, selectedModel);
  }, [selectedModel, sendMessage]);

  const showError = error && !toastDismissed;

  const startDrag = (side: "chat" | "preview", e: React.MouseEvent) => {
    draggingRef.current = side;
    dragStartX.current = e.clientX;
    dragStartWidth.current = side === "chat" ? chatWidth : previewWidth;
    e.preventDefault();
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const dx = e.clientX - dragStartX.current;
      if (draggingRef.current === "chat") {
        const cap = getChatColumnMaxPx();
        setChatWidth(Math.max(CHAT_MIN, Math.min(cap, dragStartWidth.current + dx)));
      } else if (draggingRef.current === "preview") {
        const next = Math.max(PREVIEW_OPEN_DEFAULT, Math.min(RIGHT_PANEL_MAX, dragStartWidth.current - dx));
        setPreviewWidth(next);
      }
    };
    const onUp = () => { draggingRef.current = null; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  useEffect(() => {
    const clamp = () => {
      setChatWidth((w) => Math.max(CHAT_MIN, Math.min(getChatColumnMaxPx(), w)));
    };
    window.addEventListener("resize", clamp);
    clamp();
    return () => window.removeEventListener("resize", clamp);
  }, []);

  // Track header width for compact mode.
  // IMPORTANT: only update state when the compact threshold (760 px) is crossed,
  // NOT on every pixel change, to avoid a ResizeObserver → setState → re-render
  // → DOM shrink → ResizeObserver → ... infinite loop.
  const prevCompactRef = useRef(false);
  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 9999;
      const nextCompact = w < 760;
      if (nextCompact !== prevCompactRef.current) {
        prevCompactRef.current = nextCompact;
        setHeaderWidth(w);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        setSearchOpen(true);
        return;
      }
      if (e.key === "Escape") {
        if (blockingActionPath) {
          e.preventDefault();
          closeBlockingAction();
          return;
        }
        if (systemModal) {
          e.preventDefault();
          closeSystemModal();
          return;
        }
        setSearchOpen(false);
        setSearchQuery("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [blockingActionPath, systemModal, closeBlockingAction, closeSystemModal]);

  const closePreview = useCallback(() => {
    setPreviewAnimating(true);
    setPreviewWidth(32);
    setTimeout(() => {
      setPreviewAnimating(false);
      setBlockingActionPath(null);
      setPreviewTabs([]);
      setActiveRightTabId(null);
    }, 260);
  }, []);

  const activePreviewTabPath = useMemo(() => {
    if (!activeRightTabId) return null;
    if (activeRightTabId === "__blocking__") return blockingActionPath;
    return previewTabs.find((t) => t.id === activeRightTabId)?.path ?? null;
  }, [activeRightTabId, blockingActionPath, previewTabs]);

  const sidebarProps = {
    threadId,
    apiBase,
    onClear: clearChat,
    onPreviewPath: openFilePreview,
    currentPreviewPath: previewWidth > 32
      ? blockingActionPath ?? activePreviewTabPath
      : null,
    onClosePreview: closePreview,
    messages,
    isLoading,
    sessions,
    onCreateSession: createSession,
    onSelectSession: switchSession,
    onDeleteSession: deleteSession,
    onOpenSettings: openSettings,
    onSkillSelect: handleSkillSelect,
    onOpenOrgAssetDetail: openRemoteAssetDetail,
    refreshNonce: sidebarRefreshNonce,
  };

  const openConfig = useCallback(() => {
    openControlCenter("config");
  }, [openControlCenter]);

  const artifacts = useMemo(() => {
    const paths: string[] = [];
    for (const msg of messages) {
      if (msg.artifacts) paths.push(...msg.artifacts);
    }
    return [...new Set(paths)];
  }, [messages]);

  const toggleDesktopSidebar = useCallback(() => {
    setNavExpanded((prev) => !prev);
  }, []);

  const togglePreviewPanel = useCallback(() => {
    if (previewWidth > 32) {
      closePreview();
      return;
    }
    if (activePreviewTabPath) {
      wakePreview(activePreviewTabPath);
      return;
    }
    expandPreviewPanel();
  }, [activePreviewTabPath, closePreview, expandPreviewPanel, previewWidth, wakePreview]);

  const openArtifactsHub = useCallback(() => {
    if (artifacts.length > 0) {
      wakePreview(artifacts[0]);
    } else {
      setNavExpanded(true);
    }
  }, [artifacts, wakePreview]);

  const openSkillsHub = useCallback(() => {
    setNavExpanded(true);
  }, []);

  return (
    <main className="h-dvh overflow-hidden p-4" style={{ background: "var(--surface-0)", color: "var(--text-primary)" }}>
      {runtimeMode === "unconfigured" ? (
        <div className="mb-3 rounded-xl border border-[color-mix(in_oklab,var(--warning)_35%,transparent)] bg-[color-mix(in_oklab,var(--warning)_10%,var(--surface-1))] px-4 py-3 text-xs text-[var(--text-primary)]">
          <span className="font-medium">当前处于未初始化配置模式：</span>
          可进入右上角「控制中心」填写模型与 API Key；保存后请重启{" "}
          <code className="font-mono">npm run dev</code> 使配置生效。
        </div>
      ) : null}
      {showError && (
        <ErrorToast
          message={error}
          onRetry={handleRetry}
          onClose={() => setToastDismissed(true)}
        />
      )}
      {searchOpen && (
        <SearchOverlay
          query={searchQuery}
          onQueryChange={setSearchQuery}
          onClose={() => { setSearchOpen(false); setSearchQuery(""); }}
          messages={messages}
        />
      )}
      {systemModal === "controlCenter" && (
        <SystemShellModal onClose={closeSystemModal} title="控制中心">
          <ControlCenterPanel
            key={controlCenterTab}
            initialTab={controlCenterTab}
            onClose={closeSystemModal}
            onOpenRemoteUpload={openRemoteAssetUpload}
            onSaved={() => {
              void loadModelFromConfig();
              void refreshRuntimeMode();
            }}
          />
        </SystemShellModal>
      )}
      {systemModal === "remoteAssetDetail" && (
        <SystemShellModal onClose={closeSystemModal} title="资源详情">
          <div className="max-h-[92vh] min-h-0 overflow-y-auto">
            <RemoteAssetDetailPanel
              assetId={selectedOrgAssetId}
              onClose={closeSystemModal}
              onOpenUpload={() => setSystemModal("remoteUpload")}
              onImported={refreshSidebarAssets}
            />
          </div>
        </SystemShellModal>
      )}
      {systemModal === "remoteUpload" && (
        <SystemShellModal onClose={closeSystemModal} title="上传资源">
          <div className="max-h-[92vh] min-h-0 overflow-y-auto">
            <RemoteAssetUploadPanel onClose={closeSystemModal} onUploaded={refreshSidebarAssets} />
          </div>
        </SystemShellModal>
      )}

      {/* Mobile hamburger */}
      <button
        type="button"
        onClick={() => setSidebarOpen(true)}
        aria-label="打开侧栏"
        aria-expanded={sidebarOpen}
        className="md:hidden fixed top-3 left-3 z-40 rounded-lg ui-panel p-2 ui-text-secondary"
      >
        <Menu size={16} />
      </button>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-black/60"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}
      {sidebarOpen && (
        <div className="md:hidden fixed inset-y-0 left-0 z-40 w-[21rem] p-2 bg-zinc-950 rounded-r-2xl shadow-xl border-r border-white/5">
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            aria-label="关闭侧栏"
            className="absolute top-4 right-4 z-50 rounded p-1 ui-text-secondary hover:text-[var(--text-primary)]"
          >
            <X size={16} />
          </button>
          <Sidebar
            {...sidebarProps}
            onSelectSession={(id) => {
              setSidebarOpen(false);
              switchSession(id);
            }}
          />
        </div>
      )}

      {/* 预览收起时：会话区旁的胶囊入口，展开右侧分屏（不依赖是否已有预览 Tab） */}
      {previewWidth <= 32 ? (
        <button
          type="button"
          className="hidden md:flex fixed z-[35] items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium shadow-lg transition-colors hover:opacity-95"
          style={{
            right: "44px",
            bottom: "calc(5rem + env(safe-area-inset-bottom, 0px))",
            background: "var(--surface-2)",
            borderColor: "var(--border-subtle)",
            color: "var(--text-primary)",
          }}
          title="展开右侧预览分屏"
          onClick={() => {
            if (activePreviewTabPath) wakePreview(activePreviewTabPath);
            else expandPreviewPanel();
          }}
        >
          <PanelRightOpen size={14} className="shrink-0 opacity-80" />
          预览分屏
        </button>
      ) : null}

      {/* Desktop layout: 4-column Mission Control */}
      <div className="hidden md:flex h-full min-h-0 gap-0">

        {/* Col 1: Nav strip (collapsed 44px) or full Sidebar */}
        {navExpanded ? (
          <div className="shrink-0 min-h-0 overflow-hidden" style={{ width: 260 }}>
            <Sidebar
              {...sidebarProps}
              isCollapsed={false}
              onToggleCollapse={() => setNavExpanded(false)}
            />
          </div>
        ) : (
          <div className="w-11 shrink-0 min-h-0 bg-zinc-950 rounded-l-2xl border-r border-white/5 flex flex-col items-center py-3 gap-2">
            <button
              type="button"
              title="展开导航"
              className="text-lg leading-none mb-1 hover:scale-110 transition-transform cursor-pointer bg-transparent border-0 p-0"
              onClick={() => setNavExpanded(true)}
              aria-label="展开侧边栏"
            >
              🦞
            </button>
            <span className="w-1.5 h-1.5 rounded-full mb-2" style={{ background: "var(--success)" }} />
            <button type="button" onClick={createSession} title="新建会话" className="nav-icon-btn">
              <Plus size={18} />
            </button>
            <div className="mt-auto" />
          </div>
        )}

        {/* Col 2: Chat */}
        <div
          className="shrink-0 min-h-0 flex flex-col bg-[var(--paper-chat)] rounded-2xl shadow-[var(--shadow-card)] ring-1 ring-black/[0.05] dark:ring-white/10 overflow-hidden"
          style={{ width: chatWidth }}
        >
          <div ref={headerRef} className="mb-2 flex shrink-0 items-start justify-between gap-2 px-2 pt-2 min-w-0">
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={toggleDesktopSidebar}
                aria-label={navExpanded ? "收起左侧栏" : "打开左侧栏"}
                title={navExpanded ? "收起左侧栏" : "打开左侧栏"}
                className={headerIconButtonClass}
              >
                <SidebarIcon size={17} />
              </button>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {providerOptions.length > 0 && (
                <label className="inline-flex items-center gap-2 text-xs ui-text-secondary">
                  <select
                    value={selectedProvider}
                    onChange={(e) => void applyProviderProfile(e.target.value)}
                    className="rounded-lg border px-2 py-1 text-xs"
                    style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                    aria-label="选择提供商"
                  >
                    {providerOptions.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </label>
              )}
              <ModelSelector
                value={selectedModel}
                onChange={(m) => {
                  setSelectedModel(m);
                  void fetch(configUrl, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ agents: { defaults: { provider: selectedProvider || undefined, model: m } } }),
                  }).catch(() => {});
                }}
                models={modelOptions}
                compact={headerWidth < 760}
              />
              <button type="button" onClick={openConfig} aria-label="控制中心" title="控制中心"
                className={headerIconButtonClass}>
                <Settings size={17} />
              </button>
              <button
                type="button"
                onClick={togglePreviewPanel}
                aria-label={previewWidth > 32 ? "收起右侧栏" : "打开右侧栏"}
                title={previewWidth > 32 ? "收起右侧栏" : "打开右侧栏"}
                className={headerIconButtonClass}
              >
                {previewWidth > 32 ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
              </button>
              <button
                type="button"
                onClick={openArtifactsHub}
                aria-label="产物中心"
                title={artifacts.length > 0 ? `产物中心（${artifacts.length}）` : "产物中心"}
                className={`relative ${headerIconButtonClass}`}
              >
                <FileText size={17} />
                {artifacts.length > 0 && (
                  <span className="absolute right-1 top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full px-1 text-[8px] font-bold text-white" style={{ background: "var(--accent)" }}>
                    {artifacts.length > 9 ? "9+" : artifacts.length}
                  </span>
                )}
              </button>
              <button
                type="button"
                onClick={openSkillsHub}
                aria-label="技能中心"
                title="技能中心"
                className={headerIconButtonClass}
              >
                <Zap size={17} />
              </button>
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-1 py-1 transition-colors hover:bg-[var(--surface-3)]">
                <ThemeToggle />
              </div>
            </div>
          </div>
          <div className="flex-1 min-h-0">
            <ChatArea
              messages={messages}
              stepLogs={stepLogs}
              isLoading={isLoading}
              runStatus={runStatus}
              statusMessage={statusMessage}
              effectiveModel={effectiveModel}
              pendingTool={pendingTool}
              pendingChoices={pendingChoices}
              onSend={handleSend}
              onStop={stopGenerating}
              onApproveTool={(approved) => { void approveTool(approved); }}
              onFileLinkClick={wakePreview}
              onDeleteMessage={deleteMessage}
              searchQuery={searchQuery}
              disabled={isLoading || !threadId}
              focusSignal={inputFocusSignal}
              prefillText={inputPrefill}
              chatCardPostToAgent={(text) => void sendMessage(text, selectedModel)}
              onSelectPendingChoice={handlePendingChoiceSelect}
              onDismissPendingChoices={clearPendingChoices}
            />
          </div>
        </div>

        {/* Drag handle: chat ↔ dashboard */}
        <div
          className="w-3 shrink-0 cursor-col-resize flex items-center justify-center group select-none"
          title="拖拽调整会话区宽度"
          role="separator"
          aria-orientation="vertical"
          aria-label="调整会话与大盘宽度"
          onMouseDown={(e) => startDrag("chat", e)}
        >
          <div className="w-0.5 h-12 rounded-full transition-colors group-hover:bg-[var(--accent)]" style={{ background: "var(--border-subtle)" }} />
        </div>

        {/* Col 3: DashboardNavigator */}
        <div
          className="flex-1 min-w-[280px] min-h-0 bg-[var(--surface-0)] rounded-2xl overflow-hidden dashboard-container"
          style={{ containerType: "inline-size", containerName: "dashboard" } as React.CSSProperties}
        >
          <DashboardNavigator
            threadId={threadId}
            activeModuleIds={activeModuleIds}
            skillUiPatchEvent={skillUiPatchEvent}
            skillUiBootstrapEvent={skillUiBootstrapEvent}
            onOpenPreview={wakePreview}
            postToAgent={(text) => void sendMessage(text, selectedModel)}
            postToAgentSilently={(text) => void sendSilentMessage(text, selectedModel)}
            isAgentRunning={isAgentRunning}
            activeSkillName={dashboardActiveSkillName}
          />
        </div>

        {/* Drag handle: dashboard ↔ preview */}
        {previewWidth > 32 && (
          <div className="w-3 shrink-0 cursor-col-resize flex items-center justify-center group" onMouseDown={(e) => startDrag("preview", e)}>
            <div className="w-0.5 h-12 rounded-full transition-colors group-hover:bg-[var(--accent)]" style={{ background: "var(--border-subtle)" }} />
          </div>
        )}

        {/* Col 4: Preview smart wake */}
        <div
          className="shrink-0 min-h-0 overflow-hidden"
          style={{ width: previewWidth, transition: previewAnimating ? "width 250ms ease-out" : "none" }}
        >
          {previewWidth <= 32 ? (
            <div
              className="h-full flex flex-col items-center justify-center gap-2 cursor-pointer bg-[var(--surface-0)] rounded-r-2xl border-l border-white/5"
              onClick={() => activePreviewTabPath && wakePreview(activePreviewTabPath)}
            >
              <PanelRightOpen size={14} className="text-zinc-600" />
              <span className="writing-vertical text-[9px] text-zinc-600 select-none">点击产物预览</span>
            </div>
          ) : (
            <div className="h-full flex flex-col bg-[var(--canvas-rail)] rounded-r-2xl overflow-hidden p-2">
              <div className="flex items-center justify-between px-1 py-1 shrink-0">
                <span className="text-xs ui-text-muted font-semibold tracking-wide">预览</span>
                <button type="button" onClick={closePreview} className="rounded p-1 ui-text-muted hover:ui-text-primary" title="收起预览">
                  <PanelRightClose size={14} />
                </button>
              </div>
              <PreviewPanel
                onClose={closePreview}
                baseDashboardUrl={null}
                blockingActionPath={blockingActionPath}
                onCloseBlockingAction={closeBlockingAction}
                previewTabs={previewTabs}
                activeTabId={activeRightTabId}
                onSelectTab={setActiveRightTabId}
                onClosePreviewTab={closePreviewTab}
                onOpenPath={openFilePreview}
                activeSkillName={dashboardActiveSkillName}
                onFillInput={handleFillInput}
                postToAgent={(text) => void sendMessage(text, selectedModel)}
                isAgentRunning={isAgentRunning}
                skillUiPatchEvent={skillUiPatchEvent}
              />
            </div>
          )}
        </div>
      </div>

      {/* Mobile layout — single Paper column */}
      <div className="md:hidden h-full min-h-0 flex flex-col rounded-2xl overflow-hidden bg-[var(--paper-chat)] shadow-[var(--shadow-card)] ring-1 ring-black/[0.05] dark:ring-white/10">
        <ChatArea
          messages={messages}
          stepLogs={stepLogs}
          isLoading={isLoading}
          runStatus={runStatus}
          statusMessage={statusMessage}
          effectiveModel={effectiveModel}
          pendingTool={pendingTool}
          pendingChoices={pendingChoices}
          onSend={handleSend}
          onStop={stopGenerating}
          onApproveTool={(approved) => { void approveTool(approved); }}
          onFileLinkClick={openFilePreview}
          onDeleteMessage={deleteMessage}
          searchQuery={searchQuery}
          disabled={isLoading || !threadId}
          focusSignal={inputFocusSignal}
          prefillText={inputPrefill}
          chatCardPostToAgent={(text) => void sendMessage(text, selectedModel)}
          onSelectPendingChoice={handlePendingChoiceSelect}
          onDismissPendingChoices={clearPendingChoices}
        />
      </div>
    </main>
  );
}
