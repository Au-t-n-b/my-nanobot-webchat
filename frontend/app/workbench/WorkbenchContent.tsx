"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Focus, Menu, PanelRightClose, PanelRightOpen, Plus, Settings, Sidebar as SidebarIcon, Trash2, X, Zap } from "lucide-react";
import { ChatArea } from "@/components/ChatArea";
import { ErrorToast } from "@/components/ErrorToast";
import { PreviewPanel } from "@/components/preview";
import { RemoteAssetDetailPanel } from "@/components/RemoteAssetDetailPanel";
import { RemoteAssetUploadPanel } from "@/components/RemoteAssetUploadPanel";
import { SearchOverlay } from "@/components/SearchOverlay";
import { SystemShellModal } from "@/components/SystemShellModal";
import { CommandPalette, type CommandPaletteItem } from "@/components/CommandPalette";
import { Sidebar } from "@/components/Sidebar";
import { ModelSelector } from "@/components/ModelSelector";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useAgentChat, type ChoiceItem } from "@/hooks/useAgentChat";
import type { FileInsightReport } from "@/components/preview/previewTypes";
import { coerceFileInsightReport } from "@/lib/fileInsightReport";
import { buildSkillAgentTaskExecuteEnvelope } from "@/lib/skillHybridProtocol";
import type { SduiUploadedFileRecord } from "@/lib/sdui";
import { hybridSubtaskHintFromTaskStatus } from "@/lib/skillHybridProtocol";
import {
  buildProjectGuideColdStartUserPrompt,
  isProjectGuideColdStartSettled,
  projectGuideColdStartStorageKey,
  PROJECT_GUIDE_COLD_START_DONE_BAD,
  PROJECT_GUIDE_COLD_START_OK,
} from "@/lib/projectGuideColdStart";
import { useTheme } from "@/hooks/useTheme";
import { DashboardNavigator } from "@/components/DashboardNavigator";
import { ControlCenterPanel } from "@/components/ControlCenterPanel";
import { ModuleStepper } from "@/components/dashboard/ModuleStepper";
import {
  hydrateProjectOverview,
  resetProjectOverviewSessionState,
  selectProjectOverviewModules,
  useProjectOverviewStore,
} from "@/lib/projectOverviewStore";
import {
  isBaseLayerDashboardSkillUi,
  normalizeSyntheticSkillUiPath,
} from "@/lib/skillUiRegistry";
import {
  clearGlobalProjectContext,
  hasWorkspaceAccess,
  patchGlobalProjectContext,
} from "@/lib/globalProjectContext";
import {
  createLocalProjectWithMeta,
  deleteLocalProject,
  getSelectedLocalProjectId,
  listLocalProjects,
  NANOBOT_LOCAL_PROJECTS_CHANGED,
  setSelectedLocalProjectId,
  type LocalProject,
} from "@/lib/localProjects";
import { workspacePayloadToLocalProjectMeta } from "@/lib/mapWorkspaceProjectPayload";
import type { WorkspaceProjectCreatePayload } from "@/lib/workspaceProjectCreate";
import { LocalProjectNavDropdown } from "@/components/workbench/LocalProjectNavDropdown";
import { WorkbenchTopNavSlot } from "@/components/workbench/shell/WorkbenchTopNavSlot";
import { NewWorkspaceProjectModal } from "@/components/workbench/NewWorkspaceProjectModal";
import { CenteredConfirmModal } from "@/components/CenteredModal";
import {
  CHAT_COLUMN_MIN_PX,
  getChatColumnMaxPx,
  getInitialChatWidthState,
  persistWorkbenchChatWidthPx,
  RIGHT_PANEL_MAX,
} from "@/lib/workbenchChatLayout";

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

/** HITL SkillUiChatCard 的 SDUI 节点上挂有 skillName/moduleId，但对应消息的 content 往往为空，需在节点树上推断大盘模块。 */
function extractSkillHintFromSduiNode(node: unknown): string | null {
  if (!node || typeof node !== "object") return null;
  const o = node as Record<string, unknown>;
  const skillName = o.skillName;
  if (typeof skillName === "string" && skillName.trim()) {
    const s = skillName.trim();
    // Tool-only HITL cards (request_user_upload / present_choices) use nanobot_agent as a synthetic skillName.
    // It must NOT drive the right-side module dashboard focus.
    if (s === "nanobot_agent") return null;
    return s;
  }
  const moduleId = o.moduleId;
  if (typeof moduleId === "string" && moduleId.trim()) return moduleId.trim();
  const children = o.children;
  if (Array.isArray(children)) {
    for (const c of children) {
      const hint = extractSkillHintFromSduiNode(c);
      if (hint) return hint;
    }
  }
  return null;
}

export default function WorkbenchContent() {
  const router = useRouter();
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
    skillUiPatchQueue,
    skillUiBootstrapEvent,
    taskStatusEvent,
    activeModuleIds,
    sendMessage,
    sendSilentMessage,
    sendChatRequest,
    stopGenerating,
    approveTool,
    clearPendingChoices,
    clearChat,
    undoClearChat,
    deleteMessage,
    deleteSession,
    createSession,
    switchSession,
    lockPresentChoicesCard,
    lockFilePickerCard,
    subscribeSkillAgentTaskResult,
  } = useAgentChat();
  const { setTheme } = useTheme();
  const overviewModules = useProjectOverviewStore(selectProjectOverviewModules);
  const activeModuleId = useProjectOverviewStore((snapshot) => snapshot.activeModuleId);
  const [inputPrefill, setInputPrefill] = useState("");
  const [previewTabs, setPreviewTabs] = useState<Array<{ id: string; path: string; label: string }>>([]);
  /** 右栏当前激活 Tab：具体 previewTab.id(path) */
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
  /** 右侧大盘：总览 vs Skill 模块视图（用于在模块大盘时隐藏顶栏项目区） */
  const [dashboardNavigatorView, setDashboardNavigatorView] = useState<"overview" | "module">("overview");
  const [chatWidth, setChatWidth] = useState(() => getInitialChatWidthState());
  const chatWidthRef = useRef(chatWidth);
  const [previewWidth, setPreviewWidth] = useState(32);
  const [previewAnimating, setPreviewAnimating] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const commandPaletteOpenRef = useRef(false);
  const [zenMode, setZenMode] = useState(false);
  const [clearUndoToast, setClearUndoToast] = useState(false);
  const CHAT_MIN = CHAT_COLUMN_MIN_PX;

  useEffect(() => {
    chatWidthRef.current = chatWidth;
  }, [chatWidth]);
  const PREVIEW_OPEN_DEFAULT = 460;
  /** 预览抽屉开合时长（略带回弹感的 cubic-bezier，接近弹簧阻尼） */
  const PREVIEW_ANIM_MS = 340;
  const DASHBOARD_MIN = 400;
  const [selectedModel, setSelectedModel] = useState<string>("glm-4");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [agentProfiles, setAgentProfiles] = useState<Array<{ name: string; provider: string; model: string; models: string[] }>>([]);
  const lastInputRef = useRef("");
  /** 防止 React Strict Mode 或重挂载对同一会话双发 project_guide 冷启动 */
  const projectGuideColdStartInFlightRef = useRef(false);
  const sendChatRequestRef = useRef(sendChatRequest);
  const isLoadingRef = useRef(isLoading);
  sendChatRequestRef.current = sendChatRequest;
  isLoadingRef.current = isLoading;
  const draggingRef = useRef<null | "chat" | "preview">(null);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const headerRef = useRef<HTMLDivElement>(null);
  const [headerWidth, setHeaderWidth] = useState(9999);

  const [localProjects, setLocalProjects] = useState<LocalProject[]>([]);
  const [selectedProjectId, setSelectedProjectIdState] = useState("");
  const [newProjectModalOpen, setNewProjectModalOpen] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765";
  const [runtimeMode, setRuntimeMode] = useState<"configured" | "unconfigured" | "fake" | null>(null);

  const isAgentRunning =
    isLoading || runStatus === "running" || runStatus === "awaitingApproval";

  useEffect(() => {
    projectGuideColdStartInFlightRef.current = false;
  }, [threadId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const tid = (threadId || "").trim();
    if (!tid) return;
    const key = projectGuideColdStartStorageKey(tid);
    if (isProjectGuideColdStartSettled(window.sessionStorage.getItem(key))) return;
    if (projectGuideColdStartInFlightRef.current) return;
    let cancelled = false;
    let activeTimer: number | null = null;
    const arm = (fn: () => void, ms: number) => {
      if (activeTimer != null) window.clearTimeout(activeTimer);
      activeTimer = window.setTimeout(fn, ms) as number;
    };
    const MAX_LOADING_WAIT = 50;

    const sendOnce = () => {
      if (cancelled) return;
      if (isProjectGuideColdStartSettled(window.sessionStorage.getItem(key))) return;
      if (projectGuideColdStartInFlightRef.current) return;
      const tidNow = (threadId || "").trim();
      if (tidNow !== tid) return;
      projectGuideColdStartInFlightRef.current = true;
      const coldPrompt = buildProjectGuideColdStartUserPrompt();
      void sendChatRequestRef
        .current(coldPrompt, selectedModel, {
          showInTranscript: false,
          showAssistantInTranscript: true,
          showCompletionMessage: true,
        })
        .then((ok) => {
          projectGuideColdStartInFlightRef.current = false;
          if (cancelled) return;
          try {
            window.sessionStorage.setItem(key, ok ? PROJECT_GUIDE_COLD_START_OK : PROJECT_GUIDE_COLD_START_DONE_BAD);
          } catch {
            /* ignore */
          }
        })
        .catch(() => {
          projectGuideColdStartInFlightRef.current = false;
          if (cancelled) return;
          try {
            window.sessionStorage.setItem(key, PROJECT_GUIDE_COLD_START_DONE_BAD);
          } catch {
            /* ignore */
          }
        });
    };

    let waitCount = 0;
    const schedule = () => {
      if (cancelled) return;
      if (isProjectGuideColdStartSettled(window.sessionStorage.getItem(key))) return;
      if (isLoadingRef.current) {
        waitCount += 1;
        if (waitCount < MAX_LOADING_WAIT) {
          arm(schedule, 100);
        } else {
          try {
            window.sessionStorage.setItem(key, PROJECT_GUIDE_COLD_START_DONE_BAD);
          } catch {
            /* 放弃，避免 isLoading/回调引用抖动导致反复冷启动、界面狂闪 */
          }
        }
        return;
      }
      sendOnce();
    };

    arm(() => {
      queueMicrotask(schedule);
    }, 0);

    return () => {
      cancelled = true;
      if (activeTimer != null) window.clearTimeout(activeTimer);
    };
  }, [threadId, selectedModel]);

  const hybridSubtaskHint = useMemo(
    () => hybridSubtaskHintFromTaskStatus(taskStatusEvent),
    [taskStatusEvent],
  );

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

  const reloadProjectsFromStorage = useCallback(() => {
    const list = listLocalProjects();
    let sel = getSelectedLocalProjectId() ?? "";
    let repaired = false;
    if (sel && !list.some((p) => p.id === sel)) {
      sel = list[0]?.id ?? "";
      if (sel) {
        setSelectedLocalProjectId(sel);
        repaired = true;
      }
    }
    setLocalProjects(list);
    setSelectedProjectIdState(sel);
    if (repaired && sel) {
      const p = list.find((x) => x.id === sel);
      if (p) patchGlobalProjectContext({ project: p });
    }
  }, []);

  useEffect(() => {
    reloadProjectsFromStorage();
    const onChange = () => reloadProjectsFromStorage();
    window.addEventListener(NANOBOT_LOCAL_PROJECTS_CHANGED, onChange);
    return () => window.removeEventListener(NANOBOT_LOCAL_PROJECTS_CHANGED, onChange);
  }, [reloadProjectsFromStorage]);

  const patchProjectContext = useCallback((p: LocalProject) => {
    patchGlobalProjectContext({ project: p });
  }, []);

  const handlePickProject = useCallback(
    (id: string) => {
      setSelectedLocalProjectId(id);
      setSelectedProjectIdState(id);
      const p = listLocalProjects().find((x) => x.id === id);
      if (p) patchProjectContext(p);
    },
    [patchProjectContext],
  );

  const handleCreateProject = useCallback(
    async (payload: WorkspaceProjectCreatePayload) => {
      const meta = workspacePayloadToLocalProjectMeta(payload);
      const p = createLocalProjectWithMeta(meta);
      setLocalProjects(listLocalProjects());
      setSelectedProjectIdState(p.id);
      patchProjectContext(p);
    },
    [patchProjectContext],
  );

  const confirmDeleteProject = useCallback(() => {
    if (!deleteTargetId) return;
    setDeleteBusy(true);
    try {
      const { projects, selectedId } = deleteLocalProject(deleteTargetId);
      setLocalProjects(projects);
      setSelectedProjectIdState(selectedId ?? "");
      if (selectedId) {
        const p = projects.find((x) => x.id === selectedId);
        if (p) patchProjectContext(p);
      }
    } finally {
      setDeleteBusy(false);
      setDeleteTargetId(null);
    }
  }, [deleteTargetId, patchProjectContext]);

  /** 门禁由 workbench/page 负责；此处防止运行中门禁被撤销时仍停留 */
  useEffect(() => {
    if (!hasWorkspaceAccess()) {
      router.replace("/");
    }
  }, [router]);

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

  const closePreviewTab = useCallback((id: string) => {
    setPreviewTabs((prev) => {
      const next = prev.filter((t) => t.id !== id);
      setActiveRightTabId((cur) => {
        if (cur !== id) return cur;
        return next[0]?.id ?? null;
      });
      return next;
    });
  }, []);

  const openFilePreview = useCallback((path: string) => {
    const p = normalizeSyntheticSkillUiPath(path);
    if (isBaseLayerDashboardSkillUi(p)) {
      return;
    }
    // B 宪法：右侧预览栏禁止渲染 skill-ui://（模块大盘只在中栏）
    if (p.startsWith("skill-ui://")) return;
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
      setTimeout(() => setPreviewAnimating(false), PREVIEW_ANIM_MS);
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

  // B 宪法：skill-ui:// 不通过右侧预览栏打开（模块大盘在中栏）
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

  /** 从会话文本解析 skillName（skill-first fast-path/卡片按钮会携带 skillName） */
  const skillNameInferredFromMessages = useMemo(() => {
    const re = /"skillName"\s*:\s*"([^"]+)"/g;
    for (let i = messages.length - 1; i >= 0; i--) {
      const raw = messages[i]?.content ?? "";
      if (!raw.includes("skillName")) continue;
      re.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(raw)) !== null) {
        const t = m[1]?.trim();
        if (t) return t;
      }
    }
    return null;
  }, [messages]);

  /** 从最近一条聊天卡片（HITL）的 SDUI 节点推断当前 Skill，避免大盘一直停在 PLAN */
  const skillNameInferredFromChatCards = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m?.kind !== "chat_card" || !m.chatCard?.node) continue;
      const hint = extractSkillHintFromSduiNode(m.chatCard.node);
      if (hint) return hint;
    }
    return null;
  }, [messages]);

  /** 从消息里的 RENDER_UI / skill-ui syntheticPath 推断模块名（不依赖 moduleId/skillName 字段存在） */
  const skillNameInferredFromSkillUiPath = useMemo(() => {
    // Examples:
    // [RENDER_UI](skill-ui://SduiView?dataFile=skills/text_organizer_showcase/data/dashboard.json)
    // skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json
    const re = /dataFile=\/?skills\/([^/]+)\//g;
    for (let i = messages.length - 1; i >= 0; i--) {
      const raw = messages[i]?.content ?? "";
      if (!raw.includes("skills/") || !raw.includes("dataFile=")) continue;
      re.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(raw)) !== null) {
        const t = m[1]?.trim();
        if (t) return t;
      }
    }
    return null;
  }, [messages]);

  // Prefer paths / HITL card skillName over LLM ``moduleId`` strings (often wrong or humanized).
  const dashboardActiveSkillName =
    activeSkillName?.trim() ||
    skillNameInferredFromSkillUiPath ||
    skillNameInferredFromChatCards ||
    skillNameInferredFromMessages ||
    moduleIdInferredFromMessages;

  const onPreviewInsightRequest = useCallback(
    async (filePath: string): Promise<FileInsightReport> => {
      const p = (filePath || "").trim();
      if (!p) throw new Error("empty_path");
      if (!threadId) throw new Error("no_thread");
      const taskId = `preview-insight-${
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(16).slice(2)}`
      }`;
      const goal =
        `仅分析工作区内相对路径 \`${p}\`：` +
        "使用允许的工具 read_file_head / read_file_tail / read_hex_dump / list_dir 读取有限片段，" +
        "输出严格符合 FileInsightReport 的 JSON（字段 file_type_guess, summary, risk_level, extracted_snippets, next_action_suggestion）。不得编造未读到的内容。";

      return await new Promise<FileInsightReport>((resolve, reject) => {
        let settled = false;
        const timer = window.setTimeout(() => {
          if (settled) return;
          settled = true;
          unsubscribe();
          reject(new Error("洞察请求超时"));
        }, 120_000);

        const unsubscribe = subscribeSkillAgentTaskResult((evt) => {
          if (evt.taskId !== taskId) return;
          if (settled) return;
          settled = true;
          window.clearTimeout(timer);
          unsubscribe();
          if (evt.ok && evt.report) {
            const coerced = coerceFileInsightReport(evt.report);
            if (!coerced) {
              reject(new Error("invalid_report_shape"));
              return;
            }
            resolve(coerced);
          } else {
            reject(new Error(evt.error || "insight_failed"));
          }
        });

        const envelope = buildSkillAgentTaskExecuteEnvelope({
          threadId,
          skillName: (dashboardActiveSkillName || "nanobot_preview").trim() || "nanobot_preview",
          skillRunId: `run-preview-insight-${threadId}`,
          payload: {
            taskId,
            stepId: "preview.file_insight",
            goal,
            resultDelivery: "sse",
            maxIterations: 8,
            resultSchema: { type: "FileInsightReport" },
          },
        });

        const intent = {
          type: "chat_card_intent" as const,
          verb: "skill_runtime_event" as const,
          payload: envelope,
        };

        void sendSilentMessage(JSON.stringify(intent), selectedModel).catch((e) => {
          if (settled) return;
          settled = true;
          window.clearTimeout(timer);
          unsubscribe();
          reject(e instanceof Error ? e : new Error(String(e)));
        });
      });
    },
    [threadId, subscribeSkillAgentTaskResult, sendSilentMessage, selectedModel, dashboardActiveSkillName],
  );

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

  const handleChatCardSendText = useCallback(
    (text: string, opts?: { cardId?: string; submittedValue?: string }) => {
      const v = text.trim();
      if (!v) return;
      void sendMessage(v, selectedModel);
      const cid = (opts?.cardId ?? "").trim();
      const submitted = (opts?.submittedValue ?? "").trim();
      if (cid && submitted) lockPresentChoicesCard(cid, submitted);
    },
    [lockPresentChoicesCard, selectedModel, sendMessage],
  );

  const handleChatCardLockFilePicker = useCallback(
    (cardId: string, uploads: SduiUploadedFileRecord[]) => {
      const cid = (cardId ?? "").trim();
      if (!cid) return;
      lockFilePickerCard(cid, uploads);
    },
    [lockFilePickerCard],
  );

  const expandPreviewPanel = useCallback(() => {
    if (previewWidth > 32) return;
    setPreviewAnimating(true);
    setPreviewWidth(PREVIEW_OPEN_DEFAULT);
    setTimeout(() => setPreviewAnimating(false), PREVIEW_ANIM_MS);
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
    const onUp = () => {
      if (draggingRef.current === "chat") {
        persistWorkbenchChatWidthPx(chatWidthRef.current);
      }
      draggingRef.current = null;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [CHAT_MIN]);

  useEffect(() => {
    const clamp = () => {
      setChatWidth((w) => Math.max(CHAT_MIN, Math.min(getChatColumnMaxPx(), w)));
    };
    window.addEventListener("resize", clamp);
    clamp();
    return () => window.removeEventListener("resize", clamp);
  }, [CHAT_MIN]);

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

  const closePreview = useCallback(() => {
    setPreviewAnimating(true);
    setPreviewWidth(32);
    setTimeout(() => {
      setPreviewAnimating(false);
      setPreviewTabs([]);
      setActiveRightTabId(null);
    }, PREVIEW_ANIM_MS);
  }, []);

  const openCommandPalette = useCallback(() => {
    commandPaletteOpenRef.current = true;
    setCommandPaletteOpen(true);
  }, []);

  const closeCommandPalette = useCallback(() => {
    commandPaletteOpenRef.current = false;
    setCommandPaletteOpen(false);
  }, []);

  const toggleZenMode = useCallback(() => {
    setZenMode((z) => {
      const next = !z;
      if (next) closePreview();
      return next;
    });
  }, [closePreview]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openCommandPalette();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        setSearchOpen(true);
        return;
      }
      if (e.key === "Escape") {
        if (commandPaletteOpenRef.current) return;
        if (systemModal) {
          e.preventDefault();
          closeSystemModal();
          return;
        }
        if (zenMode) {
          e.preventDefault();
          setZenMode(false);
          return;
        }
        setSearchOpen(false);
        setSearchQuery("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [systemModal, zenMode, closeSystemModal, openCommandPalette]);

  const activePreviewTabPath = useMemo(() => {
    if (!activeRightTabId) return null;
    return previewTabs.find((t) => t.id === activeRightTabId)?.path ?? null;
  }, [activeRightTabId, previewTabs]);

  const handleLogout = useCallback(() => {
    clearGlobalProjectContext();
    router.replace("/");
  }, [router]);

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

  const sidebarProps = {
    threadId,
    apiBase,
    onPreviewPath: openFilePreview,
    currentPreviewPath: previewWidth > 32
      ? activePreviewTabPath
      : null,
    onClosePreview: closePreview,
    messages,
    isLoading,
    sessions,
    onCreateSession: createSession,
    onSelectSession: switchSession,
    onDeleteSession: deleteSession,
    onOpenSettings: openSettings,
    onOpenQuickSettings: openSettings,
    onLogout: handleLogout,
    onSkillSelect: handleSkillSelect,
    onOpenOrgAssetDetail: openRemoteAssetDetail,
    refreshNonce: sidebarRefreshNonce,
    onOpenArtifactsHub: openArtifactsHub,
    onOpenSkillsHub: openSkillsHub,
  };

  const paletteCommands = useMemo<CommandPaletteItem[]>(() => {
    return [
      {
        id: "new-session",
        label: "新建会话",
        hint: "空白对话线程",
        keywords: ["session", "新对话"],
        run: () => {
          closeCommandPalette();
          createSession();
        },
      },
      {
        id: "zen-toggle",
        label: zenMode ? "退出专注模式" : "进入专注模式",
        hint: "隐藏侧栏与大盘，仅保留会话区",
        keywords: ["zen", "专注", "全屏"],
        run: () => {
          closeCommandPalette();
          toggleZenMode();
        },
      },
      {
        id: "expand-nav",
        label: "展开左侧导航",
        keywords: ["sidebar", "侧栏", "会话", "技能"],
        run: () => {
          closeCommandPalette();
          setNavExpanded(true);
        },
      },
      {
        id: "show-dashboard",
        label: "显示大盘与工作台",
        keywords: ["dashboard", "大盘", "sdui", "模块"],
        run: () => {
          closeCommandPalette();
          setZenMode(false);
          setNavExpanded(true);
        },
      },
      {
        id: "open-preview",
        label: "打开右侧预览抽屉",
        keywords: ["preview", "预览", "产物"],
        run: () => {
          closeCommandPalette();
          expandPreviewPanel();
        },
      },
      {
        id: "artifacts-hub",
        label: "打开产物预览",
        keywords: ["artifacts", "产物", "文件"],
        run: () => {
          closeCommandPalette();
          openArtifactsHub();
        },
      },
      {
        id: "skills-hub",
        label: "展开技能侧栏",
        keywords: ["skills", "技能"],
        run: () => {
          closeCommandPalette();
          openSkillsHub();
        },
      },
      {
        id: "search-messages",
        label: "搜索消息",
        hint: "同 Ctrl/⌘+F",
        keywords: ["search", "查找"],
        run: () => {
          closeCommandPalette();
          setSearchOpen(true);
        },
      },
      {
        id: "control-center",
        label: "打开控制中心",
        keywords: ["config", "设置", "api"],
        run: () => {
          closeCommandPalette();
          openControlCenter("config");
        },
      },
      {
        id: "theme-dark",
        label: "切换为深色主题",
        keywords: ["dark", "夜间"],
        run: () => {
          closeCommandPalette();
          setTheme("dark");
        },
      },
      {
        id: "theme-light",
        label: "切换为浅色主题",
        keywords: ["light", "白日"],
        run: () => {
          closeCommandPalette();
          setTheme("light");
        },
      },
      {
        id: "theme-soft",
        label: "切换为护眼主题",
        keywords: ["soft", "护眼"],
        run: () => {
          closeCommandPalette();
          setTheme("soft");
        },
      },
    ];
  }, [
    zenMode,
    createSession,
    toggleZenMode,
    expandPreviewPanel,
    openArtifactsHub,
    openSkillsHub,
    openControlCenter,
    closeCommandPalette,
    setTheme,
  ]);

  useEffect(() => {
    if (!clearUndoToast) return;
    const t = window.setTimeout(() => setClearUndoToast(false), 8000);
    return () => window.clearTimeout(t);
  }, [clearUndoToast]);

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

      <CommandPalette open={commandPaletteOpen} onClose={closeCommandPalette} commands={paletteCommands} />

      <NewWorkspaceProjectModal
        open={newProjectModalOpen}
        onDismiss={() => setNewProjectModalOpen(false)}
        onCreate={handleCreateProject}
      />

      <CenteredConfirmModal
        open={Boolean(deleteTargetId)}
        title="删除项目"
        variant="danger"
        confirmText="删除"
        loading={deleteBusy}
        description={
          deleteTargetId ? (
            <span>
              确定删除项目「
              <span className="font-semibold ui-text-primary">
                {localProjects.find((p) => p.id === deleteTargetId)?.name ?? deleteTargetId}
              </span>
              」？此操作不可恢复。
            </span>
          ) : null
        }
        onCancel={() => {
          if (!deleteBusy) setDeleteTargetId(null);
        }}
        onConfirm={() => {
          confirmDeleteProject();
        }}
      />

      {clearUndoToast ? (
        <div
          className="fixed bottom-5 left-1/2 z-[95] flex max-w-[min(100%,24rem)] -translate-x-1/2 flex-wrap items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3 text-sm shadow-[var(--shadow-panel)]"
          role="status"
        >
          <span className="ui-text-secondary">已清空当前会话</span>
          <button
            type="button"
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-3)] px-3 py-1 text-xs font-medium ui-text-primary hover:opacity-90"
            onClick={() => {
              if (undoClearChat()) setClearUndoToast(false);
            }}
          >
            撤销
          </button>
          <button
            type="button"
            className="text-xs ui-text-muted hover:ui-text-primary"
            onClick={() => setClearUndoToast(false)}
          >
            关闭
          </button>
        </div>
      ) : null}

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
        <div className="md:hidden fixed inset-y-0 left-0 z-40 w-[21rem] p-2 bg-zinc-100 dark:bg-[#121214] rounded-r-2xl shadow-xl border-r border-zinc-200/90 dark:border-white/5">
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

      {/* Desktop layout: navigation + chat + overview, preview uses overlay drawer */}
      <div className="hidden md:block h-full min-h-0 overflow-x-auto">
        <div className={`flex h-full min-h-0 gap-0 ${zenMode ? "min-w-0" : "min-w-max"}`}>

          {/* Col 1: Nav strip (collapsed 44px) or full Sidebar */}
          {!zenMode &&
            (navExpanded ? (
              <div className="shrink-0 min-h-0 overflow-hidden" style={{ width: 260 }}>
                <Sidebar
                  {...sidebarProps}
                  isCollapsed={false}
                  onToggleCollapse={() => setNavExpanded(false)}
                />
              </div>
            ) : (
              <div className="w-11 shrink-0 min-h-0 rounded-l-2xl border-r border-white/5 bg-[var(--canvas-rail)] flex flex-col items-center py-3 gap-2">
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
                <button type="button" onClick={openSettings} title="设置" className="nav-icon-btn" aria-label="设置">
                  <Settings size={18} />
                </button>
                <div className="relative">
                  <button
                    type="button"
                    onClick={openArtifactsHub}
                    title={artifacts.length > 0 ? `产物中心（${artifacts.length}）` : "产物中心"}
                    className="nav-icon-btn"
                    aria-label="产物中心"
                  >
                    <FileText size={18} />
                  </button>
                  {artifacts.length > 0 && (
                    <span
                      className="pointer-events-none absolute right-0.5 top-0.5 flex h-3 min-w-3 items-center justify-center rounded-full px-0.5 text-[7px] font-bold text-white"
                      style={{ background: "var(--accent)" }}
                    >
                      {artifacts.length > 9 ? "9+" : artifacts.length}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={openSkillsHub}
                  title="技能中心"
                  className="nav-icon-btn"
                  aria-label="技能中心"
                >
                  <Zap size={18} />
                </button>
                <div className="mt-auto" />
              </div>
            ))}

          {/* Col 2: Chat */}
          <div
            className={
              zenMode
                ? "flex-1 min-w-0 min-h-0 flex flex-col bg-[var(--paper-chat)] rounded-2xl shadow-[var(--shadow-card)] ring-1 ring-black/[0.05] dark:ring-white/10 overflow-hidden"
                : "shrink-0 min-w-0 min-h-0 flex flex-col bg-[var(--paper-chat)] rounded-2xl shadow-[var(--shadow-card)] ring-1 ring-black/[0.05] dark:ring-white/10 overflow-hidden"
            }
            style={zenMode ? { minWidth: CHAT_MIN } : { width: chatWidth, minWidth: CHAT_MIN }}
          >
            <div ref={headerRef} className="mb-2 flex shrink-0 items-center gap-2 px-2 pt-2 min-w-0">
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
                <button
                  type="button"
                  onClick={openCommandPalette}
                  aria-label="命令面板"
                  title="命令面板（Ctrl+K 或 ⌘+K）"
                  className={headerIconButtonClass}
                >
                  <span className="text-[10px] font-semibold tabular-nums opacity-80">⌘K</span>
                </button>
                <button
                  type="button"
                  onClick={toggleZenMode}
                  aria-label={zenMode ? "退出专注模式" : "专注模式"}
                  title={zenMode ? "退出专注模式（Esc）" : "专注模式：隐藏侧栏与大盘"}
                  className={`${headerIconButtonClass}${zenMode ? " ring-1 ring-[color-mix(in_oklab,var(--accent)_45%,transparent)]" : ""}`}
                >
                  <Focus size={17} className={zenMode ? "text-[var(--accent)]" : undefined} />
                </button>
              </div>
              <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
                <div
                  className={
                    "flex min-w-0 max-w-full flex-wrap items-center justify-end gap-1.5 shrink rounded-2xl border px-1.5 py-1 shadow-sm " +
                    "border-black/[0.07] bg-white/55 backdrop-blur-md dark:border-white/10 dark:bg-white/[0.05]"
                  }
                >
                  {providerOptions.length > 0 && (
                    <label className="inline-flex items-center gap-1.5 text-xs ui-text-secondary">
                      <select
                        value={selectedProvider}
                        onChange={(e) => void applyProviderProfile(e.target.value)}
                        className="rounded-lg border px-2 py-1 text-xs bg-white/70 dark:bg-black/25"
                        style={{
                          borderColor: "color-mix(in oklab, var(--border-subtle) 80%, transparent)",
                          color: "var(--text-primary)",
                        }}
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
                    selectClassName="border-[color-mix(in_oklab,var(--border-subtle)_80%,transparent)] bg-white/70 dark:bg-black/25"
                  />
                  <button type="button" onClick={openConfig} aria-label="控制中心" title="控制中心"
                    className={headerIconButtonClass}>
                    <Settings size={17} />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      clearChat({ saveUndoSnapshot: true });
                      setClearUndoToast(true);
                    }}
                    aria-label="清空当前会话"
                    title="清空当前会话（可在底部通知中撤销）"
                    className={`${headerIconButtonClass} hover:text-red-500`}
                  >
                    <Trash2 size={17} />
                  </button>
                  <div className="rounded-xl border border-[color-mix(in_oklab,var(--border-subtle)_70%,transparent)] bg-white/40 px-1 py-0.5 transition-colors hover:bg-white/70 dark:border-white/10 dark:bg-black/20 dark:hover:bg-black/35">
                    <ThemeToggle />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={togglePreviewPanel}
                  aria-label={previewWidth > 32 ? "收起右侧预览栏" : "打开右侧预览栏"}
                  title={previewWidth > 32 ? "收起右侧预览栏" : "打开右侧预览栏"}
                  className={headerIconButtonClass}
                >
                  {previewWidth > 32 ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
                </button>
              </div>
            </div>
            <div className="min-w-0 shrink-0 overflow-visible relative z-20">
              <ModuleStepper
                modules={overviewModules}
                activeModuleId={activeModuleId}
                onSelectModule={undefined}
                className="pb-2"
              />
            </div>
            <div className="flex-1 min-w-0 min-h-0">
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
                chatCardPostToAgent={(text) => sendSilentMessage(text, selectedModel)}
                chatCardPostToAgentSilently={(text) => sendSilentMessage(text, selectedModel)}
                chatCardOnSendText={handleChatCardSendText}
                chatCardOnLockFilePicker={handleChatCardLockFilePicker}
                hybridSubtaskHint={hybridSubtaskHint}
              />
            </div>
          </div>

          {!zenMode ? (
            <>
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

              {/* Col 3: 工作区项目（仅总览） + 大盘 */}
              <div
                className="min-h-0 flex-1 flex flex-col min-w-0 rounded-2xl bg-[var(--surface-0)] overflow-hidden dashboard-container"
                style={{ containerType: "inline-size", containerName: "dashboard", minWidth: DASHBOARD_MIN } as React.CSSProperties}
              >
                {dashboardNavigatorView === "overview" ? (
                  <div className="shrink-0 flex justify-center border-b border-[var(--border-subtle)] bg-[var(--surface-0)] px-3 py-2.5">
                    <LocalProjectNavDropdown
                      projects={localProjects}
                      selectedId={selectedProjectId}
                      onSelect={handlePickProject}
                      onOpenNew={() => setNewProjectModalOpen(true)}
                      onRequestDelete={(id) => setDeleteTargetId(id)}
                      compact={false}
                    />
                  </div>
                ) : null}
                <div className="min-h-0 flex-1 overflow-hidden">
                  <DashboardNavigator
                    threadId={threadId}
                    activeModuleIds={activeModuleIds}
                    skillUiPatchQueue={skillUiPatchQueue}
                    skillUiBootstrapEvent={skillUiBootstrapEvent}
                    onOpenPreview={wakePreview}
                    postToAgent={(text) =>
                      (dashboardActiveSkillName ?? "").trim() === "tool_lab"
                        ? sendMessage(text, selectedModel)
                        : sendSilentMessage(text, selectedModel)
                    }
                    postToAgentSilently={(text) => sendSilentMessage(text, selectedModel)}
                    isAgentRunning={isAgentRunning}
                    activeSkillName={dashboardActiveSkillName}
                    onViewChange={setDashboardNavigatorView}
                  />
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>

      {previewWidth > 32 && (
        <>
          <button
            type="button"
            className="hidden md:block fixed inset-0 z-30 bg-black/42 backdrop-blur-[2px]"
            aria-label="关闭预览遮罩"
            onClick={closePreview}
          />
          <div
            className="hidden md:flex fixed right-3 top-3 bottom-3 z-40 min-h-0 overflow-hidden rounded-[1.4rem] border border-white/10 bg-[var(--canvas-rail)] p-2 shadow-2xl"
            style={{
              width: Math.max(400, previewWidth),
              maxWidth: RIGHT_PANEL_MAX,
              transition: previewAnimating
                ? `width ${PREVIEW_ANIM_MS}ms cubic-bezier(0.34, 1.18, 0.64, 1), opacity ${Math.round(PREVIEW_ANIM_MS * 0.75)}ms ease-out`
                : "none",
            }}
          >
            <div
              className="mr-2 flex w-3 shrink-0 cursor-col-resize items-center justify-center group"
              onMouseDown={(e) => startDrag("preview", e)}
              title="拖拽调整预览宽度"
            >
              <div className="h-14 w-0.5 rounded-full transition-colors group-hover:bg-[var(--accent)]" style={{ background: "var(--border-subtle)" }} />
            </div>
            <div className="min-h-0 flex-1 overflow-hidden">
              <PreviewPanel
                onClose={closePreview}
                previewTabs={previewTabs}
                activeTabId={activeRightTabId}
                onSelectTab={setActiveRightTabId}
                onClosePreviewTab={closePreviewTab}
                onOpenPath={openFilePreview}
                activeSkillName={dashboardActiveSkillName}
                onFillInput={handleFillInput}
                onPreviewInsightRequest={onPreviewInsightRequest}
              />
            </div>
          </div>
        </>
      )}

      {/* Mobile layout — single Paper column */}
      <div className="md:hidden h-full min-h-0 flex flex-col rounded-2xl overflow-hidden bg-[var(--paper-chat)] shadow-[var(--shadow-card)] ring-1 ring-black/[0.05] dark:ring-white/10">
        <div className="shrink-0 border-b border-[var(--border-subtle)] px-2 py-2">
          <WorkbenchTopNavSlot className="min-w-0">
            <LocalProjectNavDropdown
              projects={localProjects}
              selectedId={selectedProjectId}
              onSelect={handlePickProject}
              onOpenNew={() => setNewProjectModalOpen(true)}
              onRequestDelete={(id) => setDeleteTargetId(id)}
              compact
            />
          </WorkbenchTopNavSlot>
        </div>
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
          chatCardPostToAgent={(text) => sendSilentMessage(text, selectedModel)}
          chatCardPostToAgentSilently={(text) => sendSilentMessage(text, selectedModel)}
          chatCardOnSendText={handleChatCardSendText}
          chatCardOnLockFilePicker={handleChatCardLockFilePicker}
          hybridSubtaskHint={hybridSubtaskHint}
        />
      </div>
    </main>
  );
}
