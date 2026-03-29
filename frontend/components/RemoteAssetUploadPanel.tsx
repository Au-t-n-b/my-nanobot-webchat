"use client";

import { AlertCircle, Loader2, Upload, X } from "lucide-react";
import { useEffect, useState } from "react";

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

type UploadKind = "skill" | "artifact";

function readRemoteError(
  body: { error?: { message?: string; detail?: string } },
  fallback: string,
): string {
  const message = body.error?.message?.trim();
  const detail = body.error?.detail?.trim();
  if (message && detail) return `${message}: ${detail}`;
  return message || detail || fallback;
}

export function RemoteAssetUploadPanel({
  onClose,
  onUploaded,
}: {
  onClose: () => void;
  onUploaded?: () => void;
}) {
  const [session, setSession] = useState<RemoteSession | null>(null);
  const [kind, setKind] = useState<UploadKind>("artifact");
  const [scope, setScope] = useState<"project" | "personal">("personal");
  const [skillFile, setSkillFile] = useState<File | null>(null);
  const [artifactFiles, setArtifactFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    fetch(aguiRequestPath("/api/remote-center/session"))
      .then((res) => res.json())
      .then((data: RemoteSession) => {
        setSession(data);
        setScope(data.selectedProjectId ? "project" : "personal");
      })
      .catch(() => {
        setSession(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSubmit = async () => {
    setSubmitting(true);
    setStatus("");
    setError("");
    try {
      if (kind === "skill") {
        if (!skillFile) throw new Error("请选择 skill zip 文件");
        const form = new FormData();
        form.append("scope", scope);
        if (scope === "project" && session?.selectedProjectId) {
          form.append("projectId", session.selectedProjectId);
        }
        form.append("sourceType", "zip_file");
        form.append("file", skillFile);
        const res = await fetch(aguiRequestPath("/api/remote-assets/personal-skills/upload"), {
          method: "POST",
          body: form,
        });
        const body = (await res.json().catch(() => ({}))) as { item?: { title?: string }; error?: { message?: string } };
        if (!res.ok) throw new Error(readRemoteError(body, `HTTP ${res.status}`));
        setStatus(`Skill 已上传：${body.item?.title ?? skillFile.name}`);
        setSkillFile(null);
        onUploaded?.();
        return;
      }

      if (!artifactFiles.length) throw new Error("请选择要上传的产物文件");
      const form = new FormData();
      form.append("scope", scope);
      if (scope === "project" && session?.selectedProjectId) {
        form.append("projectId", session.selectedProjectId);
      }
      for (const file of artifactFiles) {
        form.append("files", file);
      }
      const res = await fetch(aguiRequestPath("/api/remote-assets/personal-artifacts/upload"), {
        method: "POST",
        body: form,
      });
      const body = (await res.json().catch(() => ({}))) as { items?: Array<{ filename?: string }>; error?: { message?: string } };
      if (!res.ok) throw new Error(readRemoteError(body, `HTTP ${res.status}`));
      setStatus(`产物已上传：${body.items?.map((item) => item.filename).filter(Boolean).join(", ") || artifactFiles.length}`);
      setArtifactFiles([]);
      onUploaded?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside className="ui-panel h-full rounded-2xl p-4 flex flex-col gap-4 min-h-0">
      <div className="flex items-center justify-between gap-2 shrink-0">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider ui-text-secondary">
            个人上传 <span className="font-normal normal-case tracking-normal ui-text-muted">Upload Center</span>
          </p>
          <p className="text-xs ui-text-muted mt-1">默认支持任意格式文件上传；如需上传 Skill，再切换到 Skill zip。</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="ui-btn-ghost rounded-lg p-1.5"
          aria-label="关闭上传面板"
          title="关闭上传面板"
        >
          <X size={15} />
        </button>
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

      {loading ? (
        <div className="flex-1 flex items-center justify-center gap-2 ui-text-muted text-sm">
          <Loader2 size={16} className="animate-spin" />
          加载远端会话中…
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-auto flex flex-col gap-4">
          <section className="ui-card rounded-xl p-4 flex flex-col gap-3">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setKind("artifact")}
                className="rounded-lg px-3 py-1.5 text-xs"
                style={kind === "artifact" ? { background: "var(--accent)", color: "#fff" } : { background: "var(--surface-3)", color: "var(--text-secondary)" }}
              >
                任意文件上传
              </button>
              <button
                type="button"
                onClick={() => setKind("skill")}
                className="rounded-lg px-3 py-1.5 text-xs"
                style={kind === "skill" ? { background: "var(--accent)", color: "#fff" } : { background: "var(--surface-3)", color: "var(--text-secondary)" }}
              >
                Skill zip 上传
              </button>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-[11px] ui-text-muted">归属范围</label>
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value as "project" | "personal")}
                className="ui-input ui-input-focusable rounded-lg px-2.5 py-2 text-xs"
              >
                <option value="project" disabled={!session?.selectedProjectId}>当前项目</option>
                <option value="personal">个人空间</option>
              </select>
              <p className="text-[11px] ui-text-muted">
                当前项目：{session?.selectedProjectName ?? "未绑定项目，将默认使用个人空间"}
              </p>
            </div>

            {kind === "skill" ? (
              <div className="flex flex-col gap-2">
                <label className="text-[11px] ui-text-muted">选择 Skill zip 文件</label>
                <input
                  type="file"
                  accept=".zip,application/zip"
                  onChange={(e) => setSkillFile(e.target.files?.[0] ?? null)}
                  className="ui-input ui-input-focusable rounded-lg px-2.5 py-2 text-xs"
                />
                <p className="text-[11px] ui-text-muted">首版前端先支持 zip 上传，不改动现有其他侧栏功能。</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <label className="text-[11px] ui-text-muted">选择任意格式文件（可多选）</label>
                <input
                  type="file"
                  multiple
                  onChange={(e) => setArtifactFiles(Array.from(e.target.files ?? []))}
                  className="ui-input ui-input-focusable rounded-lg px-2.5 py-2 text-xs"
                />
                <p className="text-[11px] ui-text-muted">未绑定项目时会默认上传到个人空间。</p>
              </div>
            )}

            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={submitting}
              className="rounded-lg px-3 py-2 text-xs font-medium text-white disabled:opacity-50"
              style={{ background: "var(--accent)" }}
            >
              {submitting ? "上传中…" : <span className="inline-flex items-center gap-1.5"><Upload size={13} />开始上传</span>}
            </button>
          </section>
        </div>
      )}
    </aside>
  );
}
