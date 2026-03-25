"use client";

import { useEffect } from "react";
import { AlertCircle, RefreshCw, X } from "lucide-react";

type Props = {
  message: string;
  onRetry?: () => void;
  onClose: () => void;
};

export function ErrorToast({ message, onRetry, onClose }: Props) {
  useEffect(() => {
    const t = setTimeout(onClose, 5000);
    return () => clearTimeout(t);
  }, [message, onClose]);

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 flex items-start gap-3 rounded-2xl px-4 py-3 max-w-md w-[calc(100vw-2rem)] animate-in slide-in-from-top-2 duration-200 ui-panel" style={{ borderColor: "rgba(239,107,115,0.28)" }}>
      <AlertCircle size={16} className="shrink-0 mt-0.5" style={{ color: "var(--danger)" }} />
      <p className="flex-1 text-sm break-words" style={{ color: "var(--danger)" }}>{message}</p>
      <div className="flex items-center gap-1 shrink-0">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            aria-label="重试"
            className="rounded-md border border-[var(--border-subtle)] px-2 py-1 text-xs ui-text-secondary hover:bg-[var(--surface-3)] flex items-center gap-1 transition-colors"
          >
            <RefreshCw size={10} />
            重试
          </button>
        )}
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭错误提示"
          className="rounded-md p-1 ui-text-muted hover:bg-[var(--surface-3)] transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
