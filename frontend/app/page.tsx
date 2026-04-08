"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Menu, Settings, X } from "lucide-react";
import { ChatArea } from "@/components/ChatArea";
import { ChoicesModal } from "@/components/ChoicesModal";
import { ErrorToast } from "@/components/ErrorToast";
import { PreviewPanel } from "@/components/PreviewPanel";
import { RemoteAssetDetailPanel } from "@/components/RemoteAssetDetailPanel";
import { RemoteAssetUploadPanel } from "@/components/RemoteAssetUploadPanel";
import { SearchOverlay } from "@/components/SearchOverlay";
import { SettingsPanel } from "@/components/SettingsPanel";
import { SystemShellModal } from "@/components/SystemShellModal";
import { Sidebar } from "@/components/Sidebar";
import { ModelSelector } from "@/components/ModelSelector";
import { ConfigPanel } from "@/components/ConfigPanel";
import { TaskProgressBar } from "@/components/TaskProgressBar";
import { useAgentChat } from "@/hooks/useAgentChat";
import { previewKindFromPath } from "@/lib/previewKind";
import {
  isBaseLayerDashboardSkillUi,
  isBlockingActionSkillUi,
  normalizeSyntheticSkillUiPath,
} from "@/lib/skillUiRegistry";

const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 560;       // left panel max
const SIDEBAR_DEFAULT = 280;   // left panel default
const RIGHT_PANEL_DEFAULT = 460;
const RIGHT_PANEL_MAX = typeof window !== "undefined"
  ? Math.floor(window.innerWidth * 0.62)
  : 900;

type SystemModal = null | "settings" | "config" | "remoteAssetDetail" | "remoteUpload";

function previewTabLabel(path: string): string {
  if (path.startsWith("browser://")) return "浏览器";
  const base = path.split(/[/\\]/).pop() ?? path;
  return base.length > 36 ? `${base.slice(0, 34)}…` : base;
}

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
    sendMessage,
    approveTool,
    clearPendingChoices,
    clearChat,
    deleteMessage,
    deleteSession,
    createSession,
    switchSession,
  } = useAgentChat();
  const [inputPrefill, setInputPrefill] = useState("");
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  /** 右栏业务视窗：底层大盘 + 预览类 Tab + 强阻断 Action SDUI */
  const [baseDashboardUrl, setBaseDashboardUrl] = useState<string | null>(null);
  const [blockingActionPath, setBlockingActionPath] = useState<string | null>(null);
  const [previewTabs, setPreviewTabs] = useState<Array<{ id: string; path: string; label: string }>>([]);
  /** 右栏当前激活 Tab：__dashboard__ / __blocking__ / 具体 previewTab.id(path) */
  const [activeRightTabId, setActiveRightTabId] = useState<string | null>(null);
  const [systemModal, setSystemModal] = useState<SystemModal>(null);
  const [activeSkillName, setActiveSkillName] = useState<string | null>(null);
  const [selectedOrgAssetId, setSelectedOrgAssetId] = useState<string | null>(null);
  const [sidebarRefreshNonce, setSidebarRefreshNonce] = useState(0);
  const [inputFocusSignal, setInputFocusSignal] = useState(0);
  const [toastDismissed, setToastDismissed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [leftWidth, setLeftWidth] = useState(SIDEBAR_DEFAULT);
  const [rightWidth, setRightWidth] = useState(RIGHT_PANEL_DEFAULT);
  const [selectedModel, setSelectedModel] = useState<string>("glm-4");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [agentProfiles, setAgentProfiles] = useState<Array<{ name: string; provider: string; model: string; models: string[] }>>([]);
  const lastInputRef = useRef("");
  const draggingRef = useRef<null | "left" | "right">(null);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const headerRef = useRef<HTMLDivElement>(null);
  const [headerWidth, setHeaderWidth] = useState(9999);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765";

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
      if (baseDashboardUrl) return "__dashboard__";
      return previewTabs[0]?.id ?? null;
    });
  }, [baseDashboardUrl, previewTabs]);

  const closePreviewTab = useCallback((id: string) => {
    setPreviewTabs((prev) => {
      const next = prev.filter((t) => t.id !== id);
      setActiveRightTabId((cur) => {
        if (cur !== id) return cur;
        if (blockingActionPath) return "__blocking__";
        if (baseDashboardUrl) return "__dashboard__";
        return next[0]?.id ?? null;
      });
      return next;
    });
  }, [blockingActionPath, baseDashboardUrl]);

  const openFilePreview = useCallback((path: string) => {
    const p = normalizeSyntheticSkillUiPath(path);
    if (isBaseLayerDashboardSkillUi(p)) {
      setBaseDashboardUrl(p);
      setIsPreviewOpen(true);
      setActiveRightTabId("__dashboard__");
      return;
    }
    if (isBlockingActionSkillUi(p)) {
      setBlockingActionPath(p);
      setIsPreviewOpen(true);
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
    setIsPreviewOpen(true);
  }, []);

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
          openFilePreview(`browser://${match[1]}`);
        }
      }
    }
  }, [messages, openFilePreview]);

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
          openFilePreview(uri);
        }
      }
    }
  }, [messages, openFilePreview]);
  // ─────────────────────────────────────────────────────────────────────────

  const closeSystemModal = useCallback(() => {
    setSystemModal(null);
  }, []);

  const openSettings = useCallback(() => {
    setSystemModal("settings");
  }, []);

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

  const handleRetry = useCallback(() => {
    if (!lastInputRef.current) return;
    setToastDismissed(false);
    void sendMessage(lastInputRef.current, selectedModel);
  }, [selectedModel, sendMessage]);

  const showError = error && !toastDismissed;

  const startDrag = (side: "left" | "right", e: React.MouseEvent) => {
    draggingRef.current = side;
    dragStartX.current = e.clientX;
    dragStartWidth.current = side === "left" ? leftWidth : rightWidth;
    e.preventDefault();
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const dx = e.clientX - dragStartX.current;
      if (draggingRef.current === "left") {
        setLeftWidth(Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, dragStartWidth.current + dx)));
      } else {
        setRightWidth(Math.max(SIDEBAR_MIN, Math.min(RIGHT_PANEL_MAX, dragStartWidth.current - dx)));
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
    setIsPreviewOpen(false);
    setBaseDashboardUrl(null);
    setBlockingActionPath(null);
    setPreviewTabs([]);
    setActiveRightTabId(null);
  }, []);

  const activePreviewTabPath = useMemo(() => {
    if (!activeRightTabId) return null;
    if (activeRightTabId === "__dashboard__") return baseDashboardUrl;
    if (activeRightTabId === "__blocking__") return blockingActionPath;
    return previewTabs.find((t) => t.id === activeRightTabId)?.path ?? null;
  }, [activeRightTabId, baseDashboardUrl, blockingActionPath, previewTabs]);

  const sidebarProps = {
    threadId,
    apiBase,
    onClear: clearChat,
    onPreviewPath: openFilePreview,
    currentPreviewPath: isPreviewOpen
      ? blockingActionPath ?? activePreviewTabPath ?? baseDashboardUrl
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
    setSystemModal("config");
  }, []);

  const rightPanel = (
    <PreviewPanel
      onClose={closePreview}
      baseDashboardUrl={baseDashboardUrl}
      blockingActionPath={blockingActionPath}
      onCloseBlockingAction={closeBlockingAction}
      previewTabs={previewTabs}
      activeTabId={activeRightTabId}
      onSelectTab={setActiveRightTabId}
      onClosePreviewTab={closePreviewTab}
      onOpenPath={openFilePreview}
      activeSkillName={activeSkillName}
      onFillInput={handleFillInput}
      postToAgent={(text) => void sendMessage(text, selectedModel)}
      isAgentRunning={isAgentRunning}
      skillUiPatchEvent={skillUiPatchEvent}
    />
  );

  return (
    <main className="h-dvh overflow-hidden p-4" style={{ background: "var(--surface-0)", color: "var(--text-primary)" }}>
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
      <ChoicesModal
        choices={pendingChoices}
        onSelect={(choice) => {
          clearPendingChoices();
          void sendMessage(choice.value, selectedModel);
        }}
        onClose={clearPendingChoices}
      />

      {systemModal === "settings" && (
        <SystemShellModal onClose={closeSystemModal} title="设置">
          <div className="max-h-[92vh] min-h-0 overflow-y-auto">
            <SettingsPanel onClose={closeSystemModal} onOpenRemoteUpload={openRemoteAssetUpload} />
          </div>
        </SystemShellModal>
      )}
      {systemModal === "config" && (
        <SystemShellModal onClose={closeSystemModal} title="配置中心">
          <div className="h-[85vh] min-h-[480px] max-h-[92vh] overflow-hidden flex flex-col">
            <ConfigPanel onClose={closeSystemModal} onSaved={loadModelFromConfig} />
          </div>
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
        <div className="md:hidden fixed inset-y-0 left-0 z-40 w-[21rem] p-2 bg-[var(--canvas-rail)] rounded-r-2xl shadow-xl border-r border-[var(--border-subtle)] dark:border-white/10">
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

      {/* Desktop layout: flex with resizable panels — Canvas | Paper | Canvas */}
      <div className="hidden md:flex h-full min-h-0 gap-0">
        {/* Left sidebar — always present; collapses to 64 px icon strip */}
        <div
          className="min-h-0 shrink-0 transition-[width] duration-200 bg-[var(--canvas-rail)] rounded-l-2xl overflow-hidden"
          style={{ width: sidebarCollapsed ? 64 : leftWidth }}
        >
          <Sidebar
            {...sidebarProps}
            isCollapsed={sidebarCollapsed}
            onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
          />
        </div>
        {/* Left drag handle — hidden when collapsed */}
        {!sidebarCollapsed && (
          <div
            className="w-3 shrink-0 cursor-col-resize flex items-center justify-center group"
            onMouseDown={(e) => startDrag("left", e)}
            title="拖拽调整左侧栏宽度"
          >
            <div className="w-0.5 h-12 rounded-full transition-colors group-hover:bg-[var(--accent)]" style={{ background: "var(--border-subtle)" }} />
          </div>
        )}

        {/* Chat area — Paper */}
        <div className="flex-1 min-w-0 min-h-0 flex flex-col bg-[var(--paper-chat)] rounded-2xl shadow-[var(--shadow-card)] ring-1 ring-black/[0.05] dark:ring-white/10 overflow-hidden">
          {/* Top control bar — progress rail on left, actions on right */}
          <div ref={headerRef} className="flex items-start gap-1.5 mb-2 shrink-0 min-w-0">
            {/* Inline progress rail — flex-1 so it fills available space */}
            <TaskProgressBar runStatus={runStatus} compact={headerWidth < 760} />

            {/* Right-side action buttons */}
            <div className="flex items-center gap-1.5 shrink-0">
              {providerOptions.length > 0 && (
                <label className="inline-flex items-center gap-2 text-xs ui-text-secondary">
                  {headerWidth >= 760 && <span className="whitespace-nowrap">提供商</span>}
                  <select
                    value={selectedProvider}
                    onChange={(e) => void applyProviderProfile(e.target.value)}
                    className="rounded-lg border px-2 py-1 text-xs"
                    style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                    aria-label="选择提供商"
                  >
                    {providerOptions.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <ModelSelector
                value={selectedModel}
                onChange={(m) => {
                  setSelectedModel(m);
                  // Optional: when the user switches model in the header, persist it
                  // so the backend uses the same model on the next turn.
                  void fetch(configUrl, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ agents: { defaults: { provider: selectedProvider || undefined, model: m } } }),
                  }).catch(() => {});
                }}
                models={modelOptions}
                compact={headerWidth < 760}
              />
              <button
                type="button"
                onClick={openConfig}
                aria-label="配置中心"
                title="配置中心"
                className="rounded-lg p-2 ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary transition-colors border border-transparent hover:border-[var(--border-subtle)]"
              >
                <Settings size={17} />
              </button>
              {/* Left sidebar toggle — appears before right panel toggle (left→right order) */}
              <button
                type="button"
                onClick={() => setSidebarCollapsed((v) => !v)}
                aria-label={sidebarCollapsed ? "展开左侧栏" : "收起左侧栏"}
                className="rounded-lg p-2 ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary transition-colors border border-transparent hover:border-[var(--border-subtle)]"
                title={sidebarCollapsed ? "展开左侧栏" : "收起左侧栏"}
              >
                {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
              </button>
              <button
                type="button"
                onClick={() => setIsPreviewOpen((v) => !v)}
                aria-label={isPreviewOpen ? "收起右侧预览" : "展开右侧预览"}
                className="rounded-lg p-2 ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary transition-colors border border-transparent hover:border-[var(--border-subtle)]"
                title={isPreviewOpen ? "收起右侧预览" : "展开右侧预览"}
              >
                {isPreviewOpen ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
              </button>
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
              onApproveTool={(approved) => { void approveTool(approved); }}
              onFileLinkClick={openFilePreview}
              onDeleteMessage={deleteMessage}
              searchQuery={searchQuery}
              disabled={isLoading || !threadId}
              focusSignal={inputFocusSignal}
              prefillText={inputPrefill}
            />
          </div>
        </div>

        {/* Right panel: preview or settings */}
        {isPreviewOpen && (
          <>
            {/* Right drag handle */}
            <div
              className="w-3 shrink-0 cursor-col-resize flex items-center justify-center group"
              onMouseDown={(e) => startDrag("right", e)}
              title="拖拽调整右侧栏宽度"
            >
              <div className="w-0.5 h-12 rounded-full transition-colors group-hover:bg-[var(--accent)]" style={{ background: "var(--border-subtle)" }} />
            </div>
            {/* Browser panels get extra width for comfortable viewing */}
            <div
              className="min-h-0 shrink-0 flex flex-col bg-[var(--canvas-rail)] rounded-r-2xl overflow-hidden p-2 min-w-0"
              style={{
                width: previewKindFromPath(blockingActionPath ?? activePreviewTabPath ?? baseDashboardUrl ?? "") === "browser"
                  ? Math.max(rightWidth, Math.min(RIGHT_PANEL_MAX, Math.floor((typeof window !== "undefined" ? window.innerWidth : 1200) * 0.55)))
                  : rightWidth,
              }}
            >
              {rightPanel}
            </div>
          </>
        )}
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
          onApproveTool={(approved) => { void approveTool(approved); }}
          onFileLinkClick={openFilePreview}
          onDeleteMessage={deleteMessage}
          searchQuery={searchQuery}
          disabled={isLoading || !threadId}
          focusSignal={inputFocusSignal}
          prefillText={inputPrefill}
        />
      </div>
    </main>
  );
}
