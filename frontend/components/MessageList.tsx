"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Check, Copy, FileText, Trash2, User } from "lucide-react";
import type { AgentMessage } from "@/hooks/useAgentChat";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import { extractFilesFromContent } from "@/lib/fileIndex";
import { SkillUiRuntimeProvider } from "@/components/sdui/SkillUiRuntimeProvider";
import { SduiNodeView } from "@/components/sdui/SduiNodeView";

type Props = {
  messages: AgentMessage[];
  isLoading: boolean;
  inlineStatusTag?: string;
  onFileLinkClick?: (path: string) => void;
  onDeleteMessage?: (id: string) => void;
  searchQuery?: string;
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

/**
 * Pre-compute chip paths for every message in one pass so that:
 * 1. Bare filenames in message text are upgraded to full absolute paths using
 *    artifact data from ANY message (not just the current one).
 * 2. The same file is only shown once — in the earliest message that mentions it.
 */
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
}: {
  paths: string[];
  onFileLinkClick?: (path: string) => void;
}) {
  if (paths.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {paths.map((path) => (
        <button
          key={path}
          type="button"
          title={path}
          onClick={() => onFileLinkClick?.(path)}
          className="inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium transition-all duration-150 hover:-translate-y-px hover:shadow-sm active:translate-y-0"
          style={{
            borderColor: "var(--accent)",
            background: "var(--accent-soft)",
            color: "var(--accent)",
          }}
        >
          <FileText size={11} />
          {fileBasename(path)}
        </button>
      ))}
    </div>
  );
}

function Avatar({ role }: { role: "user" | "assistant" }) {
  return (
    <div
      className={
        "shrink-0 mt-0.5 w-6 h-6 rounded-full flex items-center justify-center " +
        (role === "user" ? "bg-[var(--surface-3)]" : "ui-card")
      }
    >
      {role === "user" ? (
        <User size={12} className="ui-text-secondary" />
      ) : (
        <Bot size={12} style={{ color: "var(--accent)" }} />
      )}
    </div>
  );
}

class ChatCardErrorBoundary extends (require("react").Component as typeof import("react").Component)<
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

function ChatCardBubble({
  msg,
  onFileLinkClick,
}: {
  msg: AgentMessage;
  onFileLinkClick?: (path: string) => void;
}) {
  const card = msg.chatCard;
  if (!card) return null;
  // Force unmount on replace (new event id) to ensure any debounced timers in SDUI inputs are cleaned up.
  const mountKey = `${card.cardId}:${card.id}`;
  return (
    <div
      className="chatcard-slide-up rounded-2xl rounded-tl-sm px-4 py-3 text-sm ui-card"
      style={{
        background: "var(--surface-2)",
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
            postToAgentRaw={() => {
              /* ChatCard 默认不直接发消息；需时在后续支持 */
            }}
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
  inlineStatusTag,
  onFileLinkClick,
  onDeleteMessage,
  searchQuery,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isLoading]);

  // Pre-compute chip paths for all messages in one pass:
  // - bare filenames are upgraded to full paths via the global artifact map
  // - each file appears only once (in the earliest message that references it)
  const chipPathsPerMessage = useMemo(() => buildMessageChipPaths(messages), [messages]);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto pr-1">
      {/* Constrain ultra-wide screens for comfortable reading */}
      <div className="w-full max-w-4xl mx-auto">
        <ul className="flex flex-col gap-4">
          {messages.map((m, i) => {
            const isLast = i === messages.length - 1;
            const isUser = m.role === "user";
            const assistantWaiting = !isUser && isLoading && isLast && !m.content?.trim();
            const isChatCard = m.kind === "chat_card" && m.chatCard;

            return (
              <li key={m.id} className={isUser ? "flex flex-col items-end gap-0" : "flex flex-row items-start gap-3"}>
                {!isUser && <Avatar role="assistant" />}
                {/* Bubble + action bar stacked vertically, wrapped in a group for hover */}
                <div className={"group flex flex-col " + (isUser ? "items-end max-w-[92%]" : "items-start max-w-[92%]")}>
                  {isChatCard ? (
                    <ChatCardBubble msg={m} onFileLinkClick={onFileLinkClick} />
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
                              background: "var(--accent-soft)",
                              border: "1px solid var(--border-subtle)",
                              color: "var(--text-primary)",
                            }
                          : undefined
                      }
                    >
                      {isUser ? (
                        <span className="whitespace-pre-wrap ui-text-primary leading-relaxed">{m.content}</span>
                      ) : assistantWaiting ? (
                        <span className="ui-text-muted text-base leading-relaxed">等待回复…</span>
                      ) : (
                        <>
                          <AgentMarkdown content={m.content} onFileLinkClick={onFileLinkClick} searchQuery={searchQuery} />
                          <FileIndexChips paths={chipPathsPerMessage[i] ?? []} onFileLinkClick={onFileLinkClick} />
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
  );
});
