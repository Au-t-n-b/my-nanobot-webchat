"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

function useBodyPortal() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

type CenteredModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  /** Panel width; default matches previous SystemShellModal content width feel */
  panelClassName?: string;
  /** When true, overlay / header close / Escape do not dismiss (e.g. in-flight submit). */
  disableDismiss?: boolean;
};

export function CenteredModal({
  open,
  onClose,
  title,
  children,
  footer,
  panelClassName = "w-full max-w-lg",
  disableDismiss = false,
}: CenteredModalProps) {
  const mounted = useBodyPortal();

  useEffect(() => {
    if (!open || disableDismiss) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, disableDismiss]);

  if (!mounted || !open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-3 sm:p-6 bg-black/50 backdrop-blur-[1px]"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      {!disableDismiss ? (
        <button
          type="button"
          className="absolute inset-0 cursor-default"
          aria-label="关闭"
          onClick={onClose}
        />
      ) : (
        <div className="absolute inset-0 cursor-default" aria-hidden="true" />
      )}
      <div
        className={`relative flex max-h-[min(92dvh,92vh)] min-h-0 flex-col overflow-hidden rounded-2xl ui-elevation-4 ${panelClassName}`}
      >
        <div className="shrink-0 flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--border-subtle)] bg-[var(--surface-2)]/60">
          <div className="text-sm font-semibold ui-text-primary truncate">{title}</div>
          <button
            type="button"
            disabled={disableDismiss}
            onClick={onClose}
            className="rounded-md p-2 ui-text-muted hover:ui-text-primary hover:bg-[var(--surface-3)] transition-colors disabled:opacity-40 disabled:pointer-events-none"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 text-sm">{children}</div>
        {footer ? <div className="shrink-0 border-t border-[var(--border-subtle)] px-4 py-3">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}

type ConfirmVariant = "default" | "warning" | "danger";

type CenteredConfirmModalProps = {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: ConfirmVariant;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function CenteredConfirmModal({
  open,
  title,
  description,
  confirmText = "确认",
  cancelText = "取消",
  variant = "default",
  loading = false,
  onConfirm,
  onCancel,
}: CenteredConfirmModalProps) {
  const accent =
    variant === "danger"
      ? "var(--danger)"
      : variant === "warning"
        ? "var(--warning)"
        : "var(--accent)";

  const footer = (
    <div className="flex flex-wrap justify-end gap-2">
      <button
        type="button"
        disabled={loading}
        onClick={onCancel}
        className="ui-btn-ghost rounded-lg px-3 py-1.5 text-xs font-medium"
      >
        {cancelText}
      </button>
      <button
        type="button"
        disabled={loading}
        onClick={onConfirm}
        className="rounded-lg px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
        style={{ background: accent }}
      >
        {loading ? "处理中…" : confirmText}
      </button>
    </div>
  );

  return (
    <CenteredModal
      open={open}
      onClose={onCancel}
      title={title}
      footer={footer}
      disableDismiss={Boolean(loading)}
    >
      <div className="ui-text-secondary space-y-2">{description}</div>
    </CenteredModal>
  );
}
