"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  content?: string | null;
};

/** 行内 code（p / li 内）柔和标签感；pre>code 在下方单独复位并交给 pre 容器 */
const inlineCode =
  "[&_p_code]:bg-[var(--surface-2)] [&_p_code]:text-[var(--text-primary)] [&_p_code]:px-1 [&_p_code]:py-0.5 [&_p_code]:rounded-lg [&_p_code]:text-sm [&_p_code]:font-mono [&_p_code]:border [&_p_code]:border-[var(--border-subtle)] " +
  "[&_li_code]:bg-[var(--surface-2)] [&_li_code]:text-[var(--text-primary)] [&_li_code]:px-1 [&_li_code]:py-0.5 [&_li_code]:rounded-lg [&_li_code]:text-sm [&_li_code]:font-mono [&_li_code]:border [&_li_code]:border-[var(--border-subtle)] " +
  "[&_blockquote_code]:bg-[var(--surface-2)] [&_blockquote_code]:text-[var(--text-primary)] [&_blockquote_code]:px-1 [&_blockquote_code]:py-0.5 [&_blockquote_code]:rounded-lg [&_blockquote_code]:text-sm [&_blockquote_code]:font-mono [&_blockquote_code]:border [&_blockquote_code]:border-[var(--border-subtle)]";

const preBlock =
  "[&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-2xl [&_pre]:border [&_pre]:border-[var(--border-subtle)] [&_pre]:bg-[var(--surface-1)] [&_pre]:p-3 " +
  "[&_pre_code]:bg-transparent [&_pre_code]:border-0 [&_pre_code]:p-0 [&_pre_code]:text-sm [&_pre_code]:font-mono [&_pre_code]:text-[var(--text-primary)]";

export function SduiMarkdown({ content }: Props) {
  const md = content ?? "";
  return (
    <div
      className={
        "max-w-none text-sm leading-relaxed ui-text-secondary " +
        "[&_strong]:font-semibold [&_strong]:ui-text-primary " +
        "[&_blockquote]:border-l-2 [&_blockquote]:border-[var(--border-subtle)] [&_blockquote]:pl-4 [&_blockquote]:my-3 [&_blockquote]:italic [&_blockquote]:ui-text-muted " +
        "[&_p]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:mb-2 [&_ol]:mb-2 " +
        inlineCode +
        " " +
        preBlock
      }
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
    </div>
  );
}
