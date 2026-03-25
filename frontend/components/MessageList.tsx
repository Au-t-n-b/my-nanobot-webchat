"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Check, Copy, FileText, User } from "lucide-react";
import type { AgentMessage } from "@/hooks/useAgentChat";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import { extractFilesFromContent } from "@/lib/fileIndex";

type Props = {
  messages: AgentMessage[];
  isLoading: boolean;
  onFileLinkClick?: (path: string) => void;
  searchQuery?: string;
};

function CopyMsgButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const copy = (e: React.MouseEvent) => {
    e.stopPropagation();
    void navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      type="button"
      onClick={copy}
      aria-label="复制消息内容"
      title={copied ? "已复制" : "复制消息"}
      className={
        "opacity-0 group-hover:opacity-100 transition-opacity duration-150 " +
        "absolute top-2 right-2 rounded-md p-1.5 " +
        "ui-text-muted hover:text-[var(--text-secondary)]"
      }
      style={{ background: "color-mix(in srgb, var(--surface-3) 85%, transparent)", backdropFilter: "blur(4px)" }}
    >
      {copied
        ? <Check size={11} style={{ color: "var(--success)" }} />
        : <Copy size={11} />}
    </button>
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
  const files = (() => {
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
  })();
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

export function MessageList({ messages, isLoading, onFileLinkClick, searchQuery }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isLoading]);

  return (
    <ul className="flex-1 min-h-0 flex flex-col gap-3 overflow-y-auto pr-1">
      {messages.map((m, i) => {
        const isLast = i === messages.length - 1;
        const isUser = m.role === "user";
        const assistantWaiting = !isUser && isLoading && isLast && !m.content?.trim();

        return (
          <li key={m.id} className={isUser ? "flex justify-end items-start gap-2" : "flex justify-start items-start gap-2"}>
            {!isUser && <Avatar role="assistant" />}
            <div
              className={
                "relative group " +
                (isUser
                  ? "max-w-[82%] rounded-2xl rounded-tr-sm px-3 py-2 text-sm"
                  : "max-w-[92%] rounded-2xl rounded-tl-sm px-3 py-2 text-sm ui-card")
              }
              style={isUser ? { background: "var(--accent-soft)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" } : undefined}
            >
              {isUser ? (
                <span className="whitespace-pre-wrap ui-text-primary">{m.content}</span>
              ) : assistantWaiting ? (
                <span className="ui-text-muted text-sm">等待回复…</span>
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
              {m.content && <CopyMsgButton content={m.content} />}
            </div>
            {isUser && <Avatar role="user" />}
          </li>
        );
      })}
      <div ref={bottomRef} />
    </ul>
  );
}
