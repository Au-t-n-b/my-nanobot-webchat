"use client";

import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { extractLocalPreviewPath } from "@/lib/localFileLink";

export function agentMarkdownComponents(onPreviewPath?: (path: string) => void): Components {
  return {
    a: ({ href, children, ...rest }) => {
      const p = extractLocalPreviewPath(href ?? undefined);
      if (p && onPreviewPath) {
        return (
          <button
            type="button"
            className="text-sky-400 hover:underline cursor-pointer bg-transparent border-0 p-0 font-inherit text-left inline"
            onClick={() => onPreviewPath(p)}
          >
            {children}
          </button>
        );
      }
      return (
        <a className="text-sky-400 underline" href={href} target="_blank" rel="noopener noreferrer" {...rest}>
          {children}
        </a>
      );
    },
    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
    ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
    li: ({ children }) => <li>{children}</li>,
    code: ({ className, children, ...props }) => {
      const inline = !className;
      if (inline) {
        return (
          <code className="rounded bg-zinc-800 px-1 py-0.5 text-[0.9em]" {...props}>
            {children}
          </code>
        );
      }
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },
    pre: ({ children }) => (
      <pre className="overflow-x-auto rounded-md border border-zinc-700 bg-zinc-950 p-2 text-xs my-2">{children}</pre>
    ),
  };
}

export function AgentMarkdown({
  content,
  onPreviewPath,
  className,
}: {
  content: string;
  onPreviewPath?: (path: string) => void;
  className?: string;
}) {
  return (
    <div className={className ?? "text-zinc-200 leading-relaxed break-words"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={agentMarkdownComponents(onPreviewPath)}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
