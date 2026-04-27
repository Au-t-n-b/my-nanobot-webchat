"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  content?: string | null;
};

/** 行内 code（p / li 内）柔和标签感；pre>code 在下方单独复位并交给 pre 容器 */
const inlineCode =
  "[&_p_code]:bg-slate-50 [&_p_code]:text-slate-800 [&_p_code]:px-1 [&_p_code]:py-0.5 [&_p_code]:rounded [&_p_code]:text-[13px] [&_p_code]:font-mono [&_p_code]:dark:bg-[var(--surface-2)]/50 [&_p_code]:dark:text-[var(--text-secondary)] [&_p_code]:dark:border [&_p_code]:dark:border-white/5 " +
  "[&_li_code]:bg-slate-50 [&_li_code]:text-slate-800 [&_li_code]:px-1 [&_li_code]:py-0.5 [&_li_code]:rounded [&_li_code]:text-[13px] [&_li_code]:font-mono [&_li_code]:dark:bg-[var(--surface-2)]/50 [&_li_code]:dark:text-[var(--text-secondary)] [&_li_code]:dark:border [&_li_code]:dark:border-white/5 " +
  "[&_blockquote_code]:bg-slate-50 [&_blockquote_code]:text-slate-800 [&_blockquote_code]:px-1 [&_blockquote_code]:py-0.5 [&_blockquote_code]:rounded [&_blockquote_code]:text-[13px] [&_blockquote_code]:font-mono [&_blockquote_code]:dark:bg-[var(--surface-2)]/50 [&_blockquote_code]:dark:text-[var(--text-secondary)] [&_blockquote_code]:dark:border [&_blockquote_code]:dark:border-white/5";

const preBlock =
  "[&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:border-slate-200 [&_pre]:bg-slate-50 [&_pre]:p-3 [&_pre]:dark:border-white/5 [&_pre]:dark:bg-[var(--surface-2)]/50 " +
  "[&_pre_code]:bg-transparent [&_pre_code]:border-0 [&_pre_code]:p-0 [&_pre_code]:text-[13px] [&_pre_code]:font-mono [&_pre_code]:text-slate-800 [&_pre_code]:dark:text-[var(--text-primary)]";

export function SduiMarkdown({ content }: Props) {
  const md = content ?? "";
  return (
    <div
      className={
        "max-w-none text-sm leading-relaxed text-slate-700 dark:text-[var(--text-secondary)] " +
        "[&_strong]:font-semibold [&_strong]:text-slate-900 [&_strong]:dark:text-[var(--text-primary)] " +
        "[&_blockquote]:border-l-2 [&_blockquote]:border-slate-200 [&_blockquote]:pl-4 [&_blockquote]:my-3 [&_blockquote]:italic [&_blockquote]:text-slate-500 [&_blockquote]:dark:border-[var(--border-strong)] [&_blockquote]:dark:text-[var(--text-secondary)] " +
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
