"use client";

import { AlertCircle, Download, Loader2, RefreshCw, Upload, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

function aguiRequestPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

type RemoteSession = {
  connected: boolean;
  selectedProjectId: string | null;
  selectedProjectName: string | null;
};

type OrgSkillDetail = {
  id: string;
  kind: "org-skill";
  name: string;
  title: string;
  description: string;
  version: string;
  organizationName: string;
  uploaderId: string;
  updatedAt: string;
  tags: string[];
  canImport: boolean;
  canClone: boolean;
};

type Props = {
  assetId: string | null;
  onClose: () => void;
  onOpenUpload?: () => void;
  onImported?: () => void;
};

function readRemoteError(
  body: { error?: { message?: string; detail?: string } },
  fallback: string,
): string {
  const message = body.error?.message?.trim();
  const detail = body.error?.detail?.trim();
  if (message && detail) return `${message}: ${detail}`;
  return message || detail || fallback;
}

export function RemoteAssetDetailPanel({ assetId, onClose, onOpenUpload, onImported }: Props) {
  const [detail, setDetail] = useState<OrgSkillDetail | null>(null);
  const [session, setSession] = useState<RemoteSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<"import" | "clone" | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const loadDetail = useCallback(async () => {
    if (!assetId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [sessionRes, detailRes] = await Promise.all([
        fetch(aguiRequestPath("/api/remote-center/session")),
        fetch(aguiRequestPath(`/api/remote-assets/org-skills/${assetId}`)),
      ]);
      const sessionJson = (await sessionRes.json().catch(() => ({}))) as RemoteSession;
      setSession(sessionJson);
      if (!detailRes.ok) {
        const body = (await detailRes.json().catch(() => ({}))) as { error?: { message?: string; detail?: string } };
        throw new Error(readRemoteError(body, `HTTP ${detailRes.status}`));
      }
      const detailJson = (await detailRes.json()) as OrgSkillDetail;
      setDetail(detailJson);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载资产详情失败");
    } finally {
      setLoading(false);
    }
  }, [assetId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  const handleImport = async () => {
    if (!assetId) return;
    setActionLoading("import");
    setStatus("");
    setError("");
    try {
      const res = await fetch(aguiRequestPath(`/api/remote-assets/org-skills/${assetId}/import`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: "workspace-skills" }),
      });
      const body = (await res.json().catch(() => ({}))) as { importedPath?: string; error?: { message?: string; detail?: string } };
      if (!res.ok) {
        throw new Error(readRemoteError(body, `HTTP ${res.status}`));
      }
      setStatus(`已导入到本地 skills：${body.importedPath ?? "完成"}`);
      onImported?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "导入失败");
    } finally {
      setActionLoading(null);
    }
  };

  const handleClone = async () => {
    if (!assetId) return;
    setActionLoading("clone");
    setStatus("");
    setError("");
    try {
      const res = await fetch(aguiRequestPath(`/api/remote-assets/org-skills/${assetId}/clone-to-personal`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope: session?.selectedProjectId ? "project" : "personal",
          projectId: session?.selectedProjectId ?? null,
        }),
      });
      const body = (await res.json().catch(() => ({}))) as { item?: { title?: string }; error?: { message?: string; detail?: string } };
      if (!res.ok) {
        throw new Error(readRemoteError(body, `HTTP ${res.status}`));
      }
      setStatus(`已复制为个人资产：${body.item?.title ?? "完成"}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "复制失败");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <aside className="ui-panel h-full rounded-2xl p-4 flex flex-col gap-4 min-h-0">
      <div className="flex items-center justify-between gap-2 shrink-0">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider ui-text-secondary">
            组织资产 <span className="font-normal normal-case tracking-normal ui-text-muted">Org Asset Detail</span>
          </p>
          <p className="text-xs ui-text-muted mt-1">右侧查看详情，不影响现有预览与会话区域。</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadDetail()}
            className="ui-btn-ghost rounded-lg p-1.5"
            title="刷新详情"
            aria-label="刷新详情"
          >
            <RefreshCw size={14} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="ui-btn-ghost rounded-lg p-1.5"
            title="关闭详情"
            aria-label="关闭详情"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {status && (
        <div className="rounded-xl px-3 py-2 text-xs" style={{ background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.28)", color: "var(--success)" }}>
          {status}
        </div>
      )}
      {error && (
        <div className="rounded-xl px-3 py-2 text-xs flex items-center gap-2" style={{ background: "rgba(239,107,115,0.12)", border: "1px solid rgba(239,107,115,0.28)", color: "var(--danger)" }}>
          <AlertCircle size={13} className="shrink-0" />
          {error}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-auto">
        {!assetId ? (
          <div className="h-full flex items-center justify-center text-sm ui-text-muted">请选择一个组织资产查看详情。</div>
        ) : loading ? (
          <div className="h-full flex items-center justify-center gap-2 text-sm ui-text-muted">
            <Loader2 size={16} className="animate-spin" />
            加载详情中…
          </div>
        ) : detail ? (
          <div className="flex flex-col gap-4">
            <section className="ui-card rounded-xl p-4 flex flex-col gap-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold ui-text-primary">{detail.title || detail.name}</h2>
                  <p className="text-xs ui-text-muted mt-1">{detail.description || "暂无描述"}</p>
                </div>
                <span className="rounded-full px-2 py-1 text-[10px]" style={{ background: "var(--surface-3)", color: "var(--text-tertiary)" }}>
                  v{detail.version || "未标注"}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="ui-text-muted">组织：<span className="ui-text-primary">{detail.organizationName || "未标注"}</span></div>
                <div className="ui-text-muted">上传人：<span className="ui-text-primary">{detail.uploaderId || "未标注"}</span></div>
                <div className="ui-text-muted">更新时间：<span className="ui-text-primary">{detail.updatedAt || "未标注"}</span></div>
                <div className="ui-text-muted">当前归属：<span className="ui-text-primary">{session?.selectedProjectName ?? "个人空间"}</span></div>
              </div>
              {detail.tags?.length ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  {detail.tags.map((tag) => (
                    <span key={tag} className="rounded-full px-2 py-1 text-[10px]" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
                      {tag}
                    </span>
                  ))}
                </div>
              ) : null}
            </section>

            <section className="ui-card rounded-xl p-4 flex flex-col gap-3">
              <p className="text-sm font-medium ui-text-primary">可用操作</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleImport()}
                  disabled={actionLoading !== null}
                  className="rounded-lg px-3 py-2 text-xs font-medium text-white disabled:opacity-50"
                  style={{ background: "var(--accent)" }}
                >
                  {actionLoading === "import" ? "导入中…" : (
                    <span className="inline-flex items-center gap-1.5"><Download size={13} />导入到本地并刷新左侧技能</span>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => void handleClone()}
                  disabled={actionLoading !== null}
                  className="ui-btn-ghost rounded-lg px-3 py-2 text-xs"
                >
                  {actionLoading === "clone" ? "复制中…" : "复制为个人资产"}
                </button>
                <button
                  type="button"
                  onClick={onOpenUpload}
                  className="ui-btn-ghost rounded-lg px-3 py-2 text-xs"
                >
                  <span className="inline-flex items-center gap-1.5"><Upload size={13} />打开上传面板</span>
                </button>
              </div>
            </section>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center text-sm ui-text-muted">详情不可用。</div>
        )}
      </div>
    </aside>
  );
}
