"use client";

import { useMemo } from "react";
import { FileSearch, X as XIcon } from "lucide-react";
import type { FileInsightReport } from "./previewTypes";
import { PreviewFileViewer } from "./PreviewFileViewer";

export type PreviewTabItem = { id: string; path: string; label: string };

type Props = {
  onClose: () => void;
  /** 预览类 Tab（文件 / browser），与中栏模块大盘互不抢焦点 */
  previewTabs: PreviewTabItem[];
  activeTabId: string | null;
  onSelectTab: (id: string) => void;
  onClosePreviewTab: (id: string) => void;
  onOpenPath: (path: string) => void;
  activeSkillName?: string | null;
  onFillInput?: (text: string) => void;
  onPreviewInsightRequest?: (path: string) => Promise<FileInsightReport>;
};

// ─── PreviewPanel (exported) ─────────────────────────────────────────────────

export function PreviewPanel({
  onClose,
  previewTabs,
  activeTabId,
  onSelectTab,
  onClosePreviewTab,
  onOpenPath,
  activeSkillName,
  onFillInput,
  onPreviewInsightRequest,
}: Props) {
  const tabs = useMemo(() => {
    const out: Array<{ id: string; label: string; path: string; kind: "preview" }> = [];
    for (const t of previewTabs) out.push({ id: t.id, label: t.label, path: t.path, kind: "preview" });
    return out;
  }, [previewTabs]);

  const effectiveActiveTabId = useMemo(() => {
    if (activeTabId && tabs.some((t) => t.id === activeTabId)) return activeTabId;
    return previewTabs[0]?.id ?? null;
  }, [activeTabId, previewTabs, tabs]);

  const activeTab = useMemo(
    () => (effectiveActiveTabId ? tabs.find((t) => t.id === effectiveActiveTabId) ?? null : null),
    [tabs, effectiveActiveTabId],
  );

  const showPathRow = false;

  return (
    <aside className="h-full min-h-0 flex flex-col gap-3 p-0 bg-transparent border-0 shadow-none text-[var(--text-primary)]">
      <div className="flex items-center justify-between gap-2 shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider ui-text-secondary">
          预览 <span className="font-normal normal-case tracking-normal ui-text-muted">Preview</span>
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 ui-text-muted hover:text-[var(--text-primary)] hover:bg-[var(--surface-3)] transition-colors"
          aria-label="关闭预览栏"
        >
          <XIcon size={14} />
        </button>
      </div>

      {showPathRow && null}

      <div className="flex flex-col flex-1 min-h-0 overflow-hidden rounded-2xl bg-[var(--paper-card)] border border-[var(--border-subtle)] text-[var(--text-primary)] shadow-[var(--shadow-panel)]">
        <div
          className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-[var(--border-subtle)] dark:border-white/10 bg-[var(--surface-3)]/80 dark:bg-black/25 px-1 py-1"
          role="tablist"
          aria-label="右侧面板标签"
        >
          {tabs.map((tab) => {
            const selected = tab.id === effectiveActiveTabId;
            const closable = tab.kind === "preview";
            return (
              <div
                key={tab.id}
                className={`group flex max-w-[12rem] shrink-0 items-center rounded-md border text-left text-[11px] transition-colors ${
                  selected
                    ? "border-[var(--accent)] bg-[var(--surface-2)] text-[var(--text-primary)]"
                    : "border-transparent bg-transparent ui-text-secondary hover:bg-[var(--surface-2)]"
                }`}
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  className="min-w-0 flex-1 truncate px-2 py-1 text-left"
                  title={tab.path}
                  onClick={() => onSelectTab(tab.id)}
                >
                  {tab.label}
                </button>
                {closable && (
                  <button
                    type="button"
                    className="shrink-0 rounded p-1 ui-text-muted opacity-70 hover:opacity-100 hover:bg-[var(--surface-3)]"
                    aria-label={`关闭 ${tab.label}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onClosePreviewTab(tab.id);
                    }}
                  >
                    <XIcon size={12} />
                  </button>
                )}
              </div>
            );
          })}
        </div>

        <div className="flex-1 min-h-0 overflow-auto p-5 bg-[var(--paper-card)]">
          {activeTab?.kind === "preview" && activeTab.path ? (
            <PreviewFileViewer
              key={activeTab.path}
              path={activeTab.path}
              onOpenPath={onOpenPath}
              activeSkillName={activeSkillName}
              onFillInput={onFillInput}
              onClosePanel={onClose}
              onPreviewInsightRequest={onPreviewInsightRequest}
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="flex w-full max-w-md flex-col items-center justify-center rounded-2xl border-2 border-dashed border-white/10 bg-[color-mix(in_srgb,var(--surface-1)_85%,transparent)] px-8 py-10 text-center">
                <div className="mb-4 rounded-2xl bg-[color-mix(in_srgb,var(--surface-3)_72%,transparent)] p-4 text-[var(--accent)]">
                  <FileSearch size={30} strokeWidth={1.8} className="opacity-85" />
                </div>
                <p className="text-base font-semibold ui-text-primary">暂无预览内容</p>
                <p className="mt-2 text-sm leading-6 ui-text-muted">
                  请在左侧会话中生成产物，或点击文件胶囊按钮在右侧分栏中预览。
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

