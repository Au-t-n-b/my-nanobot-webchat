"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Menu, Settings, X } from "lucide-react";
import { ChatArea } from "@/components/ChatArea";
import { ChoicesModal } from "@/components/ChoicesModal";
import { ErrorToast } from "@/components/ErrorToast";
import { PreviewPanel } from "@/components/PreviewPanel";
import { SearchOverlay } from "@/components/SearchOverlay";
import { SettingsPanel } from "@/components/SettingsPanel";
import { Sidebar } from "@/components/Sidebar";
import { ModelSelector } from "@/components/ModelSelector";
import { ConfigPanel } from "@/components/ConfigPanel";
import { TaskProgressBar } from "@/components/TaskProgressBar";
import { useAgentChat } from "@/hooks/useAgentChat";
import { previewKindFromPath } from "@/lib/previewKind";

const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 560;       // left panel max
const SIDEBAR_DEFAULT = 280;   // left panel default
const RIGHT_PANEL_DEFAULT = 460;
const RIGHT_PANEL_MAX = typeof window !== "undefined"
  ? Math.floor(window.innerWidth * 0.62)
  : 900;

type RightPanelMode = "preview" | "settings" | "config";

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
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [rightPanelMode, setRightPanelMode] = useState<RightPanelMode>("preview");
  const [activeSkillName, setActiveSkillName] = useState<string | null>(null);
  const [inputFocusSignal, setInputFocusSignal] = useState(0);
  const [toastDismissed, setToastDismissed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [leftWidth, setLeftWidth] = useState(SIDEBAR_DEFAULT);
  const [rightWidth, setRightWidth] = useState(RIGHT_PANEL_DEFAULT);
  const [selectedModel, setSelectedModel] = useState<string>("glm-4");
  const lastInputRef = useRef("");
  const draggingRef = useRef<null | "left" | "right">(null);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765";

  // Load the default model from config on mount
  const loadModelFromConfig = useCallback(async () => {
    try {
      const url =
        process.env.NEXT_PUBLIC_AGUI_DIRECT === "1"
          ? `${apiBase}/api/config`
          : "/api/config";
      const res = await fetch(url);
      if (!res.ok) return;
      const cfg = (await res.json()) as {
        agents?: { defaults?: { model?: string } };
      };
      const m = cfg?.agents?.defaults?.model;
      if (m && typeof m === "string") setSelectedModel(m);
    } catch {
      // keep default
    }
  }, [apiBase]);

  useEffect(() => {
    void loadModelFromConfig();
  }, [loadModelFromConfig]);

  const openFilePreview = useCallback((path: string) => {
    setPreviewPath(path);
    setRightPanelMode("preview");
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
  // ─────────────────────────────────────────────────────────────────────────

  const openSettings = useCallback(() => {
    setRightPanelMode("settings");
    setIsPreviewOpen(true);
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

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        setSearchOpen(true);
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
        setSearchQuery("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const closePreview = useCallback(() => {
    setIsPreviewOpen(false);
    setPreviewPath(null);
  }, []);

  const sidebarProps = {
    threadId,
    apiBase,
    onClear: clearChat,
    onPreviewPath: openFilePreview,
    currentPreviewPath: (isPreviewOpen && rightPanelMode === "preview") ? previewPath : null,
    onClosePreview: closePreview,
    messages,
    isLoading,
    sessions,
    onCreateSession: createSession,
    onSelectSession: switchSession,
    onDeleteSession: deleteSession,
    onOpenSettings: openSettings,
    onSkillSelect: handleSkillSelect,
  };

  const openConfig = useCallback(() => {
    setRightPanelMode("config");
    setIsPreviewOpen(true);
  }, []);

  const rightPanel =
    rightPanelMode === "settings" ? (
      <SettingsPanel onClose={() => setIsPreviewOpen(false)} />
    ) : rightPanelMode === "config" ? (
      <ConfigPanel onClose={() => setIsPreviewOpen(false)} onSaved={loadModelFromConfig} />
    ) : (
      <PreviewPanel
        onClose={() => setIsPreviewOpen(false)}
        filePath={previewPath}
        onOpenPath={openFilePreview}
        activeSkillName={activeSkillName}
        onFillInput={handleFillInput}
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
        <div className="md:hidden fixed inset-y-0 left-0 z-40 w-[21rem] p-3">
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

      {/* Desktop layout: flex with resizable panels */}
      <div className="hidden md:flex h-full min-h-0 gap-0">
        {/* Left sidebar */}
        {!sidebarCollapsed && (
          <>
            <div className="min-h-0 shrink-0" style={{ width: leftWidth }}>
              <Sidebar {...sidebarProps} />
            </div>
            {/* Left drag handle */}
            <div
              className="w-3 shrink-0 cursor-col-resize flex items-center justify-center group"
              onMouseDown={(e) => startDrag("left", e)}
              title="拖拽调整左侧栏宽度"
            >
              <div className="w-0.5 h-12 rounded-full transition-colors group-hover:bg-[var(--accent)]" style={{ background: "var(--border-subtle)" }} />
            </div>
          </>
        )}

        {/* Chat area */}
        <div className="flex-1 min-w-0 min-h-0 flex flex-col">
          {/* Top control bar — progress rail on left, actions on right */}
          <div className="flex items-start gap-1.5 mb-2 shrink-0 min-w-0">
            {/* Inline progress rail — flex-1 so it fills available space */}
            <TaskProgressBar runStatus={runStatus} />

            {/* Right-side action buttons */}
            <div className="flex items-center gap-1.5 shrink-0">
              <ModelSelector value={selectedModel} onChange={setSelectedModel} />
              <button
                type="button"
                onClick={openConfig}
                aria-label="配置中心"
                title="配置中心"
                className="rounded-lg p-2 ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary transition-colors border border-transparent hover:border-[var(--border-subtle)]"
              >
                <Settings size={17} />
              </button>
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
              className="min-h-0 shrink-0"
              style={{
                width: previewKindFromPath(previewPath ?? "") === "browser"
                  ? Math.max(rightWidth, Math.min(RIGHT_PANEL_MAX, Math.floor((typeof window !== "undefined" ? window.innerWidth : 1200) * 0.55)))
                  : rightWidth,
              }}
            >
              {rightPanel}
            </div>
          </>
        )}
      </div>

      {/* Mobile layout */}
      <div className="md:hidden h-full min-h-0">
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
