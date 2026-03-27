"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Check, Copy, FileText, Trash2, User } from "lucide-react";
import type { AgentMessage } from "@/hooks/useAgentChat";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import { extractFilesFromContent } from "@/lib/fileIndex";

type Props = {
  messages: AgentMessage[];
  isLoading: boolean;
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

function FileIndexChips({
  content,
  artifacts,
  onFileLinkClick,
}: {
  content: string;
  artifacts?: string[];
  onFileLinkClick?: (path: string) => void;
}) {
  const files = useMemo(() => {
    const fromContent = extractFilesFromContent(content);
    const seen = new Set(fromContent);
    const merged = [...fromContent];
    for (const p of artifacts ?? []) {
      const norm = p.trim();
      if (norm && !seen.has(norm)) {
        seen.add(norm);
        merged.push(norm);
      }
    }
    return merged;
  }, [content, artifacts]);
  if (files.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {files.map((path) => (
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

export const MessageList = memo(function MessageList({ messages, isLoading, onFileLinkClick, onDeleteMessage, searchQuery }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isLoading]);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto pr-1">
      {/* Constrain ultra-wide screens for comfortable reading */}
      <div className="w-full max-w-4xl mx-auto">
        <ul className="flex flex-col gap-4">
          {messages.map((m, i) => {
            const isLast = i === messages.length - 1;
            const isUser = m.role === "user";
            const assistantWaiting = !isUser && isLoading && isLast && !m.content?.trim();

            return (
              <li key={m.id} className={isUser ? "flex flex-col items-end gap-0" : "flex flex-row items-start gap-3"}>
                {!isUser && <Avatar role="assistant" />}
                {/* Bubble + action bar stacked vertically, wrapped in a group for hover */}
                <div className={"group flex flex-col " + (isUser ? "items-end max-w-[92%]" : "items-start max-w-[92%]")}>
                  <div
                    className={
                      isUser
                        ? "rounded-2xl rounded-tr-sm px-5 py-4 text-base leading-relaxed"
                        : "rounded-2xl rounded-tl-sm px-5 py-4 text-base leading-relaxed ui-card"
                    }
                    style={isUser ? { background: "var(--accent-soft)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" } : undefined}
                  >
                    {isUser ? (
                      <span className="whitespace-pre-wrap ui-text-primary leading-relaxed">{m.content}</span>
                    ) : assistantWaiting ? (
                      <span className="ui-text-muted text-base leading-relaxed">等待回复…</span>
                    ) : (
                      <>
                        <AgentMarkdown
                          content={m.content}
                          onFileLinkClick={onFileLinkClick}
                          searchQuery={searchQuery}
                        />
                        <FileIndexChips content={m.content} artifacts={m.artifacts} onFileLinkClick={onFileLinkClick} />
                      </>
                    )}
                  </div>
                  {/* Hover action bar (copy + delete) */}
                  {m.content && (
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
        <div ref={bottomRef} />
      </div>
    </div>
  );
});
