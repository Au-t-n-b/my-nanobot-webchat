"use client";

import React, { Component, memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Check, ChevronDown, Copy, FileText, Trash2, User } from "lucide-react";
import type { AgentMessage } from "@/hooks/useAgentChat";
import type { SduiUploadedFileRecord } from "@/lib/sdui";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import { extractFilesFromContent } from "@/lib/fileIndex";
import { normalizeSyntheticSkillUiPath } from "@/lib/skillUiRegistry";
import { SkillUiRuntimeProvider } from "@/components/sdui/SkillUiRuntimeProvider";
import { SduiNodeView } from "@/components/sdui/SduiNodeView";

type Props = {
  messages: AgentMessage[];
  isLoading: boolean;
  /** 最后一条助手消息在流式生成时显示 Markdown 尾游标 */
  showStreamingCaret?: boolean;
  inlineStatusTag?: string;
  onFileLinkClick?: (path: string) => void;
  /** 当前右侧预览激活的路径（用于产物卡片高亮与点击 toggle） */
  activePreviewPath?: string | null;
  /** 产物卡片点击：若与 activePreviewPath 相同则关闭预览，否则打开并切换 */
  onTogglePreviewPath?: (path: string) => void;
  onDeleteMessage?: (id: string) => void;
  searchQuery?: string;
  chatCardPostToAgent?: (text: string) => void | Promise<void>;
  chatCardPostToAgentSilently?: (text: string) => void | Promise<void>;
  /** Optional: allow chat cards to send plain text back to main input. */
  chatCardOnSendText?: (text: string, opts?: { cardId?: string; submittedValue?: string }) => void;
  /** FilePicker：将提交态与 uploads 写回聊天历史，支持刷新回放 */
  chatCardOnLockFilePicker?: (cardId: string, uploads: SduiUploadedFileRecord[]) => void;
};

/**
 * Hover action toolbar shown beneath each message bubble.
 * Includes copy and delete actions.
 */
function MessageActions({
  content,
  onDelete,
}: {
  content: string;
  onDelete?: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const copy = (e: React.MouseEvent) => {
    e.stopPropagation();
    void navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex items-center gap-0.5 mt-1">
      <button
        type="button"
        onClick={copy}
        aria-label="复制消息"
        title={copied ? "已复制" : "复制"}
        className="rounded-md p-1 ui-text-muted hover:text-[var(--text-secondary)] hover:bg-[var(--surface-3)] transition-colors"
      >
        {copied ? <Check size={11} style={{ color: "var(--success)" }} /> : <Copy size={11} />}
      </button>
      {onDelete && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          aria-label="删除消息"
          title="删除"
          className="rounded-md p-1 ui-text-muted hover:text-red-500 hover:bg-[var(--surface-3)] transition-colors"
        >
          <Trash2 size={11} />
        </button>
      )}
    </div>
  );
}

function fileBasename(p: string): string {
  return p.replace(/\\/g, "/").split("/").filter(Boolean).pop() ?? p;
}

/** 与右侧 activePreviewTabPath 对齐的稳定 DOM id（路径经 normalize 后 encode） */
function artifactAnchorId(normalizedPath: string): string {
  return `artifact-anchor-${encodeURIComponent(normalizedPath)}`;
}

/**
 * Pre-compute chip paths for every message in one pass so that:
 * 1. Bare filenames in message text are upgraded to full absolute paths using
 *    artifact data from ANY message (not just the current one).
 * 2. The same file is only shown once — in the earliest message that mentions it.
 */
function chipPathsFingerprintPart(m: AgentMessage): string {
  const arts = (m.artifacts ?? []).map((a) => a.trim()).join("\x1f");
  return `${m.id}:${m.role}:${m.content?.length ?? 0}:${arts}:${m.kind ?? "text"}:${m.chatCard?.cardId ?? ""}`;
}

function buildMessageChipPaths(messages: AgentMessage[]): string[][] {
  // Build a global basename → full-path map from all message artifacts.
  const globalMap = new Map<string, string>();
  for (const m of messages) {
    for (const raw of m.artifacts ?? []) {
      const p = raw.trim();
      if (p) globalMap.set(fileBasename(p).toLowerCase(), p);
    }
  }

  const globalSeen = new Set<string>(); // tracks paths shown in any earlier message

  return messages.map((m) => {
    if (m.role !== "assistant" || !m.content?.trim()) return [];

    // Extract paths from the message text, then upgrade bare names via global map.
    const fromContent = extractFilesFromContent(m.content);
    const candidates: string[] = [];
    const localSeen = new Set<string>();

    const addCandidate = (raw: string) => {
      const p = raw.trim();
      if (!p) return;
      const full = globalMap.get(fileBasename(p).toLowerCase()) ?? p;
      if (!localSeen.has(full)) {
        localSeen.add(full);
        candidates.push(full);
      }
    };

    for (const p of fromContent) addCandidate(p);
    for (const p of m.artifacts ?? []) addCandidate(p);

    // Keep only paths not already displayed in a prior message.
    const chips = candidates.filter((p) => !globalSeen.has(p));
    for (const p of chips) globalSeen.add(p);
    return chips;
  });
}

function FileIndexChips({
  paths,
  onFileLinkClick,
  activePreviewPath,
  onChipClick,
}: {
  paths: string[];
  onFileLinkClick?: (path: string) => void;
  activePreviewPath?: string | null;
  /** 产物 chip 点击（由 MessageList 注入：标记来源为左侧，避免反向联动误触发） */
  onChipClick?: (path: string) => void;
}) {
  if (paths.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {paths.map((path) => {
        const norm = normalizeSyntheticSkillUiPath(path);
        const active = Boolean(activePreviewPath && activePreviewPath === norm);
        return (
          <button
            key={path}
            id={artifactAnchorId(norm)}
            type="button"
            title={path}
            onClick={() => {
              if (onChipClick) return onChipClick(path);
              onFileLinkClick?.(path);
            }}
            className={
              "inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium transition-all duration-150 " +
              "hover:-translate-y-px hover:shadow-sm active:translate-y-0 " +
              (active
                ? "ring-2 ring-[var(--accent)] bg-[var(--surface-3)] text-[var(--text-primary)] border-[color-mix(in_oklab,var(--accent)_55%,var(--border-subtle))]"
                : "border-[color-mix(in_oklab,var(--accent)_45%,var(--border-subtle))] bg-[var(--accent-soft)] text-[var(--accent)]")
            }
          >
            <FileText size={11} />
            {fileBasename(path)}
          </button>
        );
      })}
    </div>
  );
}

function Avatar({ role }: { role: "user" | "assistant" }) {
  return (
    <div
      className={
        "shrink-0 mt-0.5 w-8 h-8 rounded-full flex items-center justify-center " +
        (role === "user" ? "bg-[var(--surface-3)]" : "ui-card")
      }
    >
      {role === "user" ? (
        <User size={16} className="ui-text-secondary" />
      ) : (
        <Bot size={16} style={{ color: "var(--accent)" }} />
      )}
    </div>
  );
}

class ChatCardErrorBoundary extends Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(err: unknown) {
    console.error("[ChatCard] render error", err);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div
          className="rounded-xl px-3 py-3 text-sm"
          style={{
            border: "1px solid rgba(239,107,115,0.24)",
            background: "rgba(239,107,115,0.08)",
            color: "var(--danger)",
          }}
        >
          ChatCard 渲染失败（已隔离，不影响聊天流）。
        </div>
      );
    }
    return this.props.children;
  }
}

function isPlainGuidanceCardNode(node: unknown): boolean {
  if (!node || typeof node !== "object") return false;
  const n = node as { type?: unknown; actions?: unknown };
  if (n.type !== "GuidanceCard") return false;
  const actions = Array.isArray(n.actions) ? n.actions : [];
  return actions.length === 0;
}

function ChatCardBubble({
  msg,
  onFileLinkClick,
  postToAgentRaw,
  postToAgentSilentlyRaw,
  onSendTextRaw,
  onLockFilePickerRaw,
  searchQuery,
}: {
  msg: AgentMessage;
  onFileLinkClick?: (path: string) => void;
  postToAgentRaw: (text: string) => void | Promise<void>;
  postToAgentSilentlyRaw?: (text: string) => void | Promise<void>;
  onSendTextRaw?: (text: string, opts?: { cardId?: string; submittedValue?: string }) => void;
  onLockFilePickerRaw?: (cardId: string, uploads: SduiUploadedFileRecord[]) => void;
  searchQuery?: string;
}) {
  const card = msg.chatCard;
  if (!card) return null;
  if (isPlainGuidanceCardNode(card.node)) {
    const text = String((card.node as { context?: unknown }).context ?? "").trim();
    if (!text) return null;
    return (
      <div className="w-full max-w-[min(100%,28rem)] rounded-2xl rounded-tl-sm px-5 py-4 text-base leading-relaxed ui-card">
        <AgentMarkdown content={text} onFileLinkClick={onFileLinkClick} searchQuery={searchQuery} />
      </div>
    );
  }
  // Force unmount on replace (new event id) to ensure any debounced timers in SDUI inputs are cleaned up.
  const mountKey = `${card.cardId}:${card.docId}`;
  return (
    <div
      className="chatcard-slide-up w-full max-w-[min(100%,28rem)] rounded-xl rounded-tl-sm px-4 py-3 text-sm ui-elevation-2"
      style={{
        background: "var(--paper-card)",
        border: "1px solid var(--border-subtle)",
        borderLeft: "3px solid var(--accent)",
      }}
    >
      {card.title ? (
        <div className="mb-2 text-xs font-semibold ui-text-primary">{card.title}</div>
      ) : null}
      <ChatCardErrorBoundary>
        <div key={mountKey} className="min-w-0">
          <SkillUiRuntimeProvider
            postToAgentRaw={postToAgentRaw}
            postToAgentSilentlyRaw={postToAgentSilentlyRaw}
            lockFilePickerCardRaw={onLockFilePickerRaw}
            onSendTextRaw={onSendTextRaw}
            onOpenPreview={(p) => onFileLinkClick?.(p)}
            docId={card.docId}
          >
            <SduiNodeView node={{ ...card.node, cardId: card.cardId } as unknown as typeof card.node} />
          </SkillUiRuntimeProvider>
        </div>
      </ChatCardErrorBoundary>
    </div>
  );
}

export const MessageList = memo(function MessageList({
  messages,
  isLoading,
  showStreamingCaret = false,
  inlineStatusTag,
  onFileLinkClick,
  activePreviewPath = null,
  onTogglePreviewPath,
  onDeleteMessage,
  searchQuery,
  chatCardPostToAgent,
  chatCardPostToAgentSilently,
  chatCardOnSendText,
  chatCardOnLockFilePicker,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);
  /** 区分 activePreviewPath 变化来自左侧 chip 还是右侧 Tab，避免重复 scroll/flash */
  const previewFocusSourceRef = useRef<"chip" | null>(null);
  const [, setIsAtBottom] = useState(true);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);

  const handleArtifactChipClick = useCallback(
    (path: string) => {
      previewFocusSourceRef.current = "chip";
      if (onTogglePreviewPath) {
        onTogglePreviewPath(path);
        return;
      }
      onFileLinkClick?.(path);
    },
    [onFileLinkClick, onTogglePreviewPath],
  );

  useEffect(() => {
    if (!activePreviewPath) {
      previewFocusSourceRef.current = null;
      return;
    }
    if (previewFocusSourceRef.current === "chip") {
      previewFocusSourceRef.current = null;
      return;
    }
    const id = artifactAnchorId(activePreviewPath);
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("animate-artifact-flash");
    void el.offsetWidth;
    el.classList.add("animate-artifact-flash");
    const t = window.setTimeout(() => {
      el.classList.remove("animate-artifact-flash");
    }, 1500);
    return () => window.clearTimeout(t);
  }, [activePreviewPath]);

  const lastMsg = messages.length ? messages[messages.length - 1] : null;
  const lastStreamSig = lastMsg
    ? `${lastMsg.id}:${(lastMsg.content?.length ?? 0)}`
    : "";

  const updateScrollState = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    const dist = scrollHeight - scrollTop - clientHeight;
    const atBottom = dist < 100;
    atBottomRef.current = atBottom;
    setIsAtBottom(atBottom);
    setShowJumpToBottom(!atBottom && dist > 120 && messages.length > 0);
  }, [messages.length]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    updateScrollState();
    el.addEventListener("scroll", updateScrollState, { passive: true });
    return () => el.removeEventListener("scroll", updateScrollState);
  }, [updateScrollState]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (atBottomRef.current) {
      requestAnimationFrame(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
        atBottomRef.current = true;
        setIsAtBottom(true);
        setShowJumpToBottom(false);
      });
    }
    // 仅随流式进度/条数滚到底部，避免 messages 引用导致每 token 重绑
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length, lastStreamSig, isLoading]);

  /**
   * 产物 chip 全量重算的稳定标量 key：流式仅最后一条 content 变长时，前缀指纹不变，
   * useMemo 跳过 buildMessageChipPaths，避免 O(n) 历史行反复 Diff。
   */
  const chipPathsDependencyKey =
    messages.length === 0
      ? ""
      : (() => {
          const n = messages.length;
          const last = messages[n - 1]!;
          const prior =
            n <= 1 ? "" : messages.slice(0, -1).map(chipPathsFingerprintPart).join("|");
          return `${n}|${prior}|${chipPathsFingerprintPart(last)}`;
        })();

  // 仅随 chipPathsDependencyKey（标量串）变化重算；messages 取自闭包，避免仅用 messages 引用作依赖导致无意义重算
  const chipPathsPerMessage = useMemo(() => buildMessageChipPaths(messages), [chipPathsDependencyKey]);

  return (
    <div className="relative h-full min-h-0 w-full flex-1">
      {showJumpToBottom ? (
        <button
          type="button"
          onClick={() => {
            atBottomRef.current = true;
            setIsAtBottom(true);
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
            setShowJumpToBottom(false);
          }}
          className="absolute bottom-2 right-2 z-20 inline-flex h-10 w-10 items-center justify-center rounded-full bg-[var(--surface-2)] shadow-lg ring-1 ring-white/10 ui-motion-fast hover:bg-[var(--surface-3)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)] dark:bg-[var(--surface-1)]/80 dark:hover:bg-[var(--surface-2)]"
          aria-label="跳到底部"
          title="回到底部"
        >
          <ChevronDown size={18} className="opacity-90 text-white" aria-hidden />
        </button>
      ) : null}
      <div
        ref={containerRef}
        className="h-full min-h-0 w-full overflow-y-auto pr-0.5"
      >
        {/* 宽度由外层 ChatArea 约束，此处置满 */}
        <div className="w-full">
        <ul className="flex flex-col gap-4">
          {messages.map((m, i) => {
            const isLast = i === messages.length - 1;
            const isUser = m.role === "user";
            const assistantWaiting =
              !isUser && isLoading && isLast && (m.content?.trim()?.length ?? 0) < 2;
            const isChatCard = m.kind === "chat_card" && m.chatCard;
            const ghostRunFinishedLine =
              m.role === "assistant" &&
              m.kind !== "chat_card" &&
              (m.content ?? "").trim() === "本轮执行完成";

            if (ghostRunFinishedLine) {
              return <li key={m.id} className="hidden" aria-hidden />;
            }

            return (
              <li key={m.id} className={isUser ? "flex flex-col items-end gap-0" : "flex flex-row items-start gap-3"}>
                {!isUser && <Avatar role="assistant" />}
                {/* Bubble + action bar stacked vertically, wrapped in a group for hover */}
                <div className={"group flex flex-col " + (isUser ? "items-end max-w-[92%]" : "items-start max-w-[92%]")}>
                  {isChatCard ? (
                    <ChatCardBubble
                      msg={m}
                      onFileLinkClick={onFileLinkClick}
                      postToAgentRaw={chatCardPostToAgent ?? (() => {})}
                      postToAgentSilentlyRaw={chatCardPostToAgentSilently}
                      onSendTextRaw={chatCardOnSendText}
                      onLockFilePickerRaw={chatCardOnLockFilePicker}
                      searchQuery={searchQuery}
                    />
                  ) : (
                    <div
                      className={
                        isUser
                          ? "rounded-2xl rounded-tr-sm px-5 py-4 text-base leading-relaxed"
                          : "rounded-2xl rounded-tl-sm px-5 py-4 text-base leading-relaxed ui-card"
                      }
                      style={
                        isUser
                          ? {
                              background: "color-mix(in oklab, var(--surface-2) 80%, var(--accent) 6%)",
                              border: "1px solid var(--border-subtle)",
                              color: "var(--text-primary)",
                            }
                          : undefined
                      }
                    >
                      {isUser ? (
                        <span className="whitespace-pre-wrap ui-text-primary leading-relaxed">{m.content}</span>
                      ) : assistantWaiting ? (
                        <div className="w-full space-y-2 py-0.5 animate-pulse" aria-busy>
                          <div className="h-3.5 w-full rounded-md bg-[var(--surface-2)]/50" />
                          <div className="h-3.5 w-[92%] rounded-md bg-[var(--surface-2)]/45" />
                          <div className="h-3.5 w-[70%] rounded-md bg-[var(--surface-2)]/40" />
                        </div>
                      ) : (
                        <>
                          <AgentMarkdown
                            content={m.content}
                            onFileLinkClick={onFileLinkClick}
                            searchQuery={searchQuery}
                            showStreamingCaret={
                              Boolean(showStreamingCaret && isLast && (m.content?.trim()?.length ?? 0) > 0)
                            }
                          />
                          <FileIndexChips
                            paths={chipPathsPerMessage[i] ?? []}
                            onFileLinkClick={onFileLinkClick}
                            activePreviewPath={activePreviewPath}
                            onChipClick={handleArtifactChipClick}
                          />
                        </>
                      )}
                    </div>
                  )}
                  {/* Hover action bar (copy + delete) */}
                  {m.content && !isChatCard && (
                    <MessageActions
                      content={m.content}
                      onDelete={onDeleteMessage ? () => onDeleteMessage(m.id) : undefined}
                    />
                  )}
                </div>
                {isUser && <div className="shrink-0 mt-0.5"><Avatar role="user" /></div>}
              </li>
            );
          })}
        </ul>
        {inlineStatusTag ? (
          <div className="mt-3 flex justify-center">
            <span
              className="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] ui-text-secondary"
              style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)" }}
            >
              {inlineStatusTag}
            </span>
          </div>
        ) : null}
        <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
});
